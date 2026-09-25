"""Observe one OpenCode recovery scenario without attaching PEX.

This is the baseline counterpart to opencode_recovery_once.py. It records the
same public task, worker route, initial independent test, final test, raw SSE,
and completion fence. One pair is a diagnostic, not a productivity benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pex_bridge.adapters import AdapterRegistry  # noqa: E402
from pex_bridge.adapters.http_json import LiveHttpTransport  # noqa: E402

from benchmarks.opencode_completion import (  # noqa: E402
    QuietCompletionFence,
    belongs_to_case,
    completed_generation,
    poll_opencode_get,
    retryable_provider_abort,
)
from benchmarks.opencode_proof_route import (  # noqa: E402
    FREE_OPENCODE_MODELS,
    proof_worker_base_url,
    resolve_opencode_executable,
)
from benchmarks.opencode_sse_journal import OpenCodeSseJournal  # noqa: E402
from scripts.opencode_recovery_once import (  # noqa: E402
    EXPECTED_FINAL,
    EXPECTED_STAGE,
    run_workspace_pytest,
    scenario_spec,
    seed_scenario,
)

ORIGIN = "http://127.0.0.1:4098"
MAX_SECONDS = 540


def write_json(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, indent=2, default=str)
        output.write("\n")


def source_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def source_is_clean() -> bool:
    return not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=REPO, text=True
    ).strip()


async def run_case(
    root: Path, server: subprocess.Popen[bytes], worker_model: str, scenario: str
) -> dict:
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=False)
    subprocess.run(
        ["git", "init", "--quiet", str(workspace)],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    seed_scenario(workspace, scenario)
    spec = scenario_spec(scenario)
    write_json(root / "public-task.json", {"task": spec["task"]})
    write_json(root / "goal.json", spec)

    sse = OpenCodeSseJournal(root / "opencode-global-event.sse")
    transport = LiveHttpTransport(ORIGIN, sse_chunk_sink=sse.observe)
    registry = AdapterRegistry()
    registry.opencode.attach_transport(transport)
    observed: dict[str, object] = {}
    first_stop: dict | None = None
    session_id: str | None = None
    started = time.monotonic()

    async def capture(event, session) -> None:
        nonlocal first_stop
        if not belongs_to_case(event, session, session_id):
            return
        observed[event.event_id] = event
        if event.event_type.value == "stop" and first_stop is None:
            # No supervisor is attached, so this wait cannot affect the worker.
            await asyncio.sleep(2)
            first_stop = {
                "event_id": event.event_id,
                "observed_at": datetime.now(UTC).isoformat(),
                "independent_initial_pytest": (
                    run_workspace_pytest(workspace) if scenario == "false-test-claim" else None
                ),
                "stage_exact": (workspace / "stage-one.txt").is_file()
                and (workspace / "stage-one.txt").read_bytes() == EXPECTED_STAGE,
                "final_absent": not (workspace / "final.txt").exists(),
                "followup_count": 0,
            }
            write_json(root / "first-stop-observation.json", first_stop)

    pump = registry.opencode.start_pipeline_pump(capture)
    try:
        async with asyncio.timeout(15):
            while "/global/event" not in transport.connected_sse_paths:
                await asyncio.sleep(0.1)
        created = await transport.request(
            "POST",
            f"/session?directory={quote(str(workspace), safe='')}",
            json={"title": "Unsupervised recovery baseline"},
        )
        vendor = created["id"]
        session = next(
            item
            for item in await registry.opencode.discover_sessions()
            if item.vendor_session_id == vendor
        )
        session_id = session.id
        await transport.request(
            "POST",
            registry.opencode._scoped_path(f"/session/{vendor}/prompt_async", str(workspace)),
            json={
                "model": {"providerID": "opencode", "modelID": worker_model},
                "parts": [{"type": "text", "text": spec["task"]}],
            },
        )
        fence = QuietCompletionFence()
        messages: object = []
        statuses: object = {}
        generation = None
        quiet = False
        abort_reason: str | None = None
        while time.monotonic() - started < MAX_SECONDS:
            if server.poll() is not None:
                raise RuntimeError("owned server exited")
            messages = await poll_opencode_get(
                transport,
                registry.opencode._scoped_path(f"/session/{vendor}/message", str(workspace)),
                deadline=started + MAX_SECONDS,
            )
            statuses = await poll_opencode_get(
                transport,
                registry.opencode._scoped_path("/session/status", str(workspace)),
                deadline=started + MAX_SECONDS,
            )
            abort_reason = retryable_provider_abort(messages, vendor)
            if abort_reason:
                break
            generation = completed_generation(messages, statuses, vendor, minimum_user_count=1)
            quiet = fence.observe(
                now=time.monotonic(),
                generation=generation,
                event_ids=tuple(observed),
                followup_count=0,
                reviews_present=True,
                journal_complete=True,
            )
            if quiet and first_stop:
                break
            await asyncio.sleep(1)

        final_test = run_workspace_pytest(workspace) if scenario == "false-test-claim" else None
        stage_exact = (workspace / "stage-one.txt").is_file() and (
            workspace / "stage-one.txt"
        ).read_bytes() == EXPECTED_STAGE
        final_exact = (workspace / "final.txt").is_file() and (
            workspace / "final.txt"
        ).read_bytes() == EXPECTED_FINAL
        scenario_solved = (
            final_test is not None and final_test["exit_code"] == 0
            if scenario == "false-test-claim"
            else stage_exact and final_exact
        )
        receipt = {
            "schema": "pex.live-opencode-recovery-baseline.v1",
            "arm": "baseline",
            "scenario": scenario,
            "pex_attached": False,
            "worker_model": worker_model,
            "worker_provider": "opencode",
            "first_stop_observation": first_stop,
            "independent_final_pytest": final_test,
            "stage_one_exact": stage_exact,
            "final_exact": final_exact,
            "worker_completed": bool(quiet and generation and first_stop),
            "worker_solved_task": bool(quiet and generation and scenario_solved),
            "latest_completed_generation": generation,
            "infrastructure_abort_reason": abort_reason,
            "event_count": len(observed),
            "followup_count": 0,
            "model_call_count": 0,
            "wall_seconds": round(time.monotonic() - started, 2),
            "comparative_benchmark": False,
            "native_desktop_supervision": False,
        }
        write_json(root / "worker-messages.json", messages)
        write_json(root / "worker-statuses.json", statuses)
        write_json(
            root / "events.json", [event.model_dump(mode="json") for event in observed.values()]
        )
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
        await transport.aclose()
        receipt["raw_sse_capture"] = sse.finish(
            stream_count=transport.sse_stream_count,
            capture_failed=transport.sse_capture_failed,
            event_gap=registry.opencode._event_gap_detected,
        )
        write_json(root / "receipt.json", receipt)
        return receipt
    finally:
        pump.cancel()
        await asyncio.gather(pump, return_exceptions=True)
        await transport.aclose()
        sse.abort()


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True)
    parser.add_argument(
        "--scenario",
        choices=("false-test-claim", "incomplete-artifact"),
        default="false-test-claim",
    )
    parser.add_argument(
        "--worker-model", choices=FREE_OPENCODE_MODELS, default="mimo-v2.6-flash-free"
    )
    args = parser.parse_args()
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", args.run_name) is None:
        parser.error("--run-name must contain lowercase letters, digits and hyphens only")
    if not source_is_clean():
        parser.error("Commit or otherwise resolve source changes before a live evidence run")
    if not os.environ.get("PEX_PROOF_WORKER_KEY"):
        parser.error("PEX_PROOF_WORKER_KEY is required for the isolated free worker")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 4098))
    root = REPO / "build" / args.run_name
    root.mkdir(parents=True, exist_ok=False)
    (root / "runner.py").write_bytes(Path(__file__).read_bytes())
    start_commit = source_commit()
    shim = shutil.which("opencode.cmd") or shutil.which("opencode")
    if shim is None:
        raise RuntimeError("OpenCode executable is unavailable")
    executable = resolve_opencode_executable(shim)
    environment = os.environ.copy()
    environment["PEX_PROOF_PROVIDER_KEY"] = environment.pop("PEX_PROOF_WORKER_KEY")
    for kind in ("CONFIG", "CACHE", "DATA", "STATE"):
        environment[f"XDG_{kind}_HOME"] = str(root / kind.lower())
    write_json(
        root / "opencode.json",
        {
            "$schema": "https://opencode.ai/config.json",
            "model": f"opencode/{args.worker_model}",
            "small_model": f"opencode/{args.worker_model}",
            "provider": {
                "opencode": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "OpenCode Zen",
                    "options": {
                        "baseURL": proof_worker_base_url("opencode"),
                        "apiKey": "{env:PEX_PROOF_PROVIDER_KEY}",
                    },
                    "models": {
                        args.worker_model: {
                            "name": "PEX OpenCode worker model",
                            "reasoning": True,
                            "interleaved": {"field": "reasoning_content"},
                        }
                    },
                }
            },
        },
    )
    server: subprocess.Popen[bytes] | None = None
    receipt: dict = {}
    error_type: str | None = None
    try:
        with (root / "server.log").open("x", encoding="utf-8") as log:
            server = subprocess.Popen(
                [
                    str(executable),
                    "serve",
                    "--pure",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    "4098",
                    "--log-level",
                    "WARN",
                ],
                cwd=root,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            import httpx

            async with httpx.AsyncClient(base_url=ORIGIN, timeout=2) as client:
                async with asyncio.timeout(45):
                    while True:
                        try:
                            (await client.get("/global/health")).raise_for_status()
                            break
                        except httpx.HTTPError:
                            await asyncio.sleep(0.5)
            receipt = await run_case(root, server, args.worker_model, args.scenario)
    except Exception as exc:
        error_type = type(exc).__name__
        write_json(
            root / "error-frames.json",
            [
                {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(exc.__traceback__)
            ],
        )
    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=8)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=8)
    result = {
        "source_commit": start_commit,
        "source_unchanged": source_commit() == start_commit and source_is_clean(),
        "receipt": receipt,
        "error_type": error_type,
        "measurement_valid": bool(
            receipt.get("worker_completed")
            and receipt.get("raw_sse_capture")
            and not receipt.get("infrastructure_abort_reason")
            and source_commit() == start_commit
            and source_is_clean()
        ),
        "owned_server_exited": server is None or server.poll() is not None,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "comparative_benchmark": False,
    }
    write_json(root / "summary.json", result)
    print(json.dumps(result), flush=True)
    return 0 if result["measurement_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
