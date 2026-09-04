from __future__ import annotations

import pytest
from pex_protocol.context import ClaimVerificationRequest
from pydantic import ValidationError


def test_claim_verification_request_is_frozen_and_forbids_extras() -> None:
    request = ClaimVerificationRequest(
        idempotency_key="verify-claim-0001",
        claim="All tests passed.",
    )

    assert request.claim == "All tests passed."
    with pytest.raises(ValidationError):
        request.claim = "Changed after validation."
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ClaimVerificationRequest.model_validate(
            {
                "idempotency_key": "verify-claim-0001",
                "claim": "All tests passed.",
                "session_id": "caller-controlled-binding",
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("idempotency_key", "short"),
        ("idempotency_key", "unsafe key with spaces"),
        ("idempotency_key", "a" * 129),
        ("claim", ""),
        ("claim", "x" * 4_001),
    ],
)
def test_claim_verification_request_enforces_closed_bounds(
    field: str,
    value: str,
) -> None:
    payload = {
        "idempotency_key": "verify-claim-0001",
        "claim": "All tests passed.",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        ClaimVerificationRequest.model_validate(payload)


def test_claim_verification_json_schema_exposes_exact_resource_bounds() -> None:
    schema = ClaimVerificationRequest.model_json_schema()

    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"idempotency_key", "claim"}
    assert schema["properties"]["idempotency_key"]["minLength"] == 8
    assert schema["properties"]["idempotency_key"]["maxLength"] == 128
    assert schema["properties"]["claim"]["minLength"] == 1
    assert schema["properties"]["claim"]["maxLength"] == 4_000
