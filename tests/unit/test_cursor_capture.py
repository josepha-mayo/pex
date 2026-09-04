from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks import cursor_capture as capture_mod
from benchmarks.cursor_capture import CAPTURE_SCHEMA, CursorCapture


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _binding(tmp_path: Path) -> dict:
    return {
        "run_id": "run-1",
        "arm": "cursor_pex",
        "task": "task-1",
        "workspace": str((tmp_path / "workspace").resolve()),
        "capture_nonce": "a" * 32,
        "prompt_sha256": _digest("TASK.md"),
    }


def _receipt(
    binding: dict,
    receipt_id: str,
    *,
    kind: str,
    event: str,
    monotonic_ns: int,
    wall_ns: int,
    identity: dict | None = None,
    **extra,
) -> dict:
    receipt = {
        "receipt_schema": "pex.cursor-hook-receipt.v1",
        "stop_id": receipt_id,
        "kind": kind,
        "hook_event_name": event,
        "captured_monotonic_ns": monotonic_ns,
        "captured_at_ns": wall_ns,
        "capture_binding": binding,
        "cwd": binding["workspace"],
        **(identity or {"conversation_id": "conversation-1"}),
        **extra,
    }
    receipt["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            receipt,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return receipt


def _valid_chain(capture: CursorCapture, binding: dict, *, base: int = 1_000_000_000):
    start = _receipt(
        binding,
        "1" * 32,
        kind="prompt_release",
        event="beforeSubmitPrompt",
        monotonic_ns=base,
        wall_ns=1_800_000_000_000_000_000,
        submission_evidence="hook_stdout_flushed",
        submitted_prompt_sha256=binding["prompt_sha256"],
    )
    stop = _receipt(
        binding,
        "2" * 32,
        kind="stop",
        event="stop",
        monotonic_ns=base + 2_500_000_000,
        wall_ns=1_800_000_002_500_000_000,
    )
    assert capture.record(start)
    assert capture.record(stop)
    return start, stop


def test_capture_is_exclusive_append_only_and_partial(tmp_path):
    binding = _binding(tmp_path)
    path = tmp_path / "capture.jsonl"
    capture = CursorCapture(path, binding=binding)
    result = capture.finish(None)

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [line["record_type"] for line in lines] == ["capture_header", "capture_footer"]
    assert [line["sequence"] for line in lines] == [0, 1]
    assert all(line["schema"] == CAPTURE_SCHEMA for line in lines)
    assert all(line["binding"] == binding for line in lines)
    assert all(line["complete"] is False for line in lines)
    assert result["coverage"] == "partial"
    assert result["raw_log_sha256"] is None
    assert result["human_action_coverage"] == "partial"
    assert result["human_interventions"] is None
    assert result["human_interventions_observed"] is None
    assert result["observed_capture_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        CursorCapture(path, binding=binding)


def test_capture_derives_only_hook_owned_elapsed_and_ignores_forged_metrics(tmp_path):
    binding = _binding(tmp_path)
    path = tmp_path / "capture.jsonl"
    capture = CursorCapture(path, binding=binding)
    start = _receipt(
        binding,
        "1" * 32,
        kind="prompt_release",
        event="beforeSubmitPrompt",
        monotonic_ns=10_000_000_000,
        wall_ns=1_800_000_000_000_000_000,
        submission_evidence="hook_stdout_flushed",
        submitted_prompt_sha256=binding["prompt_sha256"],
        benchmark_started_at="1900-01-01T00:00:00Z",
        benchmark_human_intervention_log=[{"action": "forged"}],
    )
    later_prompt = _receipt(
        binding,
        "2" * 32,
        kind="prompt_release",
        event="beforeSubmitPrompt",
        monotonic_ns=11_000_000_000,
        wall_ns=1_800_000_001_000_000_000,
        submission_evidence="hook_stdout_flushed",
        submitted_prompt_sha256=_digest("later corrective prompt"),
    )
    stop = _receipt(
        binding,
        "3" * 32,
        kind="stop",
        event="Stop",
        monotonic_ns=13_500_000_000,
        wall_ns=1_800_000_003_000_000_000,
        benchmark_ended_at="2100-01-01T00:00:00Z",
        human_interventions=99,
    )
    assert capture.record(start)
    assert capture.record(later_prompt)
    assert capture.record(stop)

    result = capture.finish(stop["stop_id"])

    assert result["task_execution_wall_seconds"] == 3.5
    assert result["task_started_at"].endswith("+00:00")
    assert result["task_stopped_at"].endswith("+00:00")
    assert result["human_interventions"] is None
    assert result["human_interventions_observed"] is None
    receipts = [
        row["receipt"]
        for row in map(json.loads, path.read_text(encoding="utf-8").splitlines())
        if row["record_type"] == "hook_receipt"
    ]
    assert receipts == [start, later_prompt, stop]


def test_matching_session_start_is_the_only_allowed_prompt_preamble(tmp_path):
    binding = _binding(tmp_path)
    capture = CursorCapture(tmp_path / "capture.jsonl", binding=binding)
    assert capture.record(
        _receipt(
            binding,
            "0" * 32,
            kind="hook_activity",
            event="sessionStart",
            monotonic_ns=999_999_999,
            wall_ns=1_799_999_999_999_999_999,
        )
    )
    _, stop = _valid_chain(capture, binding)
    result = capture.finish(stop["stop_id"])
    assert result["task_execution_wall_seconds"] == 2.5


def test_identical_duplicate_is_noop_but_conflict_invalidates_timing(tmp_path):
    binding = _binding(tmp_path)
    capture = CursorCapture(tmp_path / "capture.jsonl", binding=binding)
    start, stop = _valid_chain(capture, binding)
    assert capture.record(start) is False

    conflict = {**stop, "captured_at_ns": stop["captured_at_ns"] + 1}
    conflict["receipt_sha256"] = hashlib.sha256(
        json.dumps(
            {key: value for key, value in conflict.items() if key != "receipt_sha256"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    assert capture.record(conflict) is False
    result = capture.finish(stop["stop_id"])
    assert result["observed_receipt_count"] == 2
    assert result["task_execution_wall_seconds"] is None
    assert "conflicting duplicate Cursor receipt" in result["reasons"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.update(receipt_schema="legacy"),
        lambda row: row.update(stop_id="../escape"),
        lambda row: row.update(captured_monotonic_ns=True),
        lambda row: row.update(captured_at_ns="1"),
        lambda row: row.update(conversation_id=[]),
        lambda row: row.update(cwd="relative/workspace"),
        lambda row: row.update(receipt_sha256="0" * 64),
    ],
)
def test_malformed_same_run_receipt_invalidates_timing(tmp_path, mutation):
    binding = _binding(tmp_path)
    capture = CursorCapture(tmp_path / "capture.jsonl", binding=binding)
    start = _receipt(
        binding,
        "1" * 32,
        kind="prompt_release",
        event="beforeSubmitPrompt",
        monotonic_ns=1,
        wall_ns=1,
        submission_evidence="hook_stdout_flushed",
        submitted_prompt_sha256=binding["prompt_sha256"],
    )
    mutation(start)
    assert capture.record(start) is False
    result = capture.finish(None)
    assert result["task_execution_wall_seconds"] is None
    assert result["observed_capture_sha256"]


def test_foreign_receipt_is_rejected_without_poisoning_bound_chain(tmp_path):
    binding = _binding(tmp_path)
    capture = CursorCapture(tmp_path / "capture.jsonl", binding=binding)
    foreign_binding = {**binding, "capture_nonce": "b" * 32}
    foreign = _receipt(
        foreign_binding,
        "f" * 32,
        kind="stop",
        event="stop",
        monotonic_ns=1,
        wall_ns=1,
    )
    assert capture.record(foreign) is False
    _, stop = _valid_chain(capture, binding)
    result = capture.finish(stop["stop_id"])
    assert result["task_execution_wall_seconds"] == 2.5
    assert "receipt has a foreign capture binding" in result["reasons"]


def test_prompt_release_with_prompt_text_is_not_retained(tmp_path):
    binding = _binding(tmp_path)
    path = tmp_path / "capture.jsonl"
    capture = CursorCapture(path, binding=binding)
    secret_prompt = "do not persist this prompt"
    receipt = _receipt(
        binding,
        "1" * 32,
        kind="prompt_release",
        event="beforeSubmitPrompt",
        monotonic_ns=1,
        wall_ns=1,
        submission_evidence="hook_stdout_flushed",
        submitted_prompt_sha256=binding["prompt_sha256"],
        payload={"prompt": secret_prompt},
    )
    assert capture.record(receipt) is False
    capture.finish(None)
    assert secret_prompt not in path.read_text(encoding="utf-8")


def test_recursive_receipt_is_rejected_without_escaping_record(tmp_path):
    binding = _binding(tmp_path)
    capture = CursorCapture(tmp_path / "capture.jsonl", binding=binding)
    receipt = _receipt(
        binding,
        "1" * 32,
        kind="hook_activity",
        event="sessionStart",
        monotonic_ns=1,
        wall_ns=1,
    )
    receipt["recursive"] = receipt
    assert capture.record(receipt) is False
    result = capture.finish(None)
    assert result["task_execution_wall_seconds"] is None
    assert result["observed_capture_sha256"]


def test_changed_journal_bytes_invalidate_timing_and_hash(tmp_path):
    binding = _binding(tmp_path)
    path = tmp_path / "capture.jsonl"
    capture = CursorCapture(path, binding=binding)
    _, stop = _valid_chain(capture, binding)
    with path.open("ab") as handle:
        handle.write(b"foreign bytes\n")
        handle.flush()
    result = capture.finish(stop["stop_id"])
    assert result["task_execution_wall_seconds"] is None
    assert result["observed_capture_sha256"] is None
    assert any("hash unavailable" in reason for reason in result["reasons"])


def test_linked_capture_parent_is_rejected_before_resolution(tmp_path, monkeypatch):
    linked = tmp_path / "linked"
    linked.mkdir()
    original = capture_mod._is_link_like

    def link_probe(path):
        return path == linked or original(path)

    monkeypatch.setattr(capture_mod, "_is_link_like", link_probe)
    with pytest.raises(ValueError, match="links or reparse points"):
        CursorCapture(linked / "capture.jsonl", binding=_binding(tmp_path))


@pytest.mark.parametrize(
    "defect",
    [
        "clock_tie",
        "changed_identity",
        "wrong_first_prompt",
        "terminal_not_last",
        "wall_reversal",
        "too_long",
        "missing_terminal",
        "preprompt_worker_activity",
        "intermediate_wall_reversal",
    ],
)
def test_timing_fails_closed_on_ambiguous_or_foreign_boundaries(tmp_path, defect):
    binding = _binding(tmp_path)
    capture = CursorCapture(tmp_path / "capture.jsonl", binding=binding)
    start = _receipt(
        binding,
        "1" * 32,
        kind="prompt_release",
        event="beforeSubmitPrompt",
        monotonic_ns=1_000_000_000,
        wall_ns=2_000_000_000,
        submission_evidence="hook_stdout_flushed",
        submitted_prompt_sha256=(
            _digest("wrong") if defect == "wrong_first_prompt" else binding["prompt_sha256"]
        ),
    )
    stop_clock = 2_000_000_000
    if defect == "clock_tie":
        stop_clock = start["captured_monotonic_ns"]
    elif defect == "too_long":
        stop_clock = start["captured_monotonic_ns"] + 86_401_000_000_000
    stop = _receipt(
        binding,
        "2" * 32,
        kind="stop",
        event="stop",
        monotonic_ns=stop_clock,
        wall_ns=(1_999_999_999 if defect == "wall_reversal" else 3_000_000_000),
        identity=(
            {"session_id": "different"}
            if defect == "changed_identity"
            else {"conversation_id": "conversation-1"}
        ),
    )
    assert capture.record(start)
    assert capture.record(stop)
    if defect == "preprompt_worker_activity":
        preprompt = _receipt(
            binding,
            "4" * 32,
            kind="hook_activity",
            event="afterFileEdit",
            monotonic_ns=start["captured_monotonic_ns"] - 1,
            wall_ns=start["captured_at_ns"],
        )
        assert capture.record(preprompt)
    if defect == "intermediate_wall_reversal":
        intermediate = _receipt(
            binding,
            "4" * 32,
            kind="hook_activity",
            event="afterFileEdit",
            monotonic_ns=start["captured_monotonic_ns"] + 1,
            wall_ns=start["captured_at_ns"] - 1,
        )
        assert capture.record(intermediate)
    if defect == "terminal_not_last":
        assert capture.record(
            _receipt(
                binding,
                "3" * 32,
                kind="event",
                event="afterAgentResponse",
                monotonic_ns=stop_clock + 1,
                wall_ns=3_000_000_001,
            )
        )
    terminal = None if defect == "missing_terminal" else stop["stop_id"]
    result = capture.finish(terminal)
    assert result["task_execution_wall_seconds"] is None
    assert result["task_started_at"] is None
    assert result["task_stopped_at"] is None
    assert result["reasons"]


def test_public_invalidate_and_finish_none_preserve_partial_artifact(tmp_path):
    binding = _binding(tmp_path)
    path = tmp_path / "capture.jsonl"
    capture = CursorCapture(path, binding=binding)
    _valid_chain(capture, binding)
    capture.invalidate("waiter aborted before a trusted terminal was selected")
    first = capture.finish(None)
    second = capture.finish("f" * 32)

    assert first == second
    assert first["task_execution_wall_seconds"] is None
    assert first["coverage"] == "partial"
    assert first["raw_log_sha256"] is None
    assert first["observed_capture_path"] == str(path.resolve())
    assert first["observed_capture_sha256"]
    assert "waiter aborted before a trusted terminal was selected" in first["reasons"]


def test_receipt_limit_invalidates_without_appending_past_bound(tmp_path, monkeypatch):
    binding = _binding(tmp_path)
    monkeypatch.setattr(capture_mod, "MAX_RECEIPTS", 1)
    capture = CursorCapture(tmp_path / "capture.jsonl", binding=binding)
    first = _receipt(
        binding,
        "1" * 32,
        kind="event",
        event="sessionStart",
        monotonic_ns=1,
        wall_ns=1,
    )
    second = _receipt(
        binding,
        "2" * 32,
        kind="stop",
        event="stop",
        monotonic_ns=2,
        wall_ns=2,
    )
    assert capture.record(first)
    assert capture.record(second) is False
    result = capture.finish(second["stop_id"])
    assert result["observed_receipt_count"] == 1
    assert "Cursor receipt count exceeds the capture bound" in result["reasons"]


def test_aggregate_journal_limit_invalidates_without_complete_claim(tmp_path, monkeypatch):
    binding = _binding(tmp_path)
    capture = CursorCapture(tmp_path / "capture.jsonl", binding=binding)
    monkeypatch.setattr(
        capture_mod,
        "MAX_JOURNAL_BYTES",
        capture._bytes_written + capture_mod.MAX_RECEIPT_BYTES,
    )
    receipt = _receipt(
        binding,
        "1" * 32,
        kind="hook_activity",
        event="sessionStart",
        monotonic_ns=1,
        wall_ns=1,
    )
    assert capture.record(receipt) is False
    result = capture.finish(None)
    assert result["coverage"] == "partial"
    assert result["task_execution_wall_seconds"] is None
    assert "Cursor capture exceeds the aggregate journal bound" in result["reasons"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("capture_nonce"),
        lambda value: value.update(extra=True),
        lambda value: value.update(capture_nonce="A" * 32),
        lambda value: value.update(prompt_sha256="0"),
        lambda value: value.update(workspace="relative"),
    ],
)
def test_binding_must_be_exact_and_canonical(tmp_path, mutation):
    binding = _binding(tmp_path)
    mutation(binding)
    with pytest.raises(ValueError):
        CursorCapture(tmp_path / "capture.jsonl", binding=binding)
