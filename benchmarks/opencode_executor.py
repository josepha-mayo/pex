"""Controller-owned launch of an admitted OpenCode worker, without scoring."""

import asyncio
import base64
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from pex_bridge.adapters.strict_json import strict_json_loads

from benchmarks import boundary, runner
from benchmarks.async_budget import await_with_budget
from benchmarks.linux_sandbox import worker_runtime_relay_command
from benchmarks.opencode_cli import completed_turn
from benchmarks.opencode_runtime import measure_profile
from benchmarks.opencode_session import REPAIR_ACTIONS
from benchmarks.paired_preparation import admit_opencode_relay

MAX_OUTPUT = 96 * 1024 * 1024


def worker_observation(raw: bytes, *, supervised: bool, max_followups: int) -> dict:
    """Validate exported natural stops; worker claims do not establish quality."""
    if not 0 < len(raw) <= MAX_OUTPUT:
        raise ValueError("worker output exceeds its envelope bound")
    packet = strict_json_loads(raw)
    if not isinstance(packet, dict) or set(packet) != {
        "schema", "turns", "actions", "followups", "followup_limit_reached",
    } or packet["schema"] != "pex.opencode-worker-output.v1":
        raise ValueError("invalid worker output envelope")
    turns, actions, followups = packet["turns"], packet["actions"], packet["followups"]
    if (not isinstance(turns, list) or not 1 <= len(turns) <= max_followups + 1
            or not isinstance(actions, list) or not isinstance(followups, list)
            or len(followups) > max_followups
            or type(packet["followup_limit_reached"]) is not bool):
        raise ValueError("worker output exceeds the admitted session limits")
    if not supervised and (len(turns) != 1 or actions or followups
                           or packet["followup_limit_reached"]):
        raise ValueError("baseline worker reported supervision")
    if supervised and (len(actions) != len(turns) or len(followups) != len(turns) - 1):
        raise ValueError("worker review/turn lineage is incomplete")
    if (any(not isinstance(action, str) or action not in REPAIR_ACTIONS | {"NOOP"}
            for action in actions) or "NOOP" in actions[:-1]
            or any(not isinstance(text, str) or not text.strip() or len(text) > 20_000
                   or "\x00" in text for text in followups)):
        raise ValueError("worker output reports invalid review instructions")
    if supervised and (
        packet["followup_limit_reached"] != (actions[-1] in REPAIR_ACTIONS)
        or (packet["followup_limit_reached"] and len(followups) != max_followups)
    ):
        raise ValueError("terminal review does not match the follow-up capacity")
    vendor = None
    total = 0
    verified = []
    for row in turns:
        if not isinstance(row, dict) or set(row) != {
            "session_id", "stdout_sha256", "stdout_bytes", "jsonl_base64",
        }:
            raise ValueError("invalid worker turn export")
        if not isinstance(row["jsonl_base64"], str):
            raise ValueError("worker turn export must be base64 text")
        data = base64.b64decode(row["jsonl_base64"], validate=True)
        total += len(data)
        if total > 64 * 1024 * 1024:
            raise ValueError("worker turn exports exceeded their aggregate bound")
        turn = completed_turn(data, exit_code=0, expected_session=vendor)
        if (turn.session_id != row["session_id"] or turn.stdout_sha256 != row["stdout_sha256"]
                or type(row["stdout_bytes"]) is not int
                or turn.stdout_bytes != row["stdout_bytes"]):
            raise ValueError("worker export does not match its natural-stop receipt")
        vendor = turn.session_id
        verified.append({"session_id": vendor, "stdout_sha256": turn.stdout_sha256,
                         "stdout_bytes": turn.stdout_bytes, "event_count": turn.event_count})
    return {"turns": verified, "actions": actions, "followups": followups,
            "followup_limit_reached": packet["followup_limit_reached"]}


