from __future__ import annotations

import pytest
from pex_protocol import ProgressEvidenceReference, ProgressReport
from pydantic import ValidationError


def _report(**changes) -> ProgressReport:
    values = {
        "idempotency_key": "progress-12345678",
        "summary": "Parser implementation is complete and linked to observed evidence.",
        "evidence_refs": [
            {"type": "event", "id": "evt_123"},
            {"type": "context", "id": "ctx_456"},
        ],
    }
    values.update(changes)
    return ProgressReport.model_validate(values)


def test_progress_report_is_frozen_bounded_and_preserves_evidence_order():
    report = _report()

    assert report.idempotency_key == "progress-12345678"
    assert report.evidence_refs == (
        ProgressEvidenceReference(type="event", id="evt_123"),
        ProgressEvidenceReference(type="context", id="ctx_456"),
    )
    with pytest.raises(ValidationError, match="frozen"):
        report.summary = "mutated"
    with pytest.raises(ValidationError, match="frozen"):
        report.evidence_refs[0].id = "evt_other"


@pytest.mark.parametrize(
    "idempotency_key",
    [
        "short",
        "x" * 129,
        "unsafe key",
        "unsafe/key",
        "unsafe\nkey",
        "évidence-123",
        "-leading-punctuation",
    ],
)
def test_idempotency_key_rejects_out_of_bounds_or_unsafe_values(idempotency_key):
    with pytest.raises(ValidationError):
        _report(idempotency_key=idempotency_key)


def test_summary_and_evidence_count_bounds_are_enforced_without_truncation():
    with pytest.raises(ValidationError):
        _report(summary="")
    with pytest.raises(ValidationError):
        _report(summary="x" * 4_001)
    with pytest.raises(ValidationError):
        _report(evidence_refs=[])
    with pytest.raises(ValidationError):
        _report(
            evidence_refs=[
                {"type": "event", "id": f"evt_{index}"} for index in range(25)
            ]
        )


@pytest.mark.parametrize(
    "reference",
    [
        {"type": "artifact", "id": "evt_123"},
        {"type": "event", "id": ""},
        {"type": "event", "id": "x" * 513},
        {"type": "event", "id": "evt\n123"},
        {"type": "event", "id": " evt_123"},
        {"type": "event", "id": "evt_123", "extra": True},
    ],
)
def test_evidence_reference_rejects_open_types_controls_bounds_and_extras(reference):
    with pytest.raises(ValidationError):
        ProgressEvidenceReference.model_validate(reference)


def test_duplicate_reference_pair_is_rejected_but_same_id_across_types_is_valid():
    duplicate = [
        {"type": "event", "id": "same"},
        {"type": "event", "id": "same"},
    ]
    with pytest.raises(ValidationError, match="unique by type and id"):
        _report(evidence_refs=duplicate)

    report = _report(
        evidence_refs=[
            {"type": "event", "id": "same"},
            {"type": "context", "id": "same"},
        ]
    )
    assert len(report.evidence_refs) == 2


def test_progress_report_rejects_extra_fields():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProgressReport.model_validate(
            {
                **_report().model_dump(mode="json"),
                "unexpected": "not part of the MCP contract",
            }
        )


def test_generated_json_schema_is_closed_and_carries_all_contract_bounds():
    schema = ProgressReport.model_json_schema()
    report_properties = schema["properties"]
    request_schema = report_properties["idempotency_key"]
    summary_schema = report_properties["summary"]
    refs_schema = report_properties["evidence_refs"]
    reference_schema = schema["$defs"]["ProgressEvidenceReference"]

    assert schema["additionalProperties"] is False
    assert request_schema["minLength"] == 8
    assert request_schema["maxLength"] == 128
    assert request_schema["pattern"] == r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    assert summary_schema["minLength"] == 1
    assert summary_schema["maxLength"] == 4_000
    assert refs_schema["minItems"] == 1
    assert refs_schema["maxItems"] == 24
    assert reference_schema["additionalProperties"] is False
    assert reference_schema["properties"]["type"]["enum"] == ["event", "context"]
    assert reference_schema["properties"]["id"]["minLength"] == 1
    assert reference_schema["properties"]["id"]["maxLength"] == 512
