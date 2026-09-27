import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from pex_protocol.enums import HarnessType
from pex_protocol.session import HarnessSession

from benchmarks import linux_sandbox, pex_attach


def _arguments(tmp_path):
    workspace = tmp_path / "worker"
    workspace.mkdir()
    session = HarnessSession(
        id="codex:offline", harness_type=HarnessType.CODEX,
        vendor_session_id="offline", project_id=str(workspace), cwd=str(workspace),
    )
    return {
        "task_md": "Write report.json.", "workspace": workspace,
        "session": session, "observed": {
            "files": [], "file_manifest": [],
            "public_workspace_sha256": hashlib.sha256(b"[]").hexdigest(),
        },
        "agent_messages": ["Done."], "goal_id": "public-offline",
        "control_dir": tmp_path / "private", "timeout": 10,
        "offline_runtime": tmp_path / "runtime",
    }


@pytest.mark.parametrize("inference", [False, True])
async def test_offline_child_rebinds_identity_and_rejects_inference(
    tmp_path, monkeypatch, inference,
):
    arguments = _arguments(tmp_path)
    captured = {}

    def command(workspace, runtime, control):
        captured["control"] = control
        assert workspace == arguments["workspace"]
        assert runtime == arguments["offline_runtime"]
        return ["/usr/bin/bwrap", "offline"]

    async def launch(*argv, **kwargs):
        assert argv == ("/usr/bin/bwrap", "offline")
        assert kwargs["env"] == {}
        control = captured["control"]
        request_bytes = (control / "request.json").read_bytes()
        payload = json.loads(request_bytes)
        assert payload["project_id"] == "/workspace"
        assert payload["session"]["project_id"] == "/workspace"
        assert payload["session"]["cwd"] == "/workspace"
        assert payload["session"]["id"] == arguments["session"].id
        response_bytes = json.dumps({
            "action": {"type": "NOOP", "session_id": payload["session"]["id"],
                       "goal_id": payload["goal_id"], "rationale": "No action needed."},
            "used_llm": inference,
            "diagnosis": "No action needed.",
        }).encode()
        (control / "response.json").write_bytes(response_bytes)
        captured.update(request=request_bytes, response=response_bytes)

        class Process:
            returncode = 0

            async def wait(self):
                return 0

        return Process()

    monkeypatch.setattr(linux_sandbox, "supervisor_command", command)
    monkeypatch.setattr(pex_attach.asyncio, "create_subprocess_exec", launch)
    if inference:
        with pytest.raises(RuntimeError, match="live inference"):
            await pex_attach._decide_out_of_process(**arguments)
    else:
        decision = await pex_attach._decide_out_of_process(**arguments)
        boundary = decision["execution_boundary"]
        assert boundary["request_sha256"] == hashlib.sha256(captured["request"]).hexdigest()
        assert boundary["response_sha256"] == hashlib.sha256(captured["response"]).hexdigest()
        assert pex_attach._audit(decision, arguments["observed"], "Task", 1)[
            "execution_boundary"
        ] == boundary
    assert arguments["session"].cwd == str(arguments["workspace"])


@pytest.mark.parametrize("field", ["pytest", "controller_verification"])
async def test_offline_child_does_not_rewrite_host_test_receipts(tmp_path, monkeypatch, field):
    arguments = _arguments(tmp_path)
    observed = arguments["observed"]
    observed["pytest"] = {"ok": True, "exit_code": 0, "output": "1 passed"}
    # The real receipt has additional integrity constraints. Rebinding must
    # refuse even a structurally accepted receipt before process dispatch.
    if field == "controller_verification":
        monkeypatch.setattr(pex_attach, "_public_observation", lambda value: value)
        observed[field] = {"command": "host-python -m pytest"}

    async def forbidden_launch(*args, **kwargs):
        pytest.fail("host-bound evidence was dispatched into the sandbox")

    monkeypatch.setattr(pex_attach.asyncio, "create_subprocess_exec", forbidden_launch)
    with pytest.raises(RuntimeError, match="host-executed test evidence"):
        await pex_attach._decide_out_of_process(**arguments)


