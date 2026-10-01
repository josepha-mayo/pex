from datetime import UTC, datetime

import pytest
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent
from pex_supervisor.verify import (
    acceptance_surface_delta,
    required_verification_probe_kind,
    verification_probe_targets,
    verify_claims,
)
from pex_supervisor.workspace import acceptance_fingerprints, snapshot


def _event(**kwargs) -> HarnessEvent:
    return HarnessEvent(
        event_id=kwargs.pop("event_id", "e"),
        ts=datetime.now(UTC),
        harness_type=HarnessType.SYNTHETIC,
        session_id="synthetic:s",
        event_type=kwargs.pop("event_type", EventType.AGENT_RESPONSE),
        **kwargs,
    )


def _goal(**kwargs) -> Goal:
    now = datetime.now(UTC)
    return Goal(
        id="g",
        project_id="p",
        title="t",
        objective=kwargs.pop("objective", "Finish eval"),
        created_at=now,
        updated_at=now,
        **kwargs,
    )


def test_tests_pass_without_pytest_is_uncertain():
    result = verify_claims(
        [
            {
                "statement": "All tests passed",
                "kind": "tests_pass",
                "polarity": "asserted",
                "confidence": 0.9,
                "source_event_id": "e",
            }
        ],
        [_event(message_delta="All tests passed")],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )
    assert result["status"] == "uncertain"
    assert result["correction"] is None


def test_verified_tests_pass_is_not_blocked_by_same_event_generic_done():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "confidence": 0.9,
            "source_event_id": "stop",
        },
        {
            "statement": "I am done",
            "kind": "complete",
            "polarity": "asserted",
            "confidence": 0.55,
            "source_event_id": "stop",
        },
    ]
    result = verify_claims(
        claims,
        [
            _event(
                event_id="pytest",
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
            ),
            _event(
                event_id="stop",
                event_type=EventType.STOP,
                message_delta="All tests passed. I am done.",
            ),
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )

    assert result["status"] == "supported"
    assert [item["status"] for item in result["verdicts"]] == ["supported", "uncertain"]
    assert result["latest_pytest"] == {
        "event_id": "pytest",
        "scope": "full_suite",
    }
    assert result["pytest_event_id"] == "pytest"
    assert result["pytest_scope"] == "full_suite"


def test_opencode_scoped_test_command_is_validated_as_direct_pytest():
    result = verify_claims(
        [
            {
                "statement": "All tests passed",
                "kind": "tests_pass",
                "polarity": "asserted",
                "confidence": 0.9,
                "source_event_id": "stop",
            }
        ],
        [
            _event(
                event_id="pytest",
                event_type=EventType.SHELL,
                command=r"cd D:\work\case && python -m pytest -q",
                process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 1}},
                metadata={"opencode_scoped_test_command": "python -m pytest -q"},
            ),
            _event(event_id="stop", event_type=EventType.STOP),
        ],
        _goal(acceptance_criteria=["python -m pytest -q exits successfully"]),
        {},
    )

    assert result["status"] == "supported"
    assert result["pytest_scope"] == "full_suite"


