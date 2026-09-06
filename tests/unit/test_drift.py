from __future__ import annotations

from datetime import UTC, datetime

from pex_protocol.enums import EventPhase, EventType, HarnessType
from pex_protocol.session import HarnessEvent
from pex_supervisor.drift import duplicate_sibling_work


def _event(**kwargs) -> HarnessEvent:
    return HarnessEvent(
        event_id=kwargs.pop("event_id", "e1"),
        ts=kwargs.pop("ts", datetime.now(UTC)),
        harness_type=kwargs.pop("harness_type", HarnessType.CURSOR),
        session_id=kwargs.pop("session_id", "cursor:one"),
        event_type=kwargs.pop("event_type", EventType.FILE_EDIT),
        phase=kwargs.pop("phase", EventPhase.DURING),
        **kwargs,
    )


def test_duplicate_sibling_work_matches_overlapping_path():
    prior = _event(session_id="cursor:one", file_paths=["src/parser.py"])
    current = _event(
        event_id="e2",
        session_id="codex:two",
        harness_type=HarnessType.CODEX,
        file_paths=["src\\parser.py"],
    )
    found = duplicate_sibling_work(current, [("cursor:one", "cursor", [prior])])
    assert found == {
        "sibling_session_id": "cursor:one",
        "harness": "cursor",
        "path": "src/parser.py",
    }


def test_same_basename_in_different_directories_is_not_overlap():
    prior = _event(session_id="cursor:one", file_paths=["src/parser.py"])
    current = _event(session_id="codex:two", file_paths=["lib/parser.py"])
    assert duplicate_sibling_work(current, [("cursor:one", "cursor", [prior])]) is None


def test_duplicate_sibling_work_matches_identical_non_test_command():
    prior = _event(
        event_type=EventType.SHELL,
        session_id="cursor:one",
        command="python inspect_parser.py",
    )
    current = _event(
        event_id="e2",
        event_type=EventType.SHELL,
        session_id="codex:two",
        harness_type=HarnessType.CODEX,
        command="python inspect_parser.py",
    )
    found = duplicate_sibling_work(current, [("cursor:one", "cursor", [prior])])
    assert found is not None
    assert found["command"] == "python inspect_parser.py"
    assert found["harness"] == "cursor"


def test_routine_tests_are_not_duplicate_commands():
    prior = _event(
        event_type=EventType.SHELL,
        session_id="cursor:one",
        command="pytest -q",
    )
    current = _event(
        event_id="e2",
        event_type=EventType.SHELL,
        session_id="codex:two",
        harness_type=HarnessType.CODEX,
        command="pytest -q",
    )
    assert duplicate_sibling_work(current, [("cursor:one", "cursor", [prior])]) is None
