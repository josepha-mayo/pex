from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from pex_protocol.supervisor import (
    IndependentVerifierReceipt,
    SupervisorEvidenceObservation,
    SupervisorResult,
    supervisor_request_digest,
    validate_evidence_observation_bindings,
)
from pex_supervisor.evidence_observations import (
    EvidenceObservationCollector,
    canonical_arguments,
)
from pex_supervisor.planner import plan_deterministic
from test_supervisor_loop import _request


def _collector(stage: str = "main") -> EvidenceObservationCollector:
    return EvidenceObservationCollector(
        _request(0.2),
        stage=stage,  # type: ignore[arg-type]
        invocation_id=f"{stage}-invocation",
    )


def test_collector_returns_and_hashes_exact_receipt_with_reserved_id_authority():
    collector = _collector()
    output = collector.record(
        tool_name="inspect_workspace",
        arguments_json=canonical_arguments({"path": "a\\\"b"}),
        value={"pex_observation_id": "pexobs_" + "0" * 32, "ok": True},
    )

    observation = collector.observations[0]
    assert json.loads(output)["pex_observation_id"] == observation.observation_id
    assert observation.output == output
    assert observation.output_sha256 == hashlib.sha256(output.encode()).hexdigest()
    assert json.loads(observation.arguments_json) == {"path": "a\\\"b"}


def test_final_serialized_tool_payloads_remain_within_byte_bounds():
    collector = _collector()
    arguments = canonical_arguments({"query": ('\\"😀' * 10_000)})
    output = collector.record(
        tool_name="web_search",
        arguments_json=arguments,
        value={"text": '\\"😀' * 20_000},
    )

    assert len(arguments.encode("utf-8")) <= 4_096
    assert len(output.encode("utf-8")) <= 8_000
    assert collector.observations[0].output == output


def test_concurrent_collector_admission_never_exceeds_count_limit():
    collector = _collector()

    def record(index: int) -> str:
        return collector.record(
            tool_name="get_scores",
            arguments_json="{}",
            value={"index": index},
        )

    with ThreadPoolExecutor(max_workers=16) as pool:
        outputs = list(pool.map(record, range(80)))

    assert len(collector.observations) == 24
    assert sum("pex_observation_id" in item for item in outputs) == 24
    assert all(
        item == '{"error":"evidence_observation_limit_reached"}'
        for item in outputs
        if "pex_observation_id" not in item
    )


def test_aggregate_serialized_receipt_budget_refuses_before_exposing_evidence():
    collector = _collector()
    arguments = canonical_arguments({"query": '\\"😀' * 10_000})
    outputs = [
        collector.record(
            tool_name="web_search",
            arguments_json=arguments,
            value={"text": '\\"😀' * 20_000, "sequence": index},
        )
        for index in range(24)
    ]
    disclosed_ids = [
        parsed["pex_observation_id"]
        for output in outputs
        if "pex_observation_id" in (parsed := json.loads(output))
    ]

    assert len(collector.observations) < 24
    assert any(output == '{"error":"evidence_observation_limit_reached"}' for output in outputs)
    assert disclosed_ids == [item.observation_id for item in collector.observations]
    assert sum(
        len(item.model_dump_json().encode("utf-8"))
        for item in collector.observations
    ) <= 128 * 1024
    first = collector.observations[0]
    validate_evidence_observation_bindings(
        collector.observations,
        disclosed_ids,
        stage="main",
        request_digest=first.request_digest,
        session_id=first.session_id,
        goal_id=first.goal_id,
        event_id=first.event_id,
        invocation_id=first.invocation_id,
    )


def test_collector_freezes_authority_bindings_before_mutable_request_changes():
    request = _request(0.2)
    collector = EvidenceObservationCollector(
        request,
        stage="main",
        invocation_id="main-invocation",
    )
    original_session = request.session.id
    original_event = request.event.event_id
    request.session.id = "mutated-session"
    request.event.event_id = "mutated-event"

    collector.record(tool_name="get_scores", arguments_json="{}", value={"ok": True})

    observation = collector.observations[0]
    assert observation.session_id == original_session
    assert observation.event_id == original_event


