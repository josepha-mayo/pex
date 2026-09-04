from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_protocol.enums import HarnessType, PolicyVerdict
from pex_protocol.verification import (
    EvidenceGatheringReceipt,
    EvidenceGatheringState,
    PytestInvocationScope,
    VerificationBackendKind,
    VerificationExecutionReceipt,
    VerificationExecutionResult,
    VerificationProbe,
    VerificationProbeKind,
    classify_pytest_invocation,
)
from pydantic import ValidationError


def _probe(**changes) -> VerificationProbe:
    values = {
        "id": "probe_1",
        "kind": VerificationProbeKind.PYTEST,
        "harness_type": HarnessType.CODEX,
        "session_id": "codex:thread_1",
        "project_id": "project_1",
        "goal_id": "goal_1",
        "request_event_id": "stop_1",
        "cwd": "C:/workspace",
        "relative_targets": ["tests/test_parser.py"],
    }
    values.update(changes)
    return VerificationProbe(**values)


def test_probe_is_typed_and_rejects_executable_or_escaping_input():
    probe = _probe()
    assert probe.kind == VerificationProbeKind.PYTEST
    assert probe.harness_type == HarnessType.CODEX
    assert probe.relative_targets == ("tests/test_parser.py",)
    assert probe.expected_pytest_scope == PytestInvocationScope.TARGETED
    assert _probe(relative_targets=[]).expected_pytest_scope == PytestInvocationScope.FULL_SUITE
    assert "argv" not in probe.model_dump()
    assert probe.cwd == "C:/workspace"
    assert probe.project_id == "project_1"
    assert probe.request_event_id == "stop_1"

    for target in (
        "../secret.py",
        "C:/outside/test_x.py",
        "/tmp/test_x.py",
        "a//b.py",
        "-k",
    ):
        with pytest.raises(ValidationError, match="contained relative paths"):
            _probe(relative_targets=[target])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        VerificationProbe.model_validate({**probe.model_dump(), "argv": ["pytest"]})
    with pytest.raises(ValidationError, match="frozen"):
        probe.cwd = "C:/other"
    with pytest.raises(ValidationError, match="frozen"):
        probe.harness_type = HarnessType.CURSOR
    with pytest.raises(ValidationError, match="exact absolute path"):
        _probe(cwd="relative/workspace")
    with pytest.raises(ValidationError, match="concrete harness"):
        _probe(harness_type=HarnessType.UNKNOWN)


@pytest.mark.parametrize(
    "command",
    [
        "pytest -q",
        "python -m pytest -q",
        "uv run pytest -q",
        "uv run --frozen python -m pytest -q",
    ],
)
def test_classifier_recognizes_only_direct_full_suite_invocations(command):
    invocation = classify_pytest_invocation(command)
    assert invocation is not None
    assert invocation.scope == PytestInvocationScope.FULL_SUITE
    assert invocation.selectors == ()


@pytest.mark.parametrize(
    "command",
    [
        "pytest tests/test_parser.py",
        "pytest tests/test_parser.py::test_nested",
        'pytest -k "nested and parser"',
        "pytest -m smoke",
        "pytest --last-failed",
        "pytest --lf",
        "pytest --ignore tests/slow",
        "pytest -o testpaths=tests/smoke",
        "pytest -c smoke.ini",
    ],
)
def test_classifier_marks_subset_and_selection_modes_targeted(command):
    invocation = classify_pytest_invocation(command)
    assert invocation is not None
    assert invocation.scope == PytestInvocationScope.TARGETED
    assert invocation.selectors


@pytest.mark.parametrize(
    "command",
    [
        "echo pytest -q 897 passed",
        "cat pytest.log",
        "type pytest.log",
        "pytest --collect-only",
        "pytest --help",
        "pytest --version",
        "pytest --setup-only",
        "pytest --setup-plan",
        "pytest -q > pytest.log",
        "pytest -q | tee pytest.log",
        "pytest -q && echo done",
        "pytest -q || true",
        "pytest -q; echo done",
        "pytest -q $(echo tests/test_parser.py)",
        'pytest -k "`echo owned`"',
    ],
)
def test_classifier_rejects_spoofs_non_execution_modes_and_shell_control(command):
    assert classify_pytest_invocation(command) is None


