import asyncio

import pytest

from benchmarks import opencode_session
from benchmarks.opencode_cli import CliTurn


@pytest.fixture
def execution(tmp_path, monkeypatch):
    clock = [10.0]
    calls = []

    async def execute(**kwargs):
        calls.append(kwargs)
        clock[0] += 1
        return CliTurn("vendor", ("Worker output",), 3, "a" * 64, 100)

    monkeypatch.setattr(opencode_session, "monotonic", lambda: clock[0])
    monkeypatch.setattr(opencode_session, "run_turn", execute)
    arguments = dict(
        executable=tmp_path / "opencode", workspace=tmp_path, model="controlled/pinned",
        prompt="Original public task", environment={}, log_directory=tmp_path, deadline=20.0,
    )
    return arguments, calls, clock


async def test_baseline_runs_one_turn_without_review(execution):
    arguments, calls, _ = execution
    result = await opencode_session.run_session(**arguments)
    assert len(calls) == len(result.turns) == 1
    assert result.actions == result.outgoing_messages == ()
    assert calls[0]["deadline"] == 20
    assert calls[0]["session_id"] is None


async def test_repairs_keep_original_session_and_shared_deadline(execution):
    arguments, calls, clock = execution
    observed = []

    async def review(turns):
        observed.append(turns)
        clock[0] += 2
        return {"type": "SEND_NUDGE", "payload": {"text": "Exact repair instruction"}} if (
            len(turns) == 1
        ) else {"type": "NOOP"}

    result = await opencode_session.run_session(**arguments, review=review)
    assert result.actions == ("SEND_NUDGE", "NOOP")
    assert result.outgoing_messages == ("Exact repair instruction",)
    assert [call["session_id"] for call in calls] == [None, "vendor"]
    assert [call["deadline"] for call in calls] == [20, 20]
    assert calls[1]["prompt"] == result.outgoing_messages[0]
    assert calls[0]["stdout_path"] != calls[1]["stdout_path"]
    assert tuple(len(turns) for turns in observed) == (1, 2)


async def test_review_that_returns_after_deadline_cannot_launch_repair(execution):
    arguments, calls, clock = execution

    async def review(turns):
        clock[0] = 21
        return {"type": "SEND_NUDGE", "payload": {"text": "Repair"}}

    with pytest.raises(TimeoutError, match="shared task deadline"):
        await opencode_session.run_session(**arguments, review=review)
    assert len(calls) == 1


async def test_review_timeout_cancels_pending_review(execution):
    arguments, calls, _ = execution
    arguments["deadline"] = 11.02
    cancelled = []

    async def review(turns):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    async def check():
        with pytest.raises(TimeoutError):
            await opencode_session.run_session(**arguments, review=review)

    await asyncio.wait_for(check(), timeout=1)
    assert cancelled == [True]
    assert len(calls) == 1


async def test_followup_limit_records_refusal_without_sending(execution):
    arguments, calls, _ = execution

    async def review(turns):
        return {"type": "REQUEST_VERIFICATION", "payload": {"text": "Verify public test"}}

    result = await opencode_session.run_session(**arguments, review=review, max_followups=0)
    assert result.followup_limit_reached
    assert result.actions == ("REQUEST_VERIFICATION",)
    assert result.outgoing_messages == ()
    assert len(calls) == 1


@pytest.mark.parametrize("decision", [None, {}, {"type": "MOVE_SESSION"},
                                     {"type": "SEND_NUDGE", "payload": {"text": " "}},
                                     {"type": "CONTINUE_SESSION", "payload": {"text": "a\x00"}}])
async def test_unsupported_or_unusable_actions_never_launch_repair(execution, decision):
    arguments, calls, _ = execution

    async def review(turns):
        return decision

    with pytest.raises(ValueError):
        await opencode_session.run_session(**arguments, review=review)
    assert len(calls) == 1
