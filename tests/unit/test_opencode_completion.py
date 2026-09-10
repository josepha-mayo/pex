import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from benchmarks.opencode_completion import QuietCompletionFence, completed_generation


@pytest.mark.parametrize("args,code", [(["--help"], 0), ([], 2), (["--run-name", "../outside"], 2)])
def test_live_runner_requires_explicit_valid_run_name_before_any_work(args, code):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/opencode_quiet_ten.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == code
    assert "usage:" in result.stdout + result.stderr


def messages():
    return [
        {"info": {"id": "u1", "sessionID": "s", "role": "user", "time": {"created": 1}}},
        {
            "info": {
                "id": "a1",
                "sessionID": "s",
                "role": "assistant",
                "parentID": "u1",
                "time": {"created": 2, "completed": 3},
                "finish": "stop",
            }
        },
    ]


@pytest.mark.parametrize("statuses", [{}, {"s": {"type": "idle"}}])
def test_current_completed_generation(statuses):
    assert completed_generation(messages(), statuses, "s") == ("u1", "a1")


def test_admitted_followup_missing_from_http_history_cannot_complete():
    assert completed_generation(messages(), {}, "s", minimum_user_count=2) is None


@pytest.mark.parametrize(
    "statuses",
    [
        None,
        [],
        {"s": None},
        {"s": {"type": "busy"}},
        {"s": {"type": "retry"}},
        {"s": {"type": "unknown"}},
    ],
)
def test_unavailable_or_nonidle_status_never_completes(statuses):
    assert completed_generation(messages(), statuses, "s") is None


def test_previous_success_does_not_complete_followup():
    rows = messages()
    rows.append({"info": {"id": "u2", "sessionID": "s", "role": "user", "time": {"created": 4}}})
    assert completed_generation(rows, {}, "s") is None
    rows.append(
        {
            "info": {
                "id": "a2",
                "sessionID": "s",
                "role": "assistant",
                "parentID": "u2",
                "time": {"created": 5},
            }
        }
    )
    assert completed_generation(rows, {}, "s") is None
    rows[-1]["info"].update(time={"created": 5, "completed": 6}, finish="stop")
    assert completed_generation(rows, {}, "s") == ("u2", "a2")


@pytest.mark.parametrize(
    "field,value",
    [
        ("parentID", "wrong"),
        ("sessionID", "other"),
        ("error", {}),
        ("error", {"name": "APIError"}),
        ("finish", "tool-calls"),
        ("finish", None),
        ("time", {"created": 2}),
        ("time", {"created": 2, "completed": 1}),
        ("time", {"created": 2, "completed": True}),
        ("time", {"created": 2, "completed": float("nan")}),
    ],
)
def test_invalid_latest_response(field, value):
    rows = messages()
    rows[-1]["info"][field] = value
    assert completed_generation(rows, {}, "s") is None


@pytest.mark.parametrize("rows", [None, [], [None], [{"info": None}]])
def test_malformed_messages(rows):
    assert completed_generation(rows, {}, "s") is None


def test_newer_incomplete_assistant_supersedes_finished_assistant():
    rows = messages()
    newer = deepcopy(rows[-1])
    newer["info"].update(id="a2", time={"created": 4})
    rows.append(newer)
    assert completed_generation(rows, {}, "s") is None


def observation(**changes):
    result = dict(
        now=0,
        generation=("u1", "a1"),
        event_ids=("e1",),
        followup_count=0,
        reviews_present=True,
        journal_complete=True,
    )
    result.update(changes)
    return result


def test_full_quiet_interval_required():
    fence = QuietCompletionFence()
    assert not fence.observe(**observation())
    assert not fence.observe(**observation(now=11))
    assert fence.observe(**observation(now=12))


@pytest.mark.parametrize(
    "changes",
    [
        {"generation": None},
        {"journal_complete": False},
        {"reviews_present": False},
        {"event_ids": ()},
        {"generation": ("u2", "a2")},
        {"event_ids": ("e1", "e2")},
        {"followup_count": 1},
    ],
)
def test_activity_resets_interval(changes):
    fence = QuietCompletionFence()
    assert not fence.observe(**observation())
    assert not fence.observe(**observation(now=11, **changes))
    assert not fence.observe(**observation(now=12))
    assert fence.observe(**observation(now=24))
