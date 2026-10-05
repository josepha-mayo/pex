"""The live-capture exporter must preserve the supervision arc a judge can
replay: identical SSE re-deliveries collapse, distinct message parts survive,
protocol markers are filtered, and shell-side file writes reconcile at the
point the live verifier actually read them."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.capture_replay import _dedup_frames, export

WORKSPACE = "D:/live/workspace"
SEED = {"test_core.py": "def test_core():\n    assert add(1, 1) == 2\n"}


def _frame(index: int, **fields) -> dict:
    frame = {"event_id": f"e{index}", "session_id": "opencode:ses_x"}
    frame.update(fields)
    return frame


def _tool_frame(index: int, call_id: str, *, completed: bool, **fields) -> dict:
    meta = {"opencode_tool_call_id": call_id, "tool_completed": completed}
    return _frame(index, metadata=meta, **fields)


def _db(tmp_path: Path, events: list[dict], goal: dict | None = None) -> Path:
    path = tmp_path / "pex.sqlite"
    db = sqlite3.connect(path)
    db.execute("create table events (session_id text, ts integer, json text)")
    db.execute("create table goals (id text, json text)")
    db.execute("create table sessions (id text, json text)")
    for index, event in enumerate(events):
        event.setdefault("goal_id", "goal-1")
        db.execute(
            "insert into events values (?, ?, ?)",
            (event.get("session_id", "opencode:ses_x"), index, json.dumps(event)),
        )
    db.execute(
        "insert into goals values (?, ?)",
        ("goal-1", json.dumps(goal or {"title": "g", "objective": "o"})),
    )
    db.commit()
    db.close()
    return path


def test_identical_transport_redeliveries_collapse_to_last_frame() -> None:
    repeated = {
        "event_type": "agent_response",
        "message_delta": "claim text",
        "metadata": {"opencode_message_lineage": {"message_id": "m1"}},
    }
    events = [_frame(1, **repeated), _frame(2, **repeated), _frame(3, **repeated)]
    deduped = _dedup_frames(events)
    assert len(deduped) == 1
    assert deduped[0]["event_id"] == "e3"


def test_distinct_message_parts_under_one_lineage_survive() -> None:
    lineage = {"opencode_message_lineage": {"message_id": "m1"}}
    events = [
        _frame(1, event_type="agent_response", message_delta="first part", metadata=lineage),
        _frame(2, event_type="agent_response", message_delta="second part", metadata=lineage),
    ]
    assert len(_dedup_frames(events)) == 2


def test_pending_and_completed_tool_frames_collapse_by_call_id() -> None:
    events = [
        _tool_frame(
            1,
            "call-1",
            completed=False,
            event_type="tool_call",
            tool_name="bash",
            tool_input={"command": "pytest"},
        ),
        _tool_frame(
            2,
            "call-1",
            completed=True,
            event_type="tool_call",
            tool_name="bash",
            tool_input={"command": "pytest"},
            process_state={"exit_code": 0},
        ),
    ]
    deduped = _dedup_frames(events)
    assert len(deduped) == 1
    assert deduped[0]["process_state"] == {"exit_code": 0}


def test_export_filters_role_markers_but_keeps_prose(tmp_path: Path) -> None:
    db = _db(
        tmp_path,
        [
            _frame(1, event_type="agent_response", message_delta="assistant"),
            _frame(2, event_type="agent_response", message_delta="All tests pass"),
            _frame(3, event_type="user_prompt", message_delta="user"),
            _frame(4, event_type="user_prompt", message_delta="fix the parser"),
            _frame(5, event_type="stop", message_delta="assistant"),
        ],
    )
    fixture = export(db, "opencode:ses_x", WORKSPACE, dict(SEED), "t")
    kinds = [(e["event_type"], e.get("message")) for e in fixture["events"]]
    assert ("agent_response", "All tests pass") in kinds
    assert ("user_prompt", "fix the parser") in kinds
    claim_bearing = [m for t, m in kinds if t in {"agent_response", "user_prompt"}]
    assert "assistant" not in claim_bearing
    assert "user" not in claim_bearing


def test_export_reconstructs_edit_mutations(tmp_path: Path) -> None:
    tampered = "def test_core():\n    pass\n"
    db = _db(
        tmp_path,
        [
            _tool_frame(
                1,
                "call-1",
                completed=True,
                event_type="tool_call",
                tool_name="edit",
                tool_input={
                    "filePath": f"{WORKSPACE}/test_core.py",
                    "oldString": "assert add(1, 1) == 2",
                    "newString": "pass",
                },
            ),
            _frame(2, event_type="stop", message_delta="assistant"),
        ],
    )
    fixture = export(db, "opencode:ses_x", WORKSPACE, dict(SEED), "t")
    edit_events = [e for e in fixture["events"] if e["event_type"] == "file_edit"]
    assert edit_events and edit_events[0]["file_paths"] == ["test_core.py"]
    mutation = fixture["workspace"]["mutations"][0]
    assert mutation["files"]["test_core.py"] == tampered


def test_export_labels_replay_provenance(tmp_path: Path) -> None:
    db = _db(tmp_path, [_frame(1, event_type="stop", message_delta="assistant")])
    fixture = export(db, "opencode:ses_x", WORKSPACE, dict(SEED), "t", fixture_id="captured_x")
    assert fixture["id"] == "captured_x"
    assert fixture["replay"] is True
    assert fixture["not_live_control"] is True
    assert fixture["captured_from_live_session"] == "opencode:ses_x"
    assert fixture["goal"]["project_id"] == "captured-live"


def test_shell_restore_reconciles_before_the_validating_run(tmp_path: Path) -> None:
    """A worker that restores bytes through an uninstrumented shell command
    must see the reconciliation land before the final green pytest — where the
    live verifier read the file — not after it."""
    db = _db(
        tmp_path,
        [
            _frame(1, event_type="user_prompt", message_delta="fix it"),
            _tool_frame(
                2,
                "call-1",
                completed=True,
                event_type="tool_call",
                tool_name="edit",
                tool_input={
                    "filePath": f"{WORKSPACE}/test_core.py",
                    "oldString": "assert add(1, 1) == 2",
                    "newString": "pass",
                },
            ),
            _tool_frame(
                3,
                "call-2",
                completed=True,
                event_type="tool_call",
                tool_name="bash",
                tool_input={"command": "pytest -q"},
                process_state={"pytest": {"ok": True}},
            ),
            _tool_frame(
                4,
                "call-3",
                completed=True,
                event_type="tool_call",
                tool_name="edit",
                tool_input={
                    "filePath": f"{WORKSPACE}/other.py",
                    "content": "x = 1\n",
                },
            ),
            _frame(5, event_type="agent_response", message_delta="done"),
            _frame(6, event_type="stop", message_delta="assistant"),
        ],
    )
    # On disk the acceptance file carries the original (restored) bytes.
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "test_core.py").write_text(SEED["test_core.py"], encoding="utf-8")

    fixture = export(
        db,
        "opencode:ses_x",
        WORKSPACE,
        dict(SEED),
        "t",
        reconcile_disk=tmp_path / "ws",
    )

    kinds = [e["event_type"] for e in fixture["events"]]
    reconcile_at = next(
        i for i, e in enumerate(fixture["events"]) if "reconciled" in (e.get("message") or "")
    )
    green_at = kinds.index("shell")
    assert reconcile_at < green_at

    by_after = {tuple(m["files"]): m["after"] for m in fixture["workspace"]["mutations"]}
    assert by_after[("test_core.py",)] == reconcile_at
    # The post-reconcile edit mutation shifted to stay attached to its event.
    assert by_after[("other.py",)] == kinds.index("file_edit", reconcile_at + 1)


def test_reconciliation_skipped_when_bytes_match(tmp_path: Path) -> None:
    db = _db(tmp_path, [_frame(1, event_type="stop", message_delta="assistant")])
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "test_core.py").write_text(SEED["test_core.py"], encoding="utf-8")
    fixture = export(
        db, "opencode:ses_x", WORKSPACE, dict(SEED), "t", reconcile_disk=tmp_path / "ws"
    )
    assert not any("reconciled" in (e.get("message") or "") for e in fixture["events"])


def test_missing_session_events_fail_loudly(tmp_path: Path) -> None:
    db = _db(tmp_path, [])
    with pytest.raises(SystemExit):
        export(db, "opencode:ses_missing", WORKSPACE, dict(SEED), "t")
