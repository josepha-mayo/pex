"""Protocol identity and failure fences for the isolated Codex worker."""

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from benchmarks import codex_worker


def response(identity, result):
    return {"id": identity, "result": result}


def stopped(*, session="session", identity="turn", status="completed"):
    return {"method": "turn/completed", "params": {
        "threadId": session, "turn": {"id": identity, "status": status},
    }}


@pytest.mark.parametrize("terminal", [stopped(), stopped(session="wrong"),
                                      stopped(identity="wrong"), stopped(status="failed"),
                                      {"id": 99, "method": "approve", "params": {}},
                                      "deadline-after-thread", "repair-at-cap", "noop-at-cap",
                                      "repair-then-noop", "review-failed"])
async def test_worker_matches_terminal_receipts_and_reaps(tmp_path, monkeypatch, terminal):
    rows = [response(1, {}), response(2, {"thread": {"id": "session"}}),
            response(3, {"turn": {"id": "turn"}}), terminal]
    sent = []
    observed = {}
    review_modes = {"repair-at-cap", "noop-at-cap", "repair-then-noop", "review-failed"}
    supervised = isinstance(terminal, str) and terminal in review_modes
    reviews = []
    if supervised:
        rows[-1:] = [{"method": "item/completed", "params": {
            "threadId": "session", "turnId": "turn", "item": {
                "type": "agentMessage", "text": "First completion",
            },
        }}, stopped()]
        if terminal == "repair-then-noop":
            rows.extend([response(4, {"turn": {"id": "turn2"}}), stopped(identity="turn2")])

    def review(path, **kwargs):
        reviews.append(kwargs)
        if terminal == "review-failed":
            raise ValueError("uncertain review")
        if terminal == "noop-at-cap" or len(reviews) == 2:
            return {"type": "NOOP"}
        return {"type": "SEND_NUDGE", "payload": {"text": "Verify public tests"}}
    clock_reads_after_thread = []

    def clock():
        if clock_reads_after_thread:
            clock_reads_after_thread.append(True)
            return 10 if len(clock_reads_after_thread) > 2 else 0
        return 0

    class Reader:
        async def readline(self):
            value = rows.pop(0) if rows else None
            if terminal == "deadline-after-thread" and value and value.get("id") == 2:
                clock_reads_after_thread.append(True)
            return json.dumps(value).encode() + b"\n" if value else b""

    class Writer:
        def write(self, raw):
            sent.append(json.loads(raw))

        async def drain(self):
            pass

    class Process:
        stdout = Reader()
        stdin = Writer()
        returncode = None

        def terminate(self):
            self.returncode = 0

        async def wait(self):
            return self.returncode

    process = Process()

    async def launch(*args, **kwargs):
        observed.update(kwargs)
        return process

    monkeypatch.setattr(codex_worker, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    if supervised:
        monkeypatch.setattr(codex_worker, "review_request", review)
    if terminal == "deadline-after-thread":
        monkeypatch.setattr(codex_worker, "monotonic", clock)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run = codex_worker.run_worker(executable=tmp_path / "codex", workspace=workspace,
                                  state_home=tmp_path / "state",
                                  socket_path=str(tmp_path / "relay"),
                                  model="pinned", prompts=["Public task"],
                                  supervised=supervised,
                                  max_followups=1 if terminal == "repair-then-noop" else 0,
                                  deadline=5 if terminal == "deadline-after-thread"
                                  else time.monotonic() + 5)
    if terminal == stopped():
        result = await run
        assert result["turns"] == [{"turn_id": "turn", "status": "completed", "messages": []}]
        assert result["quality_measured"] is False
    elif supervised and terminal != "review-failed":
        result = await run
        assert result["turns"][0]["messages"] == ["First completion"]
        assert reviews[0]["vendor_session_id"] == "session"
        assert reviews[0]["agent_messages"] == ("First completion",)
        assert reviews[0]["schema"] == "pex.codex-review.v1"
        assert result["followup_limit_reached"] is (terminal == "repair-at-cap")
        if terminal == "repair-then-noop":
            assert result["actions"] == ["SEND_NUDGE", "NOOP"]
            assert result["outgoing_messages"] == ["Verify public tests"]
            assert len(result["turns"]) == 2
        else:
            assert result["outgoing_messages"] == [] and len(result["turns"]) == 1
    elif terminal == "deadline-after-thread":
        with pytest.raises(TimeoutError):
            await run
    else:
        with pytest.raises(ValueError):
            await run
    assert process.returncode == 0
    assert set(observed["env"]) == {"PATH", "HOME", "CODEX_HOME", "NO_COLOR"}
    assert observed["env"]["CODEX_HOME"] == str(tmp_path / "state")
    expected = ["initialize", "initialized", "thread/start"]
    if terminal != "deadline-after-thread":
        expected.append("turn/start")
    if terminal == "repair-then-noop":
        expected.append("turn/start")
    assert [row["method"] for row in sent] == expected


@pytest.mark.parametrize("port,model", [(True, "pinned"), (0, "pinned"),
                                      (1, ""), (1, "with space")])
def test_provider_configuration_rejects_unbounded_values(port, model):
    with pytest.raises(ValueError):
        codex_worker.provider_settings(port, model)