def test_protocol_roundtrip_accepts_field_name_schema_dump():
    request = _request(0.2)
    collector = EvidenceObservationCollector(
        request,
        stage="main",
        invocation_id="main-invocation",
    )
    output = collector.record(
        tool_name="get_scores",
        arguments_json="{}",
        value={"score": 0.2},
    )
    observation = collector.observations[0]
    result = SupervisorResult(
        action=plan_deterministic(request),
        local_invocation_id="main-invocation",
        evidence_observations=[observation],
        evidence_refs=[observation.observation_id],
    )

    restored = SupervisorResult.model_validate(result.model_dump(mode="json"))
    assert restored.evidence_observations[0].output == output


def test_verifier_authority_requires_resolved_observation_not_tool_name_or_prose():
    collector = _collector("verifier")
    collector.record(
        tool_name="get_recent_events",
        arguments_json="{}",
        value={"events": []},
    )
    observation = collector.observations[0]
    base = {
        "approved": True,
        "status": "approved",
        "rationale": "checked",
        "evidence": ["model prose"],
        "evidence_tools": ["get_recent_events"],
        "model_call_count": 1,
        "invocation_id": "verifier-invocation",
        "evidence_observations": [observation],
    }

    assert IndependentVerifierReceipt(**base).authorizes_intervention() is False
    receipt = IndependentVerifierReceipt(
        **base,
        evidence_refs=[observation.observation_id],
    )
    assert receipt.authorizes_intervention() is True


def test_protocol_rejects_foreign_binding_and_output_id_spoof():
    collector = _collector()
    collector.record(tool_name="get_scores", arguments_json="{}", value={"ok": True})
    observation = collector.observations[0]

    with pytest.raises(ValueError, match="authority binding"):
        validate_evidence_observation_bindings(
            [observation],
            [observation.observation_id],
            stage="main",
            request_digest=observation.request_digest,
            session_id="foreign-session",
            goal_id=observation.goal_id,
            event_id=observation.event_id,
            invocation_id=observation.invocation_id,
        )

    payload = observation.model_dump(mode="json")
    payload["output"] = json.dumps(
        {"pex_observation_id": "pexobs_" + "0" * 32},
        separators=(",", ":"),
    )
    payload["output_sha256"] = hashlib.sha256(payload["output"].encode()).hexdigest()
    with pytest.raises(ValueError, match="bind its observation"):
        SupervisorEvidenceObservation.model_validate(payload)


@pytest.mark.parametrize("hostile", [float("inf"), float("nan")])
def test_request_digest_rejects_nonfinite_values_without_lossy_normalization(hostile):
    request = _request(0.2)
    request.scores.features["hostile"] = hostile

    with pytest.raises(ValueError, match="exact canonical JSON"):
        supervisor_request_digest(request)


def test_request_digest_rejects_cycles_without_lossy_markers():
    request = _request(0.2)
    cycle: dict[str, object] = {}
    cycle["self"] = cycle
    request.scores.features["cycle"] = cycle

    with pytest.raises(ValueError, match="exact canonical JSON"):
        supervisor_request_digest(request)


def test_observation_rejects_overflowed_nonfinite_json_number():
    collector = _collector()
    collector.record(tool_name="get_scores", arguments_json="{}", value={"ok": True})
    payload = collector.observations[0].model_dump(mode="json")
    payload["output"] = (
        '{"pex_observation_id":"'
        + payload["observation_id"]
        + '","value":1e999}'
    )
    payload["output_sha256"] = hashlib.sha256(payload["output"].encode()).hexdigest()

    with pytest.raises(ValueError, match="non-finite JSON number"):
        SupervisorEvidenceObservation.model_validate(payload)