async def execute_attempt(
    destination: Path, *, index: int, expected_plan_sha256: str, runtime: Path, model: str,
    backend, review,
) -> dict:
    """Measure, consume, launch, and retain one attempt. Never evaluates or retries.

    Review/backend callbacks stay on the controller. Runtime measurement and the
    actual bubblewrap launch are required; a declared isolation flag cannot bypass
    them. Result records remain ineligible until separate evaluation/provenance.
    """
    if sys.platform != "linux":
        raise RuntimeError("OpenCode attempt execution requires Linux")
    profile = measure_profile(runtime, model=model)
    relay, reservation, limits = admit_opencode_relay(
        destination, index=index, expected_plan_sha256=expected_plan_sha256,
        worker_profile=profile, backend=backend, review=review,
    )
    row = reservation["entry"]
    workspace = destination.absolute() / "workers" / row["workspace"]
    control = destination.absolute() / "controller" / ("run-" + row["workspace"])
    control.mkdir(mode=0o700, exist_ok=False)
    result = {"schema": "pex.opencode-attempt.v1", "status": "failed_uncertain",
              "reservation": reservation, "presentation_eligible": False,
              "quality_measured": False}
    process = None
    captures = []
    server = None
    started = time.perf_counter()

    async def capture(reader, handle):
        total = 0
        while chunk := await reader.read(64 * 1024):
            total += len(chunk)
            if total > MAX_OUTPUT:
                raise ValueError("worker controller capture exceeds its output bound")
            handle.write(chunk)

    async def reap():
        if process is not None and process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await await_with_budget(process.wait, budget=5)

    async def settle_captures():
        for task in captures:
            if not task.done():
                task.cancel()
        if captures:
            await await_with_budget(
                lambda: asyncio.gather(*captures, return_exceptions=True), budget=5,
            )

    try:
        with TemporaryDirectory(prefix="pex-opencode-relay-") as ipc:
            socket = Path(ipc) / "relay.sock"
            try:
                server = await await_with_budget(
                    lambda: relay.listen(socket), budget=limits["deadline"] - time.perf_counter(),
                )
                bootstrap = (
                    "import sys;sys.path.insert(0,'/worker-runtime');"
                    "from benchmarks.opencode_worker import main;main()"
                )
                command = ["/usr/bin/python3", "-I", "-B", "-c", bootstrap,
                           "--model", model, "--deadline", str(limits["deadline"]),
                           "--max-followups", str(limits["max_followups"])]
                supervised = row["condition"] == "pex"
                if supervised:
                    command.append("--supervised")
                command = worker_runtime_relay_command(workspace, command, socket, runtime)
                with (control / "stdout.json").open("xb") as stdout, (
                    control / "stderr.txt"
                ).open("xb") as stderr:
                    async def spawn():
                        nonlocal process
                        process = await asyncio.create_subprocess_exec(
                            *command, stdin=asyncio.subprocess.DEVNULL,
                            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                            start_new_session=True, env={"PATH": "/usr/bin:/bin"},
                        )
                        return process

                    process = await await_with_budget(
                        spawn, budget=limits["deadline"] - time.perf_counter(),
                    )
                    captures = [asyncio.create_task(capture(process.stdout, stdout)),
                                asyncio.create_task(capture(process.stderr, stderr)),
                                asyncio.create_task(process.wait())]
                    try:
                        await await_with_budget(
                            lambda: asyncio.gather(*captures),
                            budget=limits["deadline"] - time.perf_counter(),
                        )
                    finally:
                        try:
                            await reap()
                        finally:
                            try:
                                await settle_captures()
                            finally:
                                stdout.flush()
                                stderr.flush()
                if process.returncode != 0:
                    raise RuntimeError("isolated worker exited unsuccessfully")
                raw = (control / "stdout.json").read_bytes()
                observation = worker_observation(
                    raw, supervised=supervised, max_followups=limits["max_followups"],
                )
                if not relay.audit or any(item["status"] != "completed" for item in relay.audit):
                    raise ValueError("worker model attempts are incomplete or uncertain")
                if supervised and (len(relay.review_audit) != len(observation["turns"])
                                   or any(item["status"] != "completed"
                                          or item["vendor_session_id"] != observation["turns"][0][
                                              "session_id"
                                          ] for item in relay.review_audit)):
                    raise ValueError("worker review attempts are incomplete or uncertain")
                result["worker_observation"] = observation
                result["stdout_sha256"] = hashlib.sha256(raw).hexdigest()
            finally:
                if server is not None:
                    server.close()
                try:
                    await reap()
                finally:
                    try:
                        await settle_captures()
                    finally:
                        try:
                            await await_with_budget(relay.close_active, budget=5)
                        finally:
                            if server is not None:
                                await await_with_budget(server.wait_closed, budget=5)
        if time.perf_counter() >= limits["deadline"]:
            raise TimeoutError("attempt exhausted the shared task deadline")
        if runner.benchmark_sha256() != reservation.get("benchmark_sha256", ""):
            raise ValueError("benchmark sources changed during worker execution")
        if measure_profile(runtime, model=model) != profile:
            raise ValueError("worker runtime changed during execution")
        result["workspace_snapshot_sha256"] = boundary.workspace_manifest_sha256(
            workspace, complete=True,
        )
        result["stderr_sha256"] = boundary.sha256_file(control / "stderr.txt", max_bytes=MAX_OUTPUT)
        if time.perf_counter() >= limits["deadline"]:
            raise TimeoutError("completion capture exhausted the shared task deadline")
        result["status"] = "worker_completed_unscored"
    except BaseException as error:
        result["error_type"] = type(error).__name__
        raise
    finally:
        result["elapsed_after_admission_seconds"] = time.perf_counter() - started
        result["model_attempts"] = relay.audit
        result["review_attempts"] = relay.review_audit
        with (control / "outcome.json").open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(result, sort_keys=True, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    return result