async def test_offline_supervision_selects_isolated_public_test_execution(tmp_path, monkeypatch):
    arguments = _arguments(tmp_path)

    def observe(workspace, fingerprint, *, isolated_tests, deadline):
        assert workspace == arguments["workspace"]
        assert fingerprint == "a" * 64
        assert isolated_tests is True
        assert deadline > 0
        raise RuntimeError("observation boundary selected")

    monkeypatch.setattr(pex_attach, "_observe_controlled_workspace", observe)
    with pytest.raises(RuntimeError, match="observation boundary selected"):
        await pex_attach.supervise_isolated_codex(
            object(), arguments["session"], arguments["workspace"], arguments["task_md"],
            store_path=tmp_path / "private" / "store.sqlite",
            public_test_sha256="a" * 64, offline_runtime=Path("/runtime"),
        )


@pytest.mark.parametrize("stalled_stage", ["delivery", "completion"])
async def test_supervision_aborts_stalled_followup_at_shared_deadline(
    tmp_path, monkeypatch, stalled_stage,
):
    arguments = _arguments(tmp_path)
    cancelled = asyncio.Event()
    dispatches = []

    async def decision(**kwargs):
        return {
            "action": {"type": "SEND_NUDGE", "payload": {"text": "Verify the report."}},
            "diagnosis": "The report is missing.", "used_llm": False,
        }

    async def stall():
        try:
            await asyncio.sleep(1)
            pytest.fail("follow-up ran beyond the shared task deadline")
        finally:
            cancelled.set()

    class Adapter:
        isolated_agent_messages = []
        last_turn_id = "initial-turn"

        async def send_message(self, session, text):
            dispatches.append((session.id, text))
            if stalled_stage == "delivery":
                await stall()
            self.last_turn_id = "followup-turn"
            return True

        async def wait_for_turn_completion(self, session, turn_id, *, timeout):
            assert turn_id == "followup-turn"
            assert 0 < timeout <= 0.1
            await stall()

    monkeypatch.setattr(
        pex_attach, "_observe_controlled_workspace", lambda *a, **kw: arguments["observed"],
    )
    monkeypatch.setattr(pex_attach, "_decide_out_of_process", decision)
    with pytest.raises(TimeoutError):
        await pex_attach.supervise_isolated_codex(
            Adapter(), arguments["session"], arguments["workspace"], arguments["task_md"],
            store_path=tmp_path / "private" / "store.sqlite",
            turn_timeout=0.1, decision_timeout=0.1,
        )
    assert cancelled.is_set()
    assert dispatches == [(arguments["session"].id, "Verify the report.")]


async def test_expired_supervisor_decision_cannot_dispatch_followup(tmp_path, monkeypatch):
    arguments = _arguments(tmp_path)
    clock = [0.0]

    async def decision(**kwargs):
        clock[0] = 2.0
        return {
            "action": {"type": "SEND_NUDGE", "payload": {"text": "Too late."}},
            "diagnosis": "The report is missing.", "used_llm": False,
        }

    class Adapter:
        isolated_agent_messages = []

        async def send_message(self, *args):
            pytest.fail("an expired decision dispatched a worker turn")

    monkeypatch.setattr(pex_attach.time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(
        pex_attach, "_observe_controlled_workspace", lambda *a, **kw: arguments["observed"],
    )
    monkeypatch.setattr(pex_attach, "_decide_out_of_process", decision)
    with pytest.raises(TimeoutError, match="shared worker-plus-supervisor task budget"):
        await pex_attach.supervise_isolated_codex(
            Adapter(), arguments["session"], arguments["workspace"], arguments["task_md"],
            store_path=tmp_path / "private" / "store.sqlite",
            turn_timeout=1, decision_timeout=1,
        )


async def test_supervisor_decision_cap_is_clipped_to_remaining_task_time(tmp_path, monkeypatch):
    arguments = _arguments(tmp_path)
    requested_timeouts = []

    async def decision(**kwargs):
        requested_timeouts.append(kwargs["timeout"])
        return {
            "action": {"type": "NOOP"}, "diagnosis": "No correction needed.",
            "used_llm": False,
        }

    class Adapter:
        isolated_agent_messages = []

    monkeypatch.setattr(
        pex_attach, "_observe_controlled_workspace", lambda *a, **kw: arguments["observed"],
    )
    monkeypatch.setattr(pex_attach, "_decide_out_of_process", decision)
    result = await pex_attach.supervise_isolated_codex(
        Adapter(), arguments["session"], arguments["workspace"], arguments["task_md"],
        store_path=tmp_path / "private" / "store.sqlite",
        turn_timeout=1, decision_timeout=180,
    )
    assert len(requested_timeouts) == 1
    assert 0 < requested_timeouts[0] <= 1
    assert result["followups"] == 0
