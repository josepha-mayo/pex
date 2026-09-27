"""Public OpenCode worker entry used only inside a caller-owned Linux boundary.

Contains no evaluator, provider credentials or controller plan. The controller
must mount this runtime read-only and enforce the shared deadline at its relay.
"""

import asyncio
import json
import math
import sys
import threading
from pathlib import Path
from time import monotonic

from benchmarks.opencode_review_client import review_request
from benchmarks.opencode_session import SessionRun, run_session
from benchmarks.worker_model_proxy import make_server, relay_request


def worker_settings(model: str, port: int) -> dict:
    """Identical coding tools for baseline and PEX; transport stays local."""
    if (not isinstance(model, str) or not model or len(model) > 256
            or any(ord(char) < 33 for char in model)):
        raise ValueError("worker model must be bounded and nonempty")
    if type(port) is not int or not 1 <= port <= 65_535:
        raise ValueError("worker relay port is invalid")
    return {
        "autoupdate": False, "share": "disabled",
        "model": f"controlled/{model}", "small_model": f"controlled/{model}",
        "enabled_providers": ["controlled"],
        "permission": {"*": "deny", "read": "allow", "glob": "allow", "grep": "allow",
                       "edit": "allow", "bash": "allow"},
        "provider": {"controlled": {
            "npm": "@ai-sdk/openai-compatible", "name": "Controller relay",
            "options": {"baseURL": f"http://127.0.0.1:{port}/v1", "apiKey": "pex-relay-local"},
            "models": {model: {"name": model, "limit": {"context": 32_000, "output": 1200}}},
        }},
    }


async def run_worker(
    *, executable: Path, workspace: Path, socket_path: str, model: str, prompt: str,
    log_directory: Path, state_home: Path, deadline: float, supervised: bool, max_followups: int,
) -> SessionRun:
    """Run the common same-session loop without inheriting host configuration.

    This function does not create or verify isolation. Its caller must launch
    it through worker_runtime_relay_command and retain/terminate that boundary.
    Logs are worker observations, not independently trusted evaluation results.
    """
    if sys.platform != "linux":
        raise RuntimeError("OpenCode relay worker requires the Linux worker boundary")
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("worker deadline must be finite")
    if type(supervised) is not bool:
        raise ValueError("worker condition must be explicit")
    if type(max_followups) is not int or not 0 <= max_followups <= 10:
        raise ValueError("worker follow-up limit is invalid")
    if not supervised and max_followups != 0:
        raise ValueError("baseline worker cannot have follow-ups")
    for path in (executable, workspace, log_directory, state_home, Path(socket_path)):
        if not path.is_absolute():
            raise ValueError("worker paths must be absolute")
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise TimeoutError("worker exhausted the shared deadline before startup")
    if state_home.is_relative_to(workspace) or workspace.is_relative_to(state_home):
        raise ValueError("worker state must be separate from the public task")
    state_home.mkdir(exist_ok=False, parents=True)

    def model_request(socket, body):
        budget = deadline - monotonic()
        if budget <= 0:
            raise TimeoutError("worker exhausted the shared model deadline")
        return relay_request(socket, body, timeout=budget)

    server = make_server(socket_path, model=model, relay=model_request)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    try:
        settings = worker_settings(model, server.server_port)
        environment = {
            "PATH": "/usr/bin:/bin", "HOME": str(state_home / "home"), "PYTHONNOUSERSITE": "1",
            "XDG_CONFIG_HOME": str(state_home / "config"),
            "XDG_DATA_HOME": str(state_home / "data"),
            "XDG_CACHE_HOME": str(state_home / "cache"),
            "XDG_STATE_HOME": str(state_home / "state"),
            "OPENCODE_CONFIG_CONTENT": json.dumps(settings, separators=(",", ":")),
        }

        async def review(turns):
            turn = turns[-1]
            return await asyncio.to_thread(
                review_request, socket_path, vendor_session_id=turn.session_id,
                agent_messages=turn.messages, deadline=deadline,
            )

        log_directory.mkdir(exist_ok=False, parents=True)
        result = await run_session(
            executable=executable, workspace=workspace, model=f"controlled/{model}", prompt=prompt,
            environment=environment, log_directory=log_directory, deadline=deadline,
            review=review if supervised else None, max_followups=max_followups,
        )
    finally:
        # A stuck HTTP handler must not turn teardown into an unbounded wait.
        # On failure the outer controller must tear down the entire boundary.
        shutdown = threading.Thread(target=server.shutdown, daemon=True)
        shutdown.start()
        shutdown.join(timeout=1)
        server.server_close()
        thread.join(timeout=1)
        if shutdown.is_alive() or thread.is_alive():
            raise RuntimeError("worker proxy teardown uncertain; terminate the worker boundary")
    if monotonic() >= deadline:
        raise TimeoutError("worker teardown exhausted the shared task deadline")
    return result
