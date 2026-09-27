import asyncio
import base64
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from benchmarks import opencode_executor as executor
from benchmarks.opencode_cli import completed_turn
from benchmarks.opencode_executor import worker_observation


def packet(vendor="vendor"):
    events = [{"type": kind, "sessionID": vendor, "part": {
        "sessionID": vendor, "messageID": "message", **extra,
    }} for kind, extra in (("step_start", {}), ("step_finish", {"reason": "stop"}))]
    raw = b"\n".join(json.dumps(row).encode() for row in events) + b"\n"
    turn = completed_turn(raw, exit_code=0)
    return {"schema": "pex.opencode-worker-output.v1", "turns": [{
        "session_id": vendor, "stdout_sha256": turn.stdout_sha256,
        "stdout_bytes": turn.stdout_bytes, "jsonl_base64": base64.b64encode(raw).decode(),
    }], "actions": [], "followups": [], "followup_limit_reached": False}


def test_export_requires_exact_natural_stop_hash_and_baseline_parity():
    value = packet()
    result = worker_observation(json.dumps(value).encode(), supervised=False, max_followups=0)
    assert result["turns"][0]["session_id"] == "vendor"
    value["turns"][0]["stdout_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="natural-stop receipt"):
        worker_observation(json.dumps(value).encode(), supervised=False, max_followups=0)


@pytest.mark.parametrize("mutation", ["baseline_review", "missing_review", "invalid_action"])
def test_export_cannot_invent_supervision_or_omit_review_lineage(mutation):
    value = packet()
    supervised = mutation != "baseline_review"
    if mutation == "baseline_review":
        value["actions"] = ["NOOP"]
    elif mutation == "invalid_action":
        value["actions"] = ["MOVE_SESSION"]
    with pytest.raises(ValueError):
        worker_observation(json.dumps(value).encode(), supervised=supervised, max_followups=0)


@pytest.mark.parametrize("action,flag,capacity", [
    ("SEND_NUDGE", False, 0), ("SEND_NUDGE", True, 1), ("NOOP", True, 0),
])
def test_terminal_review_requires_consistent_capacity(action, flag, capacity):
    value = packet()
    value["actions"] = [action]
    value["followup_limit_reached"] = flag
    with pytest.raises(ValueError, match="follow-up capacity"):
        worker_observation(json.dumps(value).encode(), supervised=True, max_followups=capacity)


@pytest.mark.parametrize("action,flag", [("NOOP", False), ("SEND_NUDGE", True)])
def test_terminal_review_accepts_natural_stop_or_exhausted_zero_capacity(action, flag):
    value = packet()
    value["actions"] = [action]
    value["followup_limit_reached"] = flag
    worker_observation(json.dumps(value).encode(), supervised=True, max_followups=0)


@pytest.mark.parametrize("mode", ["success", "late_spawn", "reap_failure"])
async def test_controller_retains_outcome_and_owns_even_a_late_spawn(
    tmp_path, monkeypatch, mode,
):
    late_spawn = mode != "success"
    monkeypatch.setattr(executor.sys, "platform", "linux")
    monkeypatch.setattr(executor.signal, "SIGKILL", 9, raising=False)
    root = tmp_path / "experiment"
    (root / "controller").mkdir(parents=True)
    flags = {"killed": False, "closed": False}
    stdout, stderr = asyncio.StreamReader(), asyncio.StreamReader()
    stdout.feed_data(json.dumps(packet()).encode())
    stdout.feed_eof()
    stderr.feed_eof()
    process = SimpleNamespace(pid=123, returncode=None if late_spawn else 0,
                              stdout=stdout, stderr=stderr)

    async def wait():
        if mode == "reap_failure":
            raise RuntimeError("reap failed")
        return process.returncode

    process.wait = wait

    def kill(pid, sig):
        assert pid == process.pid
        flags["killed"] = True
        if mode != "reap_failure":
            process.returncode = -9

    monkeypatch.setattr(executor.os, "killpg", kill, raising=False)

    async def spawn(*args, **options):
        assert options["env"] == {"PATH": "/usr/bin:/bin"}
        if late_spawn:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
        return process

    monkeypatch.setattr(executor.asyncio, "create_subprocess_exec", spawn)
    handlers_closed = asyncio.Event()

    async def wait_closed():
        await handlers_closed.wait()

    async def close_active():
        handlers_closed.set()

    server = SimpleNamespace(wait_closed=AsyncMock(side_effect=wait_closed))

    def close():
        flags["closed"] = True

    server.close = close
    relay = SimpleNamespace(
        audit=[{"status": "completed"}], review_audit=[],
        close_active=AsyncMock(side_effect=close_active),
        listen=AsyncMock(return_value=server),
    )
    reservation = {"entry": {"workspace": "a" * 64, "condition": "baseline"}}
    monkeypatch.setattr(executor, "measure_profile", lambda *a, **k: {"model": "pinned"})
    monkeypatch.setattr(executor, "admit_opencode_relay", lambda *a, **k: (
        relay, reservation, {"deadline": time.perf_counter() + (0.01 if late_spawn else 10),
                             "max_followups": 0},
    ))
    monkeypatch.setattr(executor, "worker_runtime_relay_command", lambda *args: ["test-worker"])
    options = dict(index=0, expected_plan_sha256="b" * 64, runtime=tmp_path / "runtime",
                   model="pinned", backend=lambda _: None, review=lambda *_: None)
    async def exercise():
        if late_spawn:
            with pytest.raises(RuntimeError if mode == "reap_failure" else TimeoutError):
                await executor.execute_attempt(root, **options)
        else:
            result = await executor.execute_attempt(root, **options)
            assert result["status"] == "worker_completed_unscored"
            assert not result["quality_measured"] and not result["presentation_eligible"]

    await asyncio.wait_for(exercise(), timeout=1)
    assert flags["closed"] and flags["killed"] == late_spawn
    saved = json.loads((root / "controller" / ("run-" + "a" * 64) / "outcome.json").read_text())
    assert saved["status"] == ("failed_uncertain" if late_spawn else "worker_completed_unscored")
    assert saved["model_attempts"] == relay.audit
    relay.close_active.assert_awaited_once()