def test_inspection_receipt_cannot_imply_execution():
    receipt = EvidenceGatheringReceipt(
        state=EvidenceGatheringState.INSPECTED,
        sources=["recent_events", "workspace_snapshot"],
        recent_events="inspected",
        workspace_snapshot="inspected",
        claim_count=1,
        reason="bounded_existing_evidence_only",
    )
    assert receipt.state == EvidenceGatheringState.INSPECTED
    assert receipt.execution is None

    execution = VerificationExecutionReceipt(
        backend=VerificationBackendKind.SANDBOX,
        policy_verdict=PolicyVerdict.ALLOW,
        source_event_id="pytest_1",
        observed_at=datetime.now(UTC),
        argv=["python", "-m", "pytest", "-q"],
        cwd="C:/workspace",
        process_started=True,
        exit_code=0,
        result=VerificationExecutionResult.PASSED,
    )
    with pytest.raises(ValidationError, match="only executed evidence"):
        EvidenceGatheringReceipt(
            state=EvidenceGatheringState.INSPECTED,
            execution=execution,
        )


def test_attempted_receipt_requires_probe_and_never_claims_terminal_execution():
    receipt = EvidenceGatheringReceipt(
        state=EvidenceGatheringState.ATTEMPTED,
        probe=_probe(),
        sources=["harness_verification_request"],
        reason="awaiting_matching_harness_result",
    )
    assert receipt.execution is None
    with pytest.raises(ValidationError, match="requires a typed probe"):
        EvidenceGatheringReceipt(state=EvidenceGatheringState.ATTEMPTED)


def test_executed_receipt_requires_exact_backend_argv_cwd_and_terminal_result():
    execution = VerificationExecutionReceipt(
        backend=VerificationBackendKind.SANDBOX,
        policy_verdict=PolicyVerdict.ALLOW,
        source_event_id="pytest_1",
        observed_at=datetime.now(UTC),
        argv=["python", "-m", "pytest", "-q", "tests/test_parser.py"],
        cwd="C:/workspace",
        process_started=True,
        exit_code=1,
        result=VerificationExecutionResult.FAILED,
        output="FAILED tests/test_parser.py::test_nested",
        failure_node="tests/test_parser.py::test_nested",
    )
    receipt = EvidenceGatheringReceipt(
        state=EvidenceGatheringState.EXECUTED,
        probe=_probe(),
        execution=execution,
        sources=["sandbox"],
    )
    assert receipt.execution is not None
    assert receipt.execution.result == VerificationExecutionResult.FAILED

    with pytest.raises(ValidationError, match="requires an exact cwd"):
        VerificationExecutionReceipt(
            backend=VerificationBackendKind.SANDBOX,
            policy_verdict=PolicyVerdict.ALLOW,
            source_event_id="pytest_1",
            observed_at=datetime.now(UTC),
            result=VerificationExecutionResult.ERROR,
        )
    with pytest.raises(ValidationError, match="nonzero terminal exit"):
        VerificationExecutionReceipt(
            backend=VerificationBackendKind.HARNESS,
            policy_verdict=PolicyVerdict.ALLOW,
            source_event_id="pytest_1",
            observed_at=datetime.now(UTC),
            observed_command="pytest",
            cwd="C:/workspace",
            process_started=True,
            exit_code=0,
            result=VerificationExecutionResult.FAILED,
        )


def test_executed_pytest_receipt_is_bound_to_probe_cwd_and_scope():
    full_execution = VerificationExecutionReceipt(
        backend=VerificationBackendKind.HARNESS,
        policy_verdict=PolicyVerdict.ALLOW,
        source_event_id="pytest_1",
        observed_at=datetime.now(UTC),
        observed_command="pytest -q",
        cwd="C:/workspace",
        process_started=True,
        exit_code=0,
        result=VerificationExecutionResult.PASSED,
    )
    full_receipt = EvidenceGatheringReceipt(
        state=EvidenceGatheringState.EXECUTED,
        probe=_probe(relative_targets=[]),
        execution=full_execution,
    )
    assert full_receipt.execution.source_event_id == "pytest_1"

    with pytest.raises(ValidationError, match="exact typed probe"):
        EvidenceGatheringReceipt(
            state=EvidenceGatheringState.EXECUTED,
            probe=_probe(),
            execution=full_execution,
        )
    with pytest.raises(ValidationError, match="cwd must match"):
        EvidenceGatheringReceipt(
            state=EvidenceGatheringState.EXECUTED,
            probe=_probe(relative_targets=[], cwd="C:/other"),
            execution=full_execution,
        )


