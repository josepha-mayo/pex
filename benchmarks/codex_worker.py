"""Public Responses worker; caller must enforce a Linux OS boundary.

This transport never loads host credentials or scores its own work. The
controller owns the model budget, executable pin and process isolation.
"""

import asyncio
import json
import math
import sys
import threading
from pathlib import Path
from time import monotonic

from benchmarks.worker_model_proxy import _decode, _encode, make_server, relay_request

MAX_PROTOCOL_BYTES = 1_048_576


def provider_settings(port: int, model: str) -> dict:
    if (type(port) is not int or not 1 <= port <= 65_535
            or not isinstance(model, str) or not model or len(model) > 256
            or any(ord(char) < 33 for char in model)):
        raise ValueError("invalid pinned provider configuration")
    return {
        "model": model, "model_provider": "controlled", "web_search": "disabled",
        "features.multi_agent": False, "features.goals": False,
        "model_providers.controlled.name": "Controller relay",
        "model_providers.controlled.base_url": f"http://127.0.0.1:{port}/v1",
        "model_providers.controlled.wire_api": "responses",
        "model_providers.controlled.requires_openai_auth": False,
        "model_providers.controlled.supports_websockets": False,
        "model_providers.controlled.request_max_retries": 0,
        "model_providers.controlled.stream_max_retries": 0,
    }


async def run_worker(*, executable: Path, workspace: Path, state_home: Path,
                     socket_path: str, model: str, prompts: list[str], deadline: float) -> dict:
    """Complete supplied turns in one fresh session; no supervision claim."""
    if sys.platform != "linux":
        raise RuntimeError("Codex worker requires Linux")
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("worker deadline must be finite")
    if (not isinstance(prompts, list) or not 1 <= len(prompts) <= 11
            or any(not isinstance(text, str) or not text.strip() or len(text) > 20_000
                   or "\x00" in text for text in prompts)):
        raise ValueError("worker prompts must be bounded")
    for path in (executable, workspace, state_home, Path(socket_path)):
        if not path.is_absolute():
            raise ValueError("worker paths must be absolute")
    if state_home.is_relative_to(workspace) or workspace.is_relative_to(state_home):
        raise ValueError("worker state must be separate from the task")
    state_home.mkdir(exist_ok=False, parents=True)

    def remaining():
        budget = deadline - monotonic()
        if budget <= 0:
            raise TimeoutError("Codex worker exhausted shared deadline")
        return budget

    def request_model(path, body):
        return relay_request(path, body, timeout=remaining())

    server = make_server(socket_path, model=model, relay=request_model, wire_api="responses")
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
    thread.start()
    process = None
    pending = []
    turns = []
    serial = 0
    observed = 0
    observed_bytes = 0

    async def read():
        nonlocal observed, observed_bytes
        observed += 1
        if observed > 10_000:
            raise ValueError("Codex protocol observation bound exceeded")
        budget = remaining()
        line = await asyncio.wait_for(process.stdout.readline(), timeout=budget)
        remaining()
        if not line or len(line) > MAX_PROTOCOL_BYTES:
            raise ValueError("Codex protocol frame missing or oversized")
        observed_bytes += len(line)
        if observed_bytes > 64 * 1024 * 1024:
            raise ValueError("Codex protocol exceeds total observation bound")
        value = _decode(line)
        if not isinstance(value, dict):
            raise ValueError("Codex protocol requires objects")
        # Unsolicited server requests (including approval) are never approved.
        if "method" in value and "id" in value:
            raise ValueError("unexpected Codex server request")
        return value

    async def rpc(method, params):
        nonlocal serial
        serial += 1
        identity = serial
        budget = remaining()
        process.stdin.write(_encode({"id": identity, "method": method, "params": params}) + b"\n")
        await asyncio.wait_for(process.stdin.drain(), timeout=budget)
        while True:
            value = await read()
            if value.get("id") == identity:
                if "error" in value or not isinstance(value.get("result"), dict):
                    raise ValueError("Codex RPC did not return a successful object")
                return value["result"]
            if "id" in value:
                raise ValueError("unexpected Codex response identity")
            pending.append(value)

    try:
        command = [str(executable)]
        for key, value in provider_settings(server.server_port, model).items():
            command.extend(["-c", key + "=" + json.dumps(value)])
        command.append("app-server")
        budget = remaining()
        process = await asyncio.wait_for(asyncio.create_subprocess_exec(
            *command, cwd=workspace, env={"PATH": "/usr/bin:/bin", "HOME": str(state_home),
                                        "CODEX_HOME": str(state_home), "NO_COLOR": "1"},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=MAX_PROTOCOL_BYTES,
        ), timeout=budget)
        await rpc("initialize", {"clientInfo": {"name": "pex-worker", "version": "1"}})
        budget = remaining()
        process.stdin.write(_encode({"method": "initialized", "params": {}}) + b"\n")
        await asyncio.wait_for(process.stdin.drain(), timeout=budget)
        started = await rpc("thread/start", {"cwd": str(workspace), "ephemeral": True,
                                            "sandbox": "danger-full-access",
                                            "approvalPolicy": "never"})
        session = started["thread"]["id"]
        if not isinstance(session, str) or not 1 <= len(session) <= 256:
            raise ValueError("invalid Codex session receipt")
        for prompt in prompts:
            result = await rpc("turn/start", {"threadId": session,
                                              "input": [{"type": "text", "text": prompt}]})
            identity = result["turn"]["id"]
            if not isinstance(identity, str) or not 1 <= len(identity) <= 256:
                raise ValueError("invalid Codex turn receipt")
            if any(turn["turn_id"] == identity for turn in turns):
                raise ValueError("Codex reused a completed turn")
            while True:
                value = pending.pop(0) if pending else await read()
                if value.get("method") != "turn/completed":
                    continue
                params = value.get("params", {})
                turn = params.get("turn", {})
                if params.get("threadId") != session or turn.get("id") != identity:
                    raise ValueError("Codex completion does not match the active turn")
                if turn.get("status") != "completed":
                    raise ValueError("Codex turn did not complete")
                turns.append({"turn_id": identity, "status": "completed"})
                break
        remaining()
        result = {"vendor_session_id": session, "turns": turns, "quality_measured": False,
                  "presentation_eligible": False}
    finally:
        try:
            if process is not None and process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    process.kill()
                    await asyncio.wait_for(process.wait(), timeout=2)
        finally:
            shutdown = threading.Thread(target=server.shutdown, daemon=True)
            shutdown.start()
            shutdown.join(timeout=1)
            server.server_close()
            thread.join(timeout=1)
            if shutdown.is_alive() or thread.is_alive():
                raise RuntimeError("Codex proxy teardown uncertain; terminate worker boundary")
    remaining()
    return result
