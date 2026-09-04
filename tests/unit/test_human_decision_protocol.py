from __future__ import annotations

import pytest
from pex_protocol import HumanDecisionRequest
from pydantic import ValidationError


def _request(**changes) -> HumanDecisionRequest:
    values = {
        "idempotency_key": "decision-request-0001",
        "question": "Ship the release candidate or keep iterating?",
        "options": ["ship", "iterate"],
        "urgency": "high",
        "context": "The visual gate passed; the clean-clone gate remains open.",
    }
    values.update(changes)
    return HumanDecisionRequest.model_validate(values)


def test_human_decision_request_is_frozen_closed_and_bounded():
    request = _request()

    assert request.options == ("ship", "iterate")
    with pytest.raises(ValidationError, match="frozen"):
        request.question = "changed"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        HumanDecisionRequest.model_validate(
            {**request.model_dump(mode="json"), "unexpected": True}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"idempotency_key": "short"},
        {"idempotency_key": "unsafe key value"},
        {"idempotency_key": "x" * 129},
        {"question": ""},
        {"question": " leading"},
        {"question": "trailing "},
        {"question": "line\nbreak"},
        {"question": "x" * 4_001},
        {"context": "x" * 4_001},
        {"context": "hidden\u200bcontext"},
        {"options": ["same", "SAME"]},
        {"options": ["1", "\u2460"]},
        {"options": ["a", "\uff21"]},
        {"options": ["blank", " "]},
        {"options": ["x" * 501]},
        {"options": [str(index) for index in range(17)]},
        {"urgency": "critical"},
    ],
)
def test_human_decision_request_rejects_ambiguous_or_unbounded_values(changes):
    with pytest.raises(ValidationError):
        _request(**changes)


def test_human_decision_request_schema_carries_nested_bounds():
    schema = HumanDecisionRequest.model_json_schema()
    properties = schema["properties"]

    assert schema["additionalProperties"] is False
    assert properties["idempotency_key"]["minLength"] == 8
    assert properties["idempotency_key"]["maxLength"] == 128
    assert properties["question"]["maxLength"] == 4_000
    assert properties["options"]["maxItems"] == 16
    assert properties["options"]["items"]["minLength"] == 1
    assert properties["options"]["items"]["maxLength"] == 500
    assert properties["urgency"]["enum"] == ["normal", "high", "blocking"]
    assert properties["context"]["maxLength"] == 4_000