def test_targeted_receipt_requires_exact_targets_without_selector_flags():
    execution = VerificationExecutionReceipt(
        backend=VerificationBackendKind.HARNESS,
        policy_verdict=PolicyVerdict.ALLOW,
        source_event_id="pytest_1",
        observed_at=datetime.now(UTC),
        observed_command="pytest -q tests/test_parser.py",
        cwd="C:/workspace",
        process_started=True,
        exit_code=0,
        result=VerificationExecutionResult.PASSED,
    )
    receipt = EvidenceGatheringReceipt(
        state=EvidenceGatheringState.EXECUTED,
        probe=_probe(),
        execution=execution,
    )
    assert receipt.execution.source_event_id == "pytest_1"

    for command in (
        "pytest -q tests/test_other.py",
        "pytest -q -k nested tests/test_parser.py",
        "pytest -q tests/test_parser.py tests/test_other.py",
    ):
        mismatched = execution.model_copy(update={"observed_command": command})
        with pytest.raises(ValidationError, match="exact typed probe"):
            EvidenceGatheringReceipt(
                state=EvidenceGatheringState.EXECUTED,
                probe=_probe(),
                execution=mismatched,
            )


def test_execution_receipt_requires_timezone_aware_observation_time():
    with pytest.raises(ValidationError, match="timezone-aware"):
        VerificationExecutionReceipt(
            backend=VerificationBackendKind.HARNESS,
            policy_verdict=PolicyVerdict.ALLOW,
            source_event_id="pytest_1",
            observed_at=datetime.now(),
            observed_command="pytest -q",
            cwd="C:/workspace",
            result=VerificationExecutionResult.ERROR,
        )


def test_unavailable_backend_cannot_claim_process_execution():
    receipt = VerificationExecutionReceipt(
        backend=VerificationBackendKind.UNAVAILABLE,
        policy_verdict=PolicyVerdict.DENY,
        source_event_id="stop_1",
        observed_at=datetime.now(UTC),
        result=VerificationExecutionResult.UNAVAILABLE,
    )
    assert receipt.process_started is False

    with pytest.raises(ValidationError, match="cannot claim process execution"):
        VerificationExecutionReceipt(
            backend=VerificationBackendKind.UNAVAILABLE,
            policy_verdict=PolicyVerdict.DENY,
            source_event_id="stop_1",
            observed_at=datetime.now(UTC),
            argv=["pytest"],
            cwd="C:/workspace",
            process_started=True,
            result=VerificationExecutionResult.UNAVAILABLE,
        )


def test_executed_file_count_receipt_rejects_pytest_invocation():
    probe = _probe(kind=VerificationProbeKind.FILE_COUNT, relative_targets=["report.txt"])
    execution = VerificationExecutionReceipt(
        backend=VerificationBackendKind.HARNESS,
        policy_verdict=PolicyVerdict.ALLOW,
        source_event_id="count_1",
        observed_at=datetime.now(UTC),
        observed_command="python scripts/count_files.py report.txt",
        cwd="C:/workspace",
        process_started=True,
        exit_code=0,
        result=VerificationExecutionResult.PASSED,
        output="1",
    )
    receipt = EvidenceGatheringReceipt(
        state=EvidenceGatheringState.EXECUTED,
        probe=probe,
        execution=execution,
        sources=["harness_execution"],
    )
    assert receipt.probe.kind == VerificationProbeKind.FILE_COUNT
    with pytest.raises(ValidationError, match="cannot close on a pytest invocation"):
        EvidenceGatheringReceipt(
            state=EvidenceGatheringState.EXECUTED,
            probe=probe,
            execution=execution.model_copy(update={"observed_command": "pytest -q"}),
            sources=["harness_execution"],
        )