def test_goal_required_unittest_pass_is_supported_without_pytest_nag():
    claims = [
        {
            "statement": "The requested unit tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "confidence": 0.9,
            "source_event_id": "stop",
        }
    ]
    command = (
        r'"C:\runtime\pwsh.exe" -Command '
        "'python -m unittest -v test_timeline.py'"
    )
    events = [
        _event(
            event_id="unittest",
            event_type=EventType.SHELL,
            command=command,
            process_state={"unittest": {"ok": True, "exit_code": 0, "passed": 4}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(
        acceptance_criteria=["The immutable unit tests pass."],
        evidence_requirements=["A completed python -m unittest -v test_timeline.py run."],
    )

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == "supported"
    assert result["unittest_observation"] == {
        "event_id": "unittest",
        "scope": "targeted",
        "targets": ["test_timeline.py"],
        "basis": "observed_worker_command",
        "later_file_edits_observed": False,
        "ok": True,
        "exit_code": 0,
    }
    assert required_verification_probe_kind(claims, events, goal, result) is None


def test_goal_required_unittest_without_result_mints_exact_typed_probe():
    goal = _goal(evidence_requirements=["A completed python -m unittest -v test_timeline.py run."])
    result = verify_claims([], [], goal, {})

    kind = required_verification_probe_kind([], [], goal, result)
    assert kind == "python_unittest"
    assert verification_probe_targets(kind, goal) == ("test_timeline.py",)


@pytest.mark.parametrize(
    "runs,status,probe",
    [
        ([("unittest", 0)], "uncertain", "pytest"),
        ([("pytest", 0)], "uncertain", "python_unittest"),
        ([("pytest", 1), ("unittest", 0)], "contradicted", None),
        ([("unittest", 1), ("pytest", 0)], "contradicted", None),
        ([("pytest", 0), ("unittest", 0)], "supported", None),
        ([("unittest", 0), ("pytest", 0)], "supported", None),
    ],
)
def test_explicit_both_framework_goal_needs_independent_results(runs, status, probe):
    goal = _goal(evidence_requirements=["pytest and python -m unittest must both pass."])
    claims = [{"statement": "All requested tests passed", "kind": "tests_pass",
               "polarity": "asserted", "source_event_id": "stop"}]
    events = [
        _event(
            event_id=f"{framework}-{index}", event_type=EventType.SHELL,
            command="pytest" if framework == "pytest" else "python -m unittest",
            process_state={framework: {"ok": code == 0, "exit_code": code, "passed": 4}},
        )
        for index, (framework, code) in enumerate(runs)
    ]
    result = verify_claims(claims, events, goal, {})
    assert result["status"] == status
    assert required_verification_probe_kind(claims, events, goal, result) == probe
    if status == "supported":
        evidence = result["verdicts"][0]["evidence"]
        assert "pytest_ok=true" in evidence
        assert "unittest_ok=true" in evidence


def test_goal_required_unittest_pass_needs_no_probe_when_claim_extraction_is_empty():
    goal = _goal(
        acceptance_criteria=["The immutable unit tests pass."],
        evidence_requirements=["A completed python -m unittest -v test_timeline.py run."],
    )
    events = [
        _event(
            event_id="unittest",
            event_type=EventType.SHELL,
            command=(
                r'"C:\runtime\pwsh.exe" -Command '
                "'python -m unittest -v test_timeline.py'"
            ),
            process_state={"unittest": {"ok": True, "exit_code": 0}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]

    result = verify_claims([], events, goal, {})

    assert result["status"] == "no_claims"
    assert result["unittest_observation"]["ok"] is True
    assert required_verification_probe_kind([], events, goal, result) is None


def test_targeted_pytest_pass_cannot_support_an_all_tests_pass_claim():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="targeted",
            event_type=EventType.SHELL,
            command="pytest -q tests/test_parser.py::test_nested",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 1}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(acceptance_criteria=["tests pass"])

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == "uncertain"
    assert result["latest_pytest"] == {
        "event_id": "targeted",
        "scope": "targeted",
    }
    assert result["pytest_event_id"] == "targeted"
    assert result["pytest_scope"] == "targeted"
    assert "pytest_scope=targeted" in result["verdicts"][0]["evidence"]
    assert required_verification_probe_kind(claims, events, goal, result) == "pytest"


def test_targeted_pytest_failure_can_still_contradict_all_tests_pass():
    result = verify_claims(
        [
            {
                "statement": "All tests passed",
                "kind": "tests_pass",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [
            _event(
                event_id="targeted-fail",
                event_type=EventType.SHELL,
                command="pytest -q -k nested",
                process_state={
                    "pytest": {
                        "ok": False,
                        "exit_code": 1,
                        "failed": "tests/test_parser.py::test_nested",
                    }
                },
            ),
            _event(event_id="stop", event_type=EventType.STOP),
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )

    assert result["status"] == "contradicted"
    assert result["latest_pytest"] == {
        "event_id": "targeted-fail",
        "scope": "targeted",
    }


def test_log_spoof_and_unrelated_process_state_are_not_pytest_evidence():
    result = verify_claims(
        [
            {
                "statement": "All tests passed",
                "kind": "tests_pass",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [
            _event(
                event_id="spoof",
                event_type=EventType.SHELL,
                command="cat pytest.log",
                process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 999}},
            ),
            _event(event_id="stop", event_type=EventType.STOP),
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )

    assert result["status"] == "uncertain"
    assert result["latest_pytest"] is None
    assert result["pytest_event_id"] is None
    assert result["pytest_scope"] is None


@pytest.mark.parametrize("later_edit", [False, True])
def test_observed_pytest_facts_survive_absent_claim_without_promoting_completion(later_edit):
    events = [
        _event(
            event_id="observed-test",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        )
    ]
    if later_edit:
        events.append(_event(event_id="edit", event_type=EventType.FILE_EDIT, file_paths=[]))
    result = verify_claims([], events, _goal(), {})
    assert result["status"] == "no_claims"
    assert result["pytest_observation"] == {
        "event_id": "observed-test",
        "scope": "full_suite",
        "basis": "observed_worker_command",
        "later_file_edits_observed": later_edit,
        "ok": True,
        "exit_code": 0,
        "passed": 4,
    }


@pytest.mark.parametrize("ok", [True, False])
@pytest.mark.parametrize("has_claim", [True, False])
def test_pathless_edit_invalidates_old_pytest_verdict_and_requests_fresh_evidence(ok, has_claim):
    claims = (
        [{"kind": "tests_pass", "statement": "Tests pass", "polarity": "asserted"}]
        if has_claim
        else []
    )
    events = [
        _event(
            event_id="pytest",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={
                "pytest": {
                    "ok": ok,
                    "exit_code": 0 if ok else 1,
                    "passed": 4 if ok else 0,
                }
            },
        ),
        _event(event_id="edit", event_type=EventType.FILE_EDIT, file_paths=[]),
    ]
    goal = _goal(acceptance_criteria=["tests pass"])
    result = verify_claims(claims, events, goal, {})
    assert result["status"] == ("uncertain" if has_claim else "no_claims")
    assert result["correction"] is None
    assert result["pytest_observation"]["later_file_edits_observed"] is True
    assert required_verification_probe_kind(claims, events, goal, result) == "pytest"


def test_pytest_observation_does_not_coerce_or_copy_untrusted_fields():
    result = verify_claims(
        [],
        [
            _event(
                event_type=EventType.SHELL,
                command="pytest -q tests/test_one.py",
                process_state={
                    "pytest": {
                        "ok": "true",
                        "exit_code": False,
                        "passed": True,
                        "failed_count": -1,
                        "collected": 2**53,
                        "output": "untrusted command prose",
                        "unknown": "extra",
                    }
                },
            )
        ],
        _goal(),
        {},
    )
    observation = result["pytest_observation"]
    assert observation["scope"] == "targeted"
    assert observation["ok"] is None and observation["exit_code"] is None
    assert not {"passed", "failed_count", "collected", "output", "unknown"} & observation.keys()
    spoof = verify_claims(
        [],
        [
            _event(
                event_type=EventType.SHELL,
                command="cat pytest.log",
                process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 99}},
            )
        ],
        _goal(),
        {},
    )
    assert spoof["pytest_observation"] is None


def test_generic_done_without_same_event_verified_claim_stays_uncertain():
    result = verify_claims(
        [
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "confidence": 0.55,
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP, message_delta="I am done.")],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )

    assert result["status"] == "uncertain"
    assert result["correction"] is None


def test_generic_done_from_another_event_is_not_shadowed():
    result = verify_claims(
        [
            {
                "statement": "All tests passed",
                "kind": "tests_pass",
                "polarity": "asserted",
                "confidence": 0.9,
                "source_event_id": "response",
            },
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "confidence": 0.55,
                "source_event_id": "stop",
            },
        ],
        [
            _event(
                event_id="pytest",
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={"pytest": {"ok": True, "exit_code": 0}},
            ),
            _event(event_id="response", message_delta="All tests passed."),
            _event(event_id="stop", event_type=EventType.STOP, message_delta="I am done."),
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )

    assert result["status"] == "uncertain"


def test_tests_pass_after_failed_pytest_is_contradicted():
    result = verify_claims(
        [
            {
                "statement": "All tests passed",
                "kind": "tests_pass",
                "polarity": "asserted",
                "confidence": 0.9,
                "source_event_id": "e2",
            }
        ],
        [
            _event(
                event_id="e1",
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={
                    "pytest": {
                        "ok": False,
                        "exit_code": 1,
                        "failed": "tests/test_parser.py::test_nested_array",
                    }
                },
                file_paths=["src/parser.py"],
            ),
            _event(event_id="e2", event_type=EventType.STOP, message_delta="All tests passed"),
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )
    assert result["status"] == "contradicted"
    assert "test_nested_array" in (result["correction"] or "")
    assert not (result["correction"] or "").startswith("PEX:")


def test_failed_pytest_on_stop_is_acceptance_gap_without_tests_pass_claim():
    result = verify_claims(
        [],
        [
            _event(
                event_id="stop",
                event_type=EventType.STOP,
                message_delta="stopped",
                command="pytest -q",
                process_state={
                    "pytest": {
                        "ok": False,
                        "exit_code": 1,
                        "output": "FAILED test_public.py::test_slugify",
                    }
                },
            )
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {"workspace": "C:/public/workspace", "files": ["slugify.py", "test_public.py"]},
    )
    assert result["status"] == "acceptance_gap"
    assert "test_slugify" in (result["correction"] or "")
    assert not (result["correction"] or "").startswith("PEX:")


def test_failed_pytest_after_later_edit_stays_silent_without_claim():
    result = verify_claims(
        [],
        [
            _event(
                event_id="pytest",
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={"pytest": {"ok": False, "exit_code": 1}},
            ),
            _event(
                event_id="edit",
                event_type=EventType.FILE_EDIT,
                file_paths=["slugify.py"],
            ),
            _event(event_id="stop", event_type=EventType.STOP, message_delta="stopped"),
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )
    assert result["status"] == "no_claims"
    assert result["correction"] is None


def test_passing_pytest_without_claims_is_not_a_nudge():
    result = verify_claims(
        [],
        [
            _event(
                event_id="stop",
                event_type=EventType.STOP,
                process_state={"pytest": {"ok": True, "exit_code": 0}},
            )
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )
    assert result["status"] == "no_claims"
    assert result["correction"] is None


def test_short_eval_file_contradicts_completion(tmp_path):
    rows = "\n".join(f'{{"id": {i}}}' for i in range(27))
    (tmp_path / "results.jsonl").write_text(rows + "\n", encoding="utf-8")
    workspace = snapshot(tmp_path, run_pytest=False)
    result = verify_claims(
        [
            {
                "statement": "The evaluation is complete",
                "kind": "evaluation_complete",
                "polarity": "asserted",
                "confidence": 0.85,
                "source_event_id": "e",
            }
        ],
        [_event(event_type=EventType.STOP, message_delta="The evaluation is complete.")],
        _goal(acceptance_criteria=["results.jsonl has 30 rows"]),
        workspace,
    )
    assert result["status"] == "contradicted"
    assert "27" in (result["correction"] or "")
    assert "30" in (result["correction"] or "")


@pytest.mark.parametrize("count", [True, False, -1, "1", 1.0, None])
def test_invalid_artifact_count_is_not_completion_evidence(count, tmp_path):
    goal = _goal(acceptance_criteria=["results.jsonl has 1 rows"])
    workspace = {
        "workspace": str(tmp_path),
        "files": ["results.jsonl"],
        "artifacts": [
            {
                "path": "results.jsonl",
                "row_count_complete": True,
                "row_count": count,
            }
        ],
    }
    result = verify_claims(
        [{"kind": "evaluation_complete", "statement": "Evaluation complete"}],
        [],
        goal,
        workspace,
    )
    assert result["status"] == "uncertain"
    assert result["acceptance_status"] == "uncertain"
    assert result["correction"] is None
    assert required_verification_probe_kind([], [], goal, result) == "artifact_tail"


@pytest.mark.parametrize("count,expected", [(0, "contradicted"), (1, "supported")])
def test_valid_artifact_count_remains_usable(count, expected, tmp_path):
    result = verify_claims(
        [{"kind": "evaluation_complete", "statement": "Evaluation complete"}],
        [],
        _goal(acceptance_criteria=["results.jsonl has 1 rows"]),
        {
            "workspace": str(tmp_path),
            "files": ["results.jsonl"],
            "artifacts": [
                {
                    "path": "results.jsonl",
                    "row_count_complete": True,
                    "row_count": count,
                }
            ],
        },
    )
    assert result["status"] == expected


def test_large_jsonl_row_count_uses_complete_file_not_preview(tmp_path):
    rows = "\n".join(f'{{"id": {i}, "payload": "{"x" * 200}"}}' for i in range(30))
    (tmp_path / "results.jsonl").write_text(rows + "\n", encoding="utf-8")
    workspace = snapshot(tmp_path, run_pytest=False)

    result = verify_claims(
        [
            {
                "statement": "The evaluation is complete",
                "kind": "evaluation_complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(acceptance_criteria=["results.jsonl has 30 rows"]),
        workspace,
    )

    assert workspace["artifacts"][0]["row_count"] == 30
    assert result["status"] == "supported"


def test_nonfinite_json_rows_cannot_satisfy_acceptance(tmp_path):
    (tmp_path / "results.jsonl").write_text(
        '{"score": NaN}\n{"score": Infinity}\n{"score": 1e9999}\n',
        encoding="utf-8",
    )
    workspace = snapshot(tmp_path)

    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(acceptance_criteria=["results.jsonl has 3 rows"]),
        workspace,
    )

    assert result["status"] == "no_claims"
    assert result["acceptance_status"] == "uncertain"
    assert workspace["artifacts"][0]["row_count"] is None
    assert workspace["artifacts"][0]["row_count_complete"] is False


def test_duplicate_json_keys_cannot_satisfy_row_acceptance(tmp_path):
    (tmp_path / "results.jsonl").write_text(
        '{"passed":false,"passed":true}\n',
        encoding="utf-8",
    )
    workspace = snapshot(tmp_path)

    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(acceptance_criteria=["results.jsonl has 1 rows"]),
        workspace,
    )

    assert result["acceptance_status"] == "uncertain"
    assert workspace["artifacts"][0]["row_count"] is None
    assert workspace["artifacts"][0]["row_count_complete"] is False


def test_traversal_shaped_goal_file_is_not_read_or_reported_missing(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("shipped", encoding="utf-8")
    workspace = snapshot(tmp_path)

    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(acceptance_criteria=["../outside-secret.txt contains shipped"]),
        workspace,
    )

    assert result["status"] == "no_claims"
    assert result["acceptance_status"] == "uncertain"
    assert all(
        "outside-secret" not in item
        for verdict in result["verdicts"]
        for item in verdict["evidence"]
    )


def test_unrelated_json_artifact_cannot_stand_in_for_row_requirement(tmp_path):
    (tmp_path / "results.json").write_text('[{"config": true}]', encoding="utf-8")

    result = verify_claims(
        [
            {
                "statement": "The evaluation is complete",
                "kind": "evaluation_complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(acceptance_criteria=["evaluation has 30 rows"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "uncertain"
    assert result["correction"] is None


def test_missing_declared_row_artifact_names_the_declared_file(tmp_path):
    result = verify_claims(
        [
            {
                "statement": "The evaluation is complete",
                "kind": "evaluation_complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(acceptance_criteria=["reports/final.jsonl has 30 rows"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "contradicted"
    assert "reports/final.jsonl" in (result["correction"] or "")


def test_premature_stop_without_claim_still_names_missing_file(tmp_path):
    workspace = snapshot(tmp_path, run_pytest=False)
    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP, message_delta="Stopping here.")],
        _goal(
            objective="Create report.txt containing shipped.",
            evidence_requirements=["report.txt"],
        ),
        workspace,
    )
    assert result["status"] == "acceptance_gap"
    assert "report.txt" in (result["correction"] or "")
    assert not (result["correction"] or "").startswith("PEX:")
    assert result["verdicts"][0]["claim"] is None
    assert result["verdicts"][0]["basis"] == "acceptance_criterion"


def test_exists_phrasing_is_a_required_file(tmp_path):
    from pex_supervisor.verify import required_files

    workspace = snapshot(tmp_path, run_pytest=False)
    goal = _goal(acceptance_criteria=["dataset.parquet exists"])
    assert required_files(goal) == ["dataset.parquet"]
    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP, message_delta="Stopping here.")],
        goal,
        workspace,
    )
    assert result["status"] == "acceptance_gap"
    assert "dataset.parquet" in (result["correction"] or "")


def test_generic_completion_is_supported_by_required_file_content(tmp_path):
    (tmp_path / "report.txt").write_text("shipped\n", encoding="utf-8")
    claim = {
        "statement": "I am done",
        "kind": "complete",
        "polarity": "asserted",
        "confidence": 0.55,
        "source_event_id": "stop",
    }

    result = verify_claims(
        [claim],
        [_event(event_id="stop", event_type=EventType.STOP, message_delta="I am done.")],
        _goal(
            acceptance_criteria=["report.txt contains shipped"],
            evidence_requirements=["report.txt"],
        ),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "supported"
    assert "contains:report.txt:shipped" in result["verdicts"][0]["evidence"]


@pytest.mark.parametrize(
    "content,supported",
    [
        (b"stage-one-ok\n", True),
        (b"stage-one-ok", False),
        (b"stage-one-ok\n\n", False),
        (b"stage-one-ok\r\n", False),
        (b"prefix stage-one-ok\n", False),
        (b"stage-one-ok followed by one newline", False),
    ],
)
def test_exact_file_content_with_one_newline_is_not_prose_or_substring(
    tmp_path, content, supported
):
    (tmp_path / "report.txt").write_bytes(content)
    result = verify_claims(
        [
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(
            acceptance_criteria=[
                "report.txt contains exactly stage-one-ok followed by one newline."
            ],
            evidence_requirements=["report.txt"],
        ),
        snapshot(tmp_path, run_pytest=False),
    )
    assert (result["status"] == "supported") is supported
    if not supported:
        assert result["status"] == "contradicted"


@pytest.mark.parametrize(
    "content,supported", [(b"ready", True), (b"ready\n", False), (b"already", False)]
)
def test_exact_content_without_newline_requires_whole_file(tmp_path, content, supported):
    (tmp_path / "report.txt").write_bytes(content)
    result = verify_claims(
        [
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(acceptance_criteria=['report.txt contains exactly "ready".']),
        snapshot(tmp_path, run_pytest=False),
    )
    assert (result["status"] == "supported") is supported


@pytest.mark.parametrize(
    "content,expected", [(b"ready\n", "supported"), (b"ready\r\n", "unsatisfied")]
)
def test_markdown_path_exact_acceptance_without_completion_claim(tmp_path, content, expected):
    (tmp_path / "report.txt").write_bytes(content)
    result = verify_claims(
        [],
        [],
        _goal(
            acceptance_criteria=["`report.txt` contains exactly `ready` followed by one newline."],
            evidence_requirements=[],
        ),
        snapshot(tmp_path, run_pytest=False),
    )
    assert result["acceptance_status"] == expected
    assert result["status"] == ("no_claims" if expected == "supported" else "acceptance_gap")
    assert result["acceptance_evidence"]


def test_unrecognized_goal_requirement_keeps_exact_files_uncertain_and_explains_why(tmp_path):
    (tmp_path / "report.txt").write_bytes(b"ready\n")
    criterion = "Both files are verified before the whole goal is considered complete."
    result = verify_claims(
        [],
        [],
        _goal(
            acceptance_criteria=[
                "`report.txt` contains exactly `ready` followed by one newline.",
                criterion,
            ],
            evidence_requirements=[],
        ),
        snapshot(tmp_path, run_pytest=False),
    )
    assert result["status"] == "no_claims"
    assert result["acceptance_status"] == "uncertain"
    assert "equals:report.txt:ready\n" in result["acceptance_evidence"]
    assert f"unchecked:{criterion}" in result["acceptance_evidence"]
    assert result["correction"] is None


@pytest.mark.parametrize(
    "path", ["../outside.txt", "/outside.txt", "C:/outside.txt", "report.txt` extra `"]
)
def test_quoted_unsafe_or_malformed_path_is_not_file_acceptance(path):
    from pex_supervisor.verify import _expected_content

    assert _expected_content(f"`{path}` contains exactly `ready`.") is None


@pytest.mark.parametrize(
    "criterion,content,status",
    [
        ('report.txt contains exactly "ready.done".', b"ready.done", "supported"),
        ('report.txt contains exactly "".', b"", "supported"),
        ('report.txt contains exactly "ready" followed by one newline.', b"ready\n", "supported"),
        (
            "report.txt contains exactly ready and nothing else.",
            b"ready and nothing else",
            "uncertain",
        ),
        ('report.txt contains exactly "\ufffd".', b"\xff", "uncertain"),
        ('report.txt contains exactly "ready".', b"ready" + b"x" * 4_000_000, "uncertain"),
    ],
    ids=["quoted-period", "empty", "quoted-newline", "ambiguous", "invalid-utf8", "oversized"],
)
def test_exact_content_preserves_literals_and_fails_closed_on_ambiguity(
    tmp_path, criterion, content, status
):
    (tmp_path / "report.txt").write_bytes(content)
    result = verify_claims(
        [
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(acceptance_criteria=[criterion], evidence_requirements=["report.txt"]),
        snapshot(tmp_path, run_pytest=False),
    )
    assert result["status"] == status


def test_required_content_after_legacy_preview_boundary_is_still_observed(tmp_path):
    (tmp_path / "report.txt").write_text(
        ("draft\n" * 20_000) + "shipped\n",
        encoding="utf-8",
    )
    result = verify_claims(
        [
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP, message_delta="I am done.")],
        _goal(acceptance_criteria=["report.txt contains shipped"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "supported"


def test_malformed_declared_json_artifact_never_supports_completion(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "final.json").write_text("{\n" * 30, encoding="utf-8")

    result = verify_claims(
        [
            {
                "statement": "The evaluation is complete",
                "kind": "evaluation_complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(acceptance_criteria=["reports/final.json has 30 rows"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "uncertain"
    assert result["correction"] is None


def test_oversized_content_check_stays_uncertain_instead_of_false_contradiction(tmp_path):
    (tmp_path / "report.txt").write_bytes(b"draft\n" * 700_000)
    result = verify_claims(
        [
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP, message_delta="I am done.")],
        _goal(acceptance_criteria=["report.txt contains shipped"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "uncertain"
    assert result["verdicts"][0]["evidence"] == ["content_check_incomplete:report.txt"]


def test_wrong_required_file_content_contradicts_completion(tmp_path):
    (tmp_path / "report.txt").write_text("draft\n", encoding="utf-8")
    result = verify_claims(
        [
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP, message_delta="I am done.")],
        _goal(acceptance_criteria=["report.txt contains shipped"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "contradicted"
    assert "report.txt" in (result["correction"] or "")
    assert "shipped" in (result["correction"] or "")


def test_wrong_required_file_content_is_gap_even_without_claim(tmp_path):
    (tmp_path / "report.txt").write_text("draft\n", encoding="utf-8")

    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(acceptance_criteria=["report.txt contains shipped"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "acceptance_gap"
    assert result["verdicts"][0]["basis"] == "acceptance_criterion"


def test_goal_criteria_cannot_turn_hidden_evaluator_files_into_evidence(tmp_path):
    secret = "HIDDEN_EVALUATOR_CONTENT_SENTINEL"
    (tmp_path / "evaluator.py").write_text(secret, encoding="utf-8")
    (tmp_path / "metadata.yaml").write_text("rows: [one]", encoding="utf-8")
    claim = {
        "statement": "I am done",
        "kind": "complete",
        "polarity": "asserted",
        "source_event_id": "stop",
    }

    result = verify_claims(
        [claim],
        [_event(event_id="stop", event_type=EventType.STOP, message_delta="I am done.")],
        _goal(
            acceptance_criteria=[f"evaluator.py contains {secret}"],
            evidence_requirements=["metadata.yaml"],
        ),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "uncertain"
    assert result["acceptance_status"] == "uncertain"
    assert secret not in str(result)


def test_satisfied_file_acceptance_is_observed_without_worker_claim(tmp_path):
    (tmp_path / "report.txt").write_text("shipped\n", encoding="utf-8")

    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(acceptance_criteria=["report.txt contains shipped"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "no_claims"
    assert result["acceptance_status"] == "supported"


def test_full_suite_pytest_requirement_is_first_class_acceptance_evidence(tmp_path):
    (tmp_path / "csv_utils.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "test_csv_utils.py").write_text(
        "def test_value():\n    assert True\n", encoding="utf-8"
    )
    events = [
        _event(
            event_id="pytest-pass",
            event_type=EventType.SHELL,
            command="python -m pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 1}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]

    result = verify_claims(
        [],
        events,
        _goal(
            acceptance_criteria=["python -m pytest -q exits successfully"],
            evidence_requirements=["csv_utils.py", "test_csv_utils.py"],
        ),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "no_claims"
    assert result["acceptance_status"] == "supported"
    assert "pytest_event_id=pytest-pass" in result["acceptance_evidence"]
    assert "pytest_ok=true" in result["acceptance_evidence"]


def test_full_suite_pytest_requirement_stays_uncertain_without_a_run(tmp_path):
    (tmp_path / "csv_utils.py").write_text("VALUE = 1\n", encoding="utf-8")

    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(
            acceptance_criteria=["python -m pytest -q exits successfully"],
            evidence_requirements=["csv_utils.py"],
        ),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "no_claims"
    assert result["acceptance_status"] == "uncertain"
    assert "unchecked:full-suite pytest exits successfully" in result["acceptance_evidence"]


def test_existing_file_does_not_hide_unverified_acceptance_criterion(tmp_path):
    (tmp_path / "report.txt").write_text("shipped\n", encoding="utf-8")
    result = verify_claims(
        [
            {
                "statement": "I am done",
                "kind": "complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP, message_delta="I am done.")],
        _goal(
            acceptance_criteria=["report.txt contains shipped", "deployment is healthy"],
            evidence_requirements=["report.txt"],
        ),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "uncertain"


def test_unrelated_partial_claim_does_not_hide_acceptance_gap(tmp_path):
    result = verify_claims(
        [
            {
                "statement": "parser",
                "kind": "implemented",
                "polarity": "asserted",
                "confidence": 0.75,
                "source_event_id": "response",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(evidence_requirements=["reports/report.txt"]),
        snapshot(tmp_path, run_pytest=False),
    )
    assert result["status"] == "acceptance_gap"
    assert result["missing_files"] == ["reports/report.txt"]


def test_required_file_matching_is_case_insensitive():
    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(evidence_requirements=["report.txt"]),
        {
            "workspace": "C:/worker",
            "files": ["REPORT.TXT"],
            "files_truncated": False,
        },
    )
    assert result["status"] == "no_claims"
    assert result["missing_files"] == []


def test_exact_required_file_is_checked_beyond_snapshot_limit(tmp_path):
    for index in range(401):
        (tmp_path / f"a_{index:03}.txt").write_text("x", encoding="utf-8")
    (tmp_path / "z_required.txt").write_text("done", encoding="utf-8")
    workspace = snapshot(tmp_path, run_pytest=False)
    assert workspace["files_truncated"] is True
    assert "z_required.txt" not in workspace["files"]
    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(evidence_requirements=["z_required.txt"]),
        workspace,
    )
    assert result["status"] == "no_claims"


def test_edit_after_failed_pytest_is_uncertain_until_rerun():
    result = verify_claims(
        [
            {
                "statement": "All tests passed",
                "kind": "tests_pass",
                "polarity": "asserted",
                "confidence": 0.9,
                "source_event_id": "stop",
            }
        ],
        [
            _event(
                event_id="pytest",
                event_type=EventType.SHELL,
                command="pytest -q",
                process_state={
                    "pytest": {
                        "ok": False,
                        "exit_code": 1,
                        "failed": "tests/test_parser.py::test_nested_array",
                    }
                },
            ),
            _event(
                event_id="edit",
                event_type=EventType.FILE_EDIT,
                file_paths=["src/parser.py"],
            ),
            _event(event_id="stop", event_type=EventType.STOP),
        ],
        _goal(acceptance_criteria=["tests pass"]),
        {},
    )
    assert result["status"] == "uncertain"
    verdict = result["verdicts"][0]
    assert verdict["correction"] is None
    assert "later_edit:src/parser.py" in verdict["evidence"]
    assert "Observe a new pytest result" in verdict["probe"]


def test_csv_line_count_does_not_guess_whether_header_is_a_data_row(tmp_path):
    (tmp_path / "report.csv").write_text(
        "name,value\na,1\nb,2\nc,3\nd,4\n",
        encoding="utf-8",
    )
    result = verify_claims(
        [
            {
                "statement": "Evaluation complete",
                "kind": "evaluation_complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(acceptance_criteria=["report.csv has 5 rows"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "uncertain"
    assert result["acceptance_status"] == "uncertain"


def test_pathological_row_requirement_stays_uncertain_instead_of_overflowing(tmp_path):
    requirement = f"results.jsonl has {'9' * 100} rows"
    result = verify_claims(
        [],
        [_event(event_type=EventType.STOP)],
        _goal(acceptance_criteria=[requirement]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "no_claims"
    assert result["acceptance_status"] == "uncertain"


def test_deep_json_artifact_cannot_crash_or_fake_row_evidence(tmp_path):
    (tmp_path / "results.json").write_text("[" * 10_000 + "]" * 10_000, encoding="utf-8")
    result = verify_claims(
        [
            {
                "statement": "Evaluation complete",
                "kind": "evaluation_complete",
                "polarity": "asserted",
                "source_event_id": "stop",
            }
        ],
        [_event(event_id="stop", event_type=EventType.STOP)],
        _goal(acceptance_criteria=["results.json has 1 rows"]),
        snapshot(tmp_path, run_pytest=False),
    )

    assert result["status"] == "uncertain"


def test_full_suite_pass_summary_without_terminal_exit_is_uncertain_and_requests_probe():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-no-exit",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": None, "passed": 4, "output": "4 passed"}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(acceptance_criteria=["4 tests pass"])

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == "uncertain"
    assert "pytest_observed_without_exit" in result["verdicts"][0]["evidence"]
    assert required_verification_probe_kind(claims, events, goal, result) == "pytest"


def test_expected_pytest_count_mismatch_contradicts_tests_pass_claim():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-short-collection",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 1}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(acceptance_criteria=["4 tests pass"])

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == "contradicted"
    verdict = result["verdicts"][0]
    assert "pytest_exit_code=0" in verdict["evidence"]
    assert "pytest_passed=1" in verdict["evidence"]
    assert "pytest_expected_passed=4" in verdict["evidence"]
    assert "requires 4 passing tests" in str(result["correction"])


def test_exact_expected_pytest_count_with_exit_zero_supports_without_probe():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-exact",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(acceptance_criteria=["4 tests pass"])

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == "supported"
    assert "pytest_exit_code=0" in result["verdicts"][0]["evidence"]
    assert required_verification_probe_kind(claims, events, goal, result) is None


@pytest.mark.parametrize(
    ("observed", "expected_status"),
    [(3, "contradicted"), (4, "supported"), (5, "supported")],
)
def test_minimum_pytest_count_is_not_collapsed_to_no_requirement(observed, expected_status):
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-minimum",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": observed}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(acceptance_criteria=["at least 4 tests pass"])

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == expected_status


def test_minimum_pytest_count_violation_is_an_acceptance_gap_without_a_worker_claim():
    events = [
        _event(
            event_id="pytest-short",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 3}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]

    result = verify_claims([], events, _goal(acceptance_criteria=["at least 4 tests pass"]), {})

    assert result["status"] == "acceptance_gap"
    assert any(
        item.get("basis") == "acceptance_criterion"
        and "pytest_count_requirement" in " ".join(item.get("evidence") or [])
        for item in result["verdicts"]
    )


def test_conflicting_exact_pytest_counts_stay_ambiguous_and_do_not_loop_a_probe():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-conflict",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(acceptance_criteria=["4 tests pass", "5 tests pass"])

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == "uncertain"
    assert "pytest_count_requirement_ambiguous" in result["verdicts"][0]["evidence"]
    assert required_verification_probe_kind(claims, events, goal, result) is None


@pytest.mark.parametrize(
    "criterion",
    [
        "at most 4 tests pass",
        "between 4 and 6 tests pass",
        "4-6 tests pass",
        "4.5 tests pass",
        "Do not require 4 tests pass",
    ],
)
def test_unsupported_or_historical_count_language_never_partially_matches(criterion):
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-ambiguous",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]

    result = verify_claims(claims, events, _goal(acceptance_criteria=[criterion]), {})

    assert result["status"] == "uncertain"
    assert "pytest_count_requirement_ambiguous" in result["verdicts"][0]["evidence"]


def test_passed_and_collected_counts_have_distinct_semantics():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-categories",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={
                "pytest": {
                    "ok": True,
                    "exit_code": 0,
                    "passed": 4,
                    "collected": 7,
                    "skipped": 2,
                    "xfailed": 1,
                }
            },
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(acceptance_criteria=["4 tests pass", "7 tests collected"])

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == "supported"


def test_deselected_tests_block_generic_all_tests_support():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-deselected",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={
                "pytest": {
                    "ok": True,
                    "exit_code": 0,
                    "passed": 4,
                    "deselected": 2,
                }
            },
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]

    result = verify_claims(claims, events, _goal(acceptance_criteria=["tests pass"]), {})

    assert result["status"] == "uncertain"
    assert "pytest_evidence_inconsistent" in result["verdicts"][0]["evidence"]


def test_ok_true_with_nonzero_exit_cannot_support():
    claims = [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "source_event_id": "stop",
        }
    ]
    events = [
        _event(
            event_id="pytest-inconsistent",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 1, "passed": 4}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    goal = _goal(acceptance_criteria=["tests pass"])

    result = verify_claims(claims, events, goal, {})

    assert result["status"] == "contradicted"
    assert "pytest_exit_code=1" in result["verdicts"][0]["evidence"]


@pytest.mark.parametrize("ok", [None, True])
@pytest.mark.parametrize("exit_code", [1, 2])
def test_nonzero_pytest_exit_is_unfinished_without_completion_claim(ok, exit_code):
    events = [
        _event(
            event_id="failed-run", event_type=EventType.SHELL, command="pytest -q",
            process_state={"pytest": {"ok": ok, "exit_code": exit_code}},
        ),
        _event(event_id="stop", event_type=EventType.STOP),
    ]
    result = verify_claims([], events, _goal(acceptance_criteria=["tests pass"]), {})
    assert result["status"] == "acceptance_gap"
    assert f"(exit {exit_code})" in result["correction"]
    assert "pytest_event_id=failed-run" in result["evidence"]
    assert f"pytest_exit_code={exit_code}" in result["evidence"]

    events.insert(1, _event(event_type=EventType.FILE_EDIT, file_paths=["solver.py"]))
    after_edit = verify_claims([], events, _goal(acceptance_criteria=["tests pass"]), {})
    assert after_edit["status"] == "no_claims"
    assert after_edit["correction"] is None


@pytest.mark.parametrize("exit_code", [True, "1", None])
def test_untyped_pytest_exit_is_not_failure_proof_without_claim(exit_code):
    events = [
        _event(event_type=EventType.SHELL, command="pytest -q",
               process_state={"pytest": {"exit_code": exit_code}}),
        _event(event_type=EventType.STOP),
    ]
    result = verify_claims([], events, _goal(acceptance_criteria=["tests pass"]), {})
    assert result["status"] == "no_claims"
    assert result["correction"] is None


def test_uncertain_unreadable_file_selects_file_count_probe():
    goal = _goal(
        objective="Ship the report artifact",
        acceptance_criteria=["report.txt"],
    )
    verification = {
        "status": "uncertain",
        "verdicts": [
            {
                "status": "uncertain",
                "evidence": ["temporarily_unreadable:report.txt"],
            }
        ],
    }

    assert required_verification_probe_kind([], [], goal, verification) == "file_count"
    assert verification_probe_targets("file_count", goal) == ("report.txt",)


def test_uncertain_row_count_selects_artifact_tail_probe():
    goal = _goal(
        objective="Build the ledger",
        acceptance_criteria=["results.jsonl has 10 rows"],
    )
    verification = {
        "status": "uncertain",
        "verdicts": [
            {
                "status": "uncertain",
                "evidence": ["row_count_unavailable:results.jsonl"],
            }
        ],
    }

    assert required_verification_probe_kind([], [], goal, verification) == "artifact_tail"
    assert verification_probe_targets("artifact_tail", goal) == ("results.jsonl",)


def test_uncertain_health_goal_selects_service_health_probe():
    goal = _goal(
        objective="Keep the local /health endpoint green",
        acceptance_criteria=["healthcheck is green"],
    )
    verification = {"status": "uncertain", "verdicts": []}

    assert required_verification_probe_kind([], [], goal, verification) == "service_health"
    assert verification_probe_targets("service_health", goal) == ()


def test_uncertain_script_requirement_selects_command_exit_probe():
    goal = _goal(
        objective="Run the project check script",
        acceptance_criteria=["scripts/check.sh"],
        evidence_requirements=["scripts/check.sh"],
    )
    verification = {
        "status": "uncertain",
        "verdicts": [{"status": "uncertain", "evidence": ["no_external_check"]}],
    }

    assert required_verification_probe_kind([], [], goal, verification) == "command_exit"
    assert verification_probe_targets("command_exit", goal) == ("scripts/check.sh",)


def _green_pytest_events() -> list[HarnessEvent]:
    return [
        _event(
            event_id="pytest",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": True, "exit_code": 0, "passed": 4}},
        ),
        _event(event_id="stop", event_type=EventType.STOP, message_delta="done"),
    ]


def _tests_pass_claims() -> list[dict]:
    return [
        {
            "statement": "All tests passed",
            "kind": "tests_pass",
            "polarity": "asserted",
            "confidence": 0.9,
            "source_event_id": "stop",
        }
    ]


def test_acceptance_surface_fingerprinted_in_snapshot(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_core.py").write_text("def test_core():\n    assert True\n")
    (tmp_path / "app.py").write_text("print('hi')\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")

    workspace = snapshot(tmp_path)
    fingerprints = acceptance_fingerprints(workspace)

    assert set(fingerprints) == {"tests/test_core.py", "pyproject.toml"}
    assert all(len(digest) == 64 for digest in fingerprints.values())
    assert "app.py" not in fingerprints


def test_modified_acceptance_file_downgrades_supported_claim(tmp_path):
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    test_file = tests_dir / "test_core.py"
    test_file.write_text("def test_core():\n    assert add(1, 1) == 2\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
    }
    test_file.write_text("def test_core():\n    pass\n")

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "uncertain"
    assert result["acceptance_status"] == "uncertain"
    assert result["acceptance_surface"]["modified"] == ["tests/test_core.py"]
    verdict_evidence = [
        item for verdict in result["verdicts"] for item in verdict["evidence"]
    ]
    assert "acceptance_surface_modified:tests/test_core.py" in verdict_evidence
    assert all(item["status"] != "supported" for item in result["verdicts"])


def test_deleted_acceptance_file_downgrades_supported_claim(tmp_path):
    test_file = tmp_path / "test_core.py"
    test_file.write_text("def test_core():\n    assert True\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
    }
    test_file.unlink()

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "uncertain"
    assert result["acceptance_surface"]["deleted"] == ["test_core.py"]
    assert "acceptance_surface_deleted:test_core.py" in result["acceptance_evidence"]


def test_added_test_file_does_not_downgrade_supported_claim(tmp_path):
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
    }
    (tmp_path / "test_new.py").write_text("def test_new():\n    assert True\n")

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "supported"
    assert result["acceptance_surface"]["added"] == ["test_new.py"]


def test_added_runner_config_downgrades_supported_claim(tmp_path):
    """Dropping a pytest.ini/conftest.py post-baseline can deselect the suite."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_core.py").write_text("def test_core():\n    assert True\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
    }
    (tmp_path / "pytest.ini").write_text(
        "[pytest]\naddopts = --deselect tests/test_core.py\n"
    )

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "uncertain"
    surface = result["acceptance_surface"]
    assert surface["added_config"] == ["pytest.ini"]
    assert "acceptance_surface_config_added:pytest.ini" in result["acceptance_evidence"]


def test_incomplete_baseline_cannot_support_claim(tmp_path):
    """A truncated first scan may have missed surface files — fail closed."""
    (tmp_path / "test_core.py").write_text("def test_core():\n    assert True\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": False,
    }

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "uncertain"
    assert result["acceptance_surface"]["baseline_complete"] is False
    assert "acceptance_surface_baseline_incomplete" in result["acceptance_evidence"]


def test_verify_context_baseline_stays_flagged_forever(tmp_path):
    """A baseline sealed by a verify_claim call is claim-adjacent forever."""
    (tmp_path / "test_core.py").write_text("def test_core():\n    assert True\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
        "sealed_context": "verify",
    }

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "uncertain"
    assert result["acceptance_surface"]["sealed_at_claim"] is True
    assert "acceptance_surface_baseline_at_claim" in result["acceptance_evidence"]


def test_unsealed_marker_flags_supported_claim(tmp_path):
    """Seal attempted but impossible → unbaselined, not silently supported."""
    (tmp_path / "test_core.py").write_text("def test_core():\n    assert True\n")

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline={"unsealed": True},
    )

    assert result["status"] == "uncertain"
    assert result["acceptance_surface"]["reason"] == "unsealed"
    assert "acceptance_surface_unbaselined" in result["acceptance_evidence"]


def test_unbaselined_claim_verification_is_unchanged(tmp_path):
    (tmp_path / "test_core.py").write_text("def test_core():\n    assert True\n")

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
    )

    assert result["status"] == "supported"
    assert result["acceptance_surface"]["baselined"] is False


def test_unobserved_workspace_with_baseline_cannot_support_claim(tmp_path):
    test_file = tmp_path / "test_core.py"
    test_file.write_text("def test_core():\n    assert True\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
    }

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        {"error": "cwd missing"},
        acceptance_baseline=baseline,
    )

    assert result["status"] == "uncertain"
    surface = result["acceptance_surface"]
    assert surface["baselined"] is True and surface["checked"] is False
    verdict_evidence = [
        item for verdict in result["verdicts"] for item in verdict["evidence"]
    ]
    assert "acceptance_surface_check_incomplete" in verdict_evidence


def test_oversized_acceptance_file_is_flagged_unhashed(tmp_path, monkeypatch):
    from pex_supervisor import workspace as workspace_module

    monkeypatch.setattr(workspace_module, "MAX_FINGERPRINT_BYTES", 8)
    (tmp_path / "test_big.py").write_text("def test_big():\n    assert True\n")
    snapshot_result = snapshot(tmp_path)
    assert snapshot_result["files_truncated"] is True
    fingerprints = acceptance_fingerprints(snapshot_result)
    assert fingerprints == {"test_big.py": None}
    baseline = {"files": {"test_big.py": None}, "files_complete": True}
    delta = acceptance_surface_delta(baseline, snapshot_result)
    assert delta["unhashed"] == ["test_big.py"]
    assert delta["modified"] == []


def test_acceptance_surface_delta_without_baseline_is_honest():
    assert acceptance_surface_delta(None, {})["baselined"] is False
    assert acceptance_surface_delta({"files": "nope"}, {})["baselined"] is False


def test_baseline_sealed_at_claim_cannot_support_claim(tmp_path):
    """A baseline first captured at claim time proves no prior integrity."""
    test_file = tmp_path / "test_core.py"
    test_file.write_text("def test_core():\n    assert True\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
        "sealed_now": True,
    }

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "uncertain"
    surface = result["acceptance_surface"]
    assert surface["sealed_at_claim"] is True
    assert surface["modified"] == []
    assert "acceptance_surface_baseline_at_claim" in result["acceptance_evidence"]


def test_empty_surface_sealed_at_claim_stays_supported(tmp_path):
    """With no acceptance files to protect, a late baseline is not a flag."""
    (tmp_path / "app.py").write_text("print('hi')\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
        "sealed_now": True,
    }

    result = verify_claims(
        _tests_pass_claims(),
        _green_pytest_events(),
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "supported"
    assert result["acceptance_surface"]["sealed_at_claim"] is False


def test_tampered_surface_does_not_hide_contradicted_verdict(tmp_path):
    test_file = tmp_path / "test_core.py"
    test_file.write_text("def test_core():\n    assert True\n")
    baseline = {
        "files": acceptance_fingerprints(snapshot(tmp_path)),
        "files_complete": True,
    }
    test_file.write_text("def test_core():\n    pass\n")
    events = [
        _event(
            event_id="pytest",
            event_type=EventType.SHELL,
            command="pytest -q",
            process_state={"pytest": {"ok": False, "exit_code": 1}},
        ),
        _event(event_id="stop", event_type=EventType.STOP, message_delta="done"),
    ]

    result = verify_claims(
        _tests_pass_claims(),
        events,
        _goal(acceptance_criteria=["tests pass"]),
        snapshot(tmp_path),
        acceptance_baseline=baseline,
    )

    assert result["status"] == "contradicted"
    assert result["acceptance_surface"]["modified"] == ["test_core.py"]
