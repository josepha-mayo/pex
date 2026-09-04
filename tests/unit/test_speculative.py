from __future__ import annotations

from datetime import UTC, datetime

from pex_bridge.speculative import (
    cheap_competing_approaches,
    compare_probe_results,
    probe_already_running,
    probe_instructions,
    probe_result_from_stop,
)
from pex_protocol.enums import DecisionSource, DecisionStatus, EventType, HarnessType
from pex_protocol.goal import Decision
from pex_protocol.session import HarnessEvent, HarnessSession


def _decision(statement: str, *, kind: str = "unresolved_question") -> Decision:
    return Decision(
        id=f"dec_{statement[:8]}",
        goal_id="goal_1",
        statement=statement,
        source=DecisionSource.HUMAN,
        status=DecisionStatus.UNCERTAIN,
        created_at=datetime.now(UTC),
        metadata={"kind": kind},
    )


def test_cheap_competing_approaches_need_two_short_unresolved_questions():
    rows = [
        _decision("Try an in-memory index first"),
        _decision("Try a sqlite index first"),
    ]
    assert cheap_competing_approaches(rows) == [
        "Try an in-memory index first",
        "Try a sqlite index first",
    ]
    assert cheap_competing_approaches(rows[:1]) == []
    assert cheap_competing_approaches(
        [_decision("rejected", kind="rejected_approach"), *rows]
    ) == [
        "Try an in-memory index first",
        "Try a sqlite index first",
    ]
    huge = _decision("x" * 401)
    assert cheap_competing_approaches([rows[0], huge]) == []


def test_probe_instructions_are_bounded_and_specific():
    text = probe_instructions("Try sqlite")
    assert "Try sqlite" in text
    assert "at most 8 tool calls" in text
    assert not text.startswith("PEX:")


def test_compare_probe_results_prefers_passing_pytest():
    parent = {
        "session_id": "synthetic:a",
        "status": "uncertain",
        "pytest_ok": False,
        "approach": "in-memory",
        "role": "a",
    }
    child = {
        "session_id": "synthetic:b",
        "status": "supported",
        "pytest_ok": True,
        "approach": "sqlite",
        "role": "b",
    }
    compared = compare_probe_results(parent=parent, child=child)
    assert compared["winner"] == "b"
    assert compared["winner_session_id"] == "synthetic:b"
    assert compared["loser_session_id"] == "synthetic:a"
    tied = compare_probe_results(parent=parent, child=dict(parent, session_id="synthetic:b"))
    assert tied["winner"] == "tie"
    assert tied["winner_session_id"] is None


def test_probe_result_reads_pytest_from_recent_events():
    session = HarnessSession(
        id="synthetic:s1",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="s1",
        metadata={
            "speculative": {
                "pair_id": "p1",
                "role": "a",
                "approach": "sqlite",
                "sibling_session_id": "synthetic:s2",
            }
        },
    )
    event = HarnessEvent(
        event_id="e1",
        ts=datetime.now(UTC),
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:s1",
        event_type=EventType.SHELL,
        process_state={"pytest": {"ok": True, "exit_code": 0}},
    )
    result = probe_result_from_stop(session, {"status": "supported"}, [event])
    assert result["pytest_ok"] is True
    assert result["approach"] == "sqlite"


def test_probe_already_running_sees_sibling_probe_metadata():
    current = HarnessSession(
        id="synthetic:s1",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="s1",
        goal_id="goal_1",
    )
    sibling = HarnessSession(
        id="synthetic:s2",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id="s2",
        goal_id="goal_1",
        metadata={"probe": True},
    )
    assert probe_already_running(
        [current, sibling], goal_id="goal_1", current_session_id=current.id
    )
    sibling.goal_id = "other"
    assert not probe_already_running(
        [current, sibling], goal_id="goal_1", current_session_id=current.id
    )
