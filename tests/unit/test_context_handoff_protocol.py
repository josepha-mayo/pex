from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pex_protocol import ContextHandoffRequest, HandoffAssimilationEvidence
from pex_protocol.enums import EventType, HarnessType
from pydantic import ValidationError


def _request(**changes: object) -> ContextHandoffRequest:
    values: dict[str, object] = {
        "idempotency_key": "handoff-request-0001",
        "target_session_id": "codex:thread-123",
    }
    values.update(changes)
    return ContextHandoffRequest.model_validate(values)


def test_context_handoff_request_is_frozen_closed_and_has_bounded_default() -> None:
    request = _request()

    assert request.target_session_id == "codex:thread-123"
    assert request.token_budget == 2_000
    with pytest.raises(ValidationError, match="frozen"):
        request.target_session_id = "cursor:other"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ContextHandoffRequest.model_validate(
            {**request.model_dump(mode="json"), "source_session_id": "caller-controlled"}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"idempotency_key": "short"},
        {"idempotency_key": "unsafe key value"},
        {"idempotency_key": "unsafe/key"},
        {"idempotency_key": "x" * 129},
        {"target_session_id": ""},
        {"target_session_id": " leading"},
        {"target_session_id": "trailing "},
        {"target_session_id": "session\nother"},
        {"target_session_id": "session\u200bother"},
        {"target_session_id": "x" * 513},
        {"token_budget": 255},
        {"token_budget": 12_001},
        {"token_budget": "2000"},
    ],
)
def test_context_handoff_request_rejects_unsafe_unbounded_or_coerced_values(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _request(**changes)


@pytest.mark.parametrize(
    "payload",
    [
        {"target_session_id": "codex:thread-123"},
        {"idempotency_key": "handoff-request-0001"},
    ],
)
def test_context_handoff_request_requires_caller_key_and_target(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ContextHandoffRequest.model_validate(payload)


def test_context_handoff_request_schema_exposes_exact_contract() -> None:
    schema = ContextHandoffRequest.model_json_schema()
    properties = schema["properties"]

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"idempotency_key", "target_session_id"}
    assert properties["idempotency_key"]["minLength"] == 8
    assert properties["idempotency_key"]["maxLength"] == 128
    assert properties["idempotency_key"]["pattern"] == (
        r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    assert properties["target_session_id"]["minLength"] == 1
    assert properties["target_session_id"]["maxLength"] == 512
    assert properties["token_budget"]["minimum"] == 256
    assert properties["token_budget"]["maximum"] == 12_000
    assert properties["token_budget"]["default"] == 2_000


def _assimilation_evidence(**changes: object) -> HandoffAssimilationEvidence:
    started = datetime(2026, 9, 1, 12, tzinfo=UTC)
    values: dict[str, object] = {
        "evidence_id": "handoff_evidence_0001",
        "effect_id": "effect_0001",
        "handoff_intervention_id": "intervention_0001",
        "bundle_digest": "a" * 64,
        "dispatch_started_at": started,
        "dispatch_version": 2,
        "dispatch_target_accept_seq_through": 41,
        "source_session_id": "cursor:source",
        "source_vendor_session_id": "source",
        "source_harness_type": HarnessType.CURSOR,
        "target_session_id": "codex:target",
        "target_vendor_session_id": "target",
        "target_harness_type": HarnessType.CODEX,
        "source_project_id": "C:/work/source",
        "target_project_id": "C:/work/target",
        "source_project_binding": "identity:project",
        "target_project_binding": "identity:project",
        "goal_project_binding": "identity:project",
        "goal_id": "goal_0001",
        "target_event_id": "event_0001",
        "target_event_type": EventType.FILE_READ,
        "target_event_accept_seq": 42,
        "target_mutation_id": None,
        "evidence_kind": "artifact_read",
        "evidence_strength": "behavioral",
        "matched_context_item_ids": ("context_0001",),
        "matched_artifact_paths": ("artifacts/prepared.parquet",),
        "target_event_ts": started + timedelta(seconds=1),
        "observed_at": started + timedelta(seconds=2),
    }
    values.update(changes)
    return HandoffAssimilationEvidence.model_validate(values)


def test_handoff_assimilation_evidence_is_closed_frozen_and_never_proof() -> None:
    evidence = _assimilation_evidence()

    assert evidence.verified is False
    assert evidence.assimilation_proven is False
    assert evidence.model_dump(mode="json", by_alias=True)["schema"] == (
        "pex.handoff-assimilation-evidence.v1"
    )
    with pytest.raises(ValidationError, match="frozen"):
        evidence.verified = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HandoffAssimilationEvidence.model_validate(
            {**evidence.model_dump(mode="python", by_alias=True), "understood": True}
        )
    with pytest.raises(ValidationError):
        _assimilation_evidence(verified=True)
    with pytest.raises(ValidationError):
        _assimilation_evidence(assimilation_proven=True)


@pytest.mark.parametrize(
    "changes",
    [
        {"evidence_strength": "self_attested"},
        {"matched_artifact_paths": ()},
        {"target_event_accept_seq": None},
        {"target_mutation_id": "mutation_0001"},
        {"matched_context_item_ids": ("context_0001", "context_0001")},
        {
            "matched_artifact_paths": (
                "artifacts/prepared.parquet",
                "artifacts/prepared.parquet",
            )
        },
    ],
)
def test_artifact_assimilation_evidence_rejects_ambiguous_shapes(
    changes: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        _assimilation_evidence(**changes)


def test_target_acknowledgement_is_explicitly_self_attested() -> None:
    acknowledgement = _assimilation_evidence(
        target_event_type=EventType.STATUS,
        target_event_accept_seq=None,
        target_mutation_id="mutation_0001",
        evidence_kind="target_acknowledgement",
        evidence_strength="self_attested",
        matched_artifact_paths=(),
    )

    assert acknowledgement.evidence_strength == "self_attested"
    assert acknowledgement.verified is False
    with pytest.raises(ValidationError):
        _assimilation_evidence(
            target_event_type=EventType.STATUS,
            target_event_accept_seq=None,
            target_mutation_id="mutation_0001",
            evidence_kind="target_acknowledgement",
            evidence_strength="behavioral",
            matched_artifact_paths=(),
        )
