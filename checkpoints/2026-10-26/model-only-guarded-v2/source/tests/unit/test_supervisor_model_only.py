"""Local actual-SDK/authored-model tests, not provider or autonomous benchmarks."""

import socket
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pex_bridge.agentcore import SupervisorRouter
from pex_bridge.config import Settings
from pex_protocol.actions import InterventionType
from pex_protocol.enums import EventType
from pex_protocol.supervisor import SupervisorRequest, supervisor_request_digest
from pex_supervisor import loop, model_only_transport
from pex_supervisor.strict_usage import validated_sdk_usage
from strands.types.exceptions import ModelThrottledException

from tests.model_only_support import AuthoredSupervisorModel
from tests.unit.test_supervisor_loop import _request

_PRODUCTION_ADMISSION = model_only_transport.qualified


@pytest.fixture(autouse=True)
def no_network_or_ambient_model(monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("forbidden call")
        raise AssertionError("local authored-model test attempted a network call")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(loop, "load_supervisor_model", forbidden)
    monkeypatch.delenv("PEX_FORCE_LLM", raising=False)
    # Test-only dependency injection; production admission refuses every model.
    monkeypatch.setattr(
        model_only_transport, "qualified", lambda model: type(model) is AuthoredSupervisorModel
    )
    yield
    assert attempts == [], "even caught network/model-loader attempts invalidate this test"


def request():
    value = _request(0.95)
    value.supervisor_decision_mode = "supervisor_model_only"
    value.scores.features["verification"] = {
        "status": "acceptance_gap",
        "acceptance_status": "unsatisfied",
    }
    return value


def test_default_request_digest_and_serialization_stay_unchanged():
    default = _request(0.95)
    old = default.model_dump(mode="json")
    assert "supervisor_decision_mode" not in old
    assert SupervisorRequest.model_validate(old).model_dump(mode="json") == old
    before = supervisor_request_digest(default)
    default.supervisor_decision_mode = "supervisor_model_only"
    assert supervisor_request_digest(default) != before
    restored = SupervisorRequest.model_validate(default.model_dump(mode="json"))
    assert restored.supervisor_decision_mode == "supervisor_model_only"


def test_missing_model_and_force_flag_never_load_or_nudge(monkeypatch):
    monkeypatch.setenv("PEX_FORCE_LLM", "1")
    for entry in (loop.decide, loop.run_strands):
        result = entry(request())
        assert result.action.type == InterventionType.NOOP
        assert result.used_llm is False
        assert result.inference_status == "not_attempted"
    quiet = request()
    quiet.event.event_type = EventType.COMPACTION
    model = AuthoredSupervisorModel()
    assert loop.decide(quiet, model=model).action.type == InterventionType.NOOP
    assert model.calls == 0


def test_model_only_actual_sdk_uses_observed_evidence_and_two_independent_agents():
    model = AuthoredSupervisorModel()
    result = loop.decide(request(), model=model)
    assert result.action.type == InterventionType.SEND_NUDGE, result.model_dump()
    assert result.inference_status == "completed"
    assert result.usage_validated is True
    assert model.calls == result.model_call_count == 4
    assert (result.input_tokens, result.output_tokens) == (80, 40)
    assert result.independent_verifier.authorizes_intervention()
    assert result.local_invocation_id != result.independent_verifier.invocation_id
    assert result.action.payload["text"] == (
        "Inspect the unresolved acceptance evidence, then choose your own next step."
    )


@pytest.mark.parametrize("action", ["NOOP", "REQUEST_VERIFICATION"])
def test_model_noop_or_scripted_probe_never_becomes_feedback(action):
    model = AuthoredSupervisorModel(action=action)
    result = loop.decide(request(), model=model)
    assert result.action.type == InterventionType.NOOP
    assert model.calls == 2
    assert result.independent_verifier is None


@pytest.mark.parametrize("bad", [True, "20", 20.5, -1, float("nan"), "missing"])
@pytest.mark.parametrize("call", [1, 2, 3, 4])
def test_invalid_or_missing_sdk_usage_fails_closed_in_every_round(bad, call):
    model = AuthoredSupervisorModel(bad_usage=bad, bad_call=call)
    result = loop.decide(request(), model=model)
    assert result.action.type == InterventionType.NOOP
    assert result.inference_status == "failed"
    assert model.calls == call  # Neither SDK retry nor verifier replacement.


def test_sdk_throttling_is_not_retried():
    model = AuthoredSupervisorModel(failure=ModelThrottledException("authored failure"))
    result = loop.decide(request(), model=model)
    assert result.action.type == InterventionType.NOOP
    assert result.inference_status == "failed"
    assert model.calls == 1


def test_paused_hard_veto_never_calls_model():
    value = request()
    value.session.supervision_paused = True
    model = AuthoredSupervisorModel()
    assert loop.decide(value, model=model).action.type == InterventionType.NOOP
    assert model.calls == 0


def test_deterministic_candidate_cannot_replace_model_noop_or_verifier_failure():
    value = request()
    deterministic = loop._action_from_proposal(
        value,
        {"type": "REQUEST_VERIFICATION", "rationale": "test", "evidence": ["test"]},
    )
    with patch.object(loop, "plan_deterministic", return_value=deterministic):
        result = loop.decide(value, model=AuthoredSupervisorModel(action="NOOP"))
        assert result.action.type == InterventionType.NOOP
        failed = loop.decide(value, model=AuthoredSupervisorModel(bad_usage=True, bad_call=3))
        assert failed.action.type == InterventionType.NOOP
        assert "verification_request_preserved" not in failed.traces


def test_sdk_cycle_cannot_hide_missing_usage_behind_positive_aggregate():
    good = {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30}
    metrics = SimpleNamespace(
        cycle_count=2,
        accumulated_usage=good,
        agent_invocations=[
            SimpleNamespace(
                usage=good,
                cycles=[SimpleNamespace(usage=good), SimpleNamespace(usage={})],
            )
        ],
    )
    assert validated_sdk_usage(SimpleNamespace(metrics=metrics)) is None


def test_cache_usage_must_reconcile_at_every_level():
    good = {"inputTokens": 20, "outputTokens": 10, "totalTokens": 30, "cacheReadInputTokens": 7}
    metrics = SimpleNamespace(
        cycle_count=1,
        accumulated_usage=dict(good),
        agent_invocations=[
            SimpleNamespace(usage=dict(good), cycles=[SimpleNamespace(usage=dict(good))])
        ],
    )
    result = SimpleNamespace(metrics=metrics)
    assert validated_sdk_usage(result) == (1, 20, 10)
    metrics.agent_invocations[0].cycles[0].usage["cacheReadInputTokens"] = 6
    assert validated_sdk_usage(result) is None


def test_model_only_remote_configuration_refused(tmp_path):
    with pytest.raises(ValueError, match="requires the local"):
        Settings.for_test(
            require_auth=False,
            home=tmp_path,
            supervisor_mode="hybrid",
            supervisor_decision_mode="supervisor_model_only",
        )
    settings = Settings.for_test(
        require_auth=False, home=tmp_path, supervisor_decision_mode="supervisor_model_only"
    )
    router = SupervisorRouter(settings)
    assert router.can_attempt_semantic(None) is False


def test_model_only_does_not_expose_unqualified_remote_evidence():
    from pex_supervisor.evidence_tools import select_evidence_tool_names

    value = request()
    value.scores.features["public_claims"] = True
    assert not {"web_search", "scrape_url"} & set(select_evidence_tool_names(value))
    value.supervisor_decision_mode = "default"
    assert {"web_search", "scrape_url"} <= set(select_evidence_tool_names(value))


@pytest.mark.parametrize("provider_kind", ["bedrock", "openai"])
def test_production_admission_refuses_standard_sdk_provider_before_any_call(
    monkeypatch, tmp_path, provider_kind
):
    from importlib import import_module

    from pex_supervisor.strict_model import UsageCheckedModel

    module, name = (
        ("strands.models.bedrock", "BedrockModel")
        if provider_kind == "bedrock"
        else ("strands.models.openai", "OpenAIModel")
    )
    provider_type = getattr(import_module(module), name)
    monkeypatch.setattr(model_only_transport, "qualified", _PRODUCTION_ADMISSION)
    # Allocate the real SDK adapter type without constructing a client, reading
    # credentials, or requesting metadata. Admission must precede all of that.
    provider = object.__new__(provider_type)
    calls = []

    async def forbidden_stream(*args, **kwargs):
        calls.append("stream")
        raise AssertionError("unqualified provider invoked")
        yield

    monkeypatch.setattr(provider_type, "stream", forbidden_stream)
    monkeypatch.setenv("PEX_FORCE_LLM", "1")
    for entry in (loop.decide, loop.run_strands):
        result = entry(request(), model=provider)
        assert result.action.type == InterventionType.NOOP
        assert result.diagnosis == "model_only_transport_unqualified"
        assert result.inference_status == "not_attempted"
        assert result.used_llm is False
    with pytest.raises(ValueError, match="model_only_transport_unqualified"):
        UsageCheckedModel(provider)
    settings = Settings.for_test(
        require_auth=False, home=tmp_path, supervisor_decision_mode="supervisor_model_only"
    )
    assert SupervisorRouter(settings).can_attempt_semantic(provider) is False
    assert _PRODUCTION_ADMISSION(AuthoredSupervisorModel()) is False
    assert calls == []


def test_default_mode_still_invokes_authored_model_under_production_admission(monkeypatch):
    monkeypatch.setattr(model_only_transport, "qualified", _PRODUCTION_ADMISSION)
    value = request()
    value.supervisor_decision_mode = "default"
    model = AuthoredSupervisorModel()
    result = loop.decide(value, model=model)
    assert result.action.type == InterventionType.SEND_NUDGE
    assert model.calls == 4


@pytest.mark.asyncio
async def test_router_mode_cannot_be_downgraded_by_default_request(tmp_path):
    settings = Settings.for_test(
        require_auth=False, home=tmp_path, supervisor_decision_mode="supervisor_model_only"
    )
    value = request()
    value.supervisor_decision_mode = "default"
    model = AuthoredSupervisorModel()
    result = await SupervisorRouter(settings).decide(value, local_model=model)
    assert result.action.type == InterventionType.NOOP
    assert result.diagnosis == "supervisor_decision_mode_changed"
    assert model.calls == 0


@pytest.mark.asyncio
async def test_sdk_wrapper_rechecks_admission_before_stream(monkeypatch):
    from pex_supervisor.strict_model import InvalidModelUsage, UsageCheckedModel

    model = AuthoredSupervisorModel()
    checked = UsageCheckedModel(model)
    monkeypatch.setattr(model_only_transport, "qualified", _PRODUCTION_ADMISSION)
    with pytest.raises(InvalidModelUsage, match="model_only_transport_unqualified"):
        async for _ in checked.stream([]):
            raise AssertionError("unqualified stream yielded")
    assert model.calls == 0


def test_app_preparation_refuses_before_secret_read_or_provider_construction(monkeypatch, tmp_path):
    from pex_bridge import app as bridge_app
    from pex_supervisor import providers
    from pex_supervisor.model_only_transport import ModelOnlyTransportUnqualified

    settings = Settings.for_test(
        require_auth=False, home=tmp_path, supervisor_decision_mode="supervisor_model_only"
    )
    monkeypatch.setattr(bridge_app.state, "settings", settings)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("credential or model preparation")
        raise AssertionError("model-only preparation crossed the admission boundary")

    monkeypatch.setattr(providers, "load_supervisor_model", forbidden)
    monkeypatch.setattr(bridge_app, "_resolve_choice_secret", forbidden)
    for prepare in (
        lambda: bridge_app._prepare_saved_supervisor_choice(None),
        lambda: bridge_app._activate_supervisor_choice(None),
        lambda: bridge_app._prepare_supervisor_config(None, None, None),
    ):
        with pytest.raises(ModelOnlyTransportUnqualified):
            prepare()
    assert calls == []


@pytest.mark.asyncio
async def test_saved_activation_records_unsupported_without_provider_work(monkeypatch, tmp_path):
    from pex_bridge import app as bridge_app

    settings = Settings.for_test(
        require_auth=False, home=tmp_path, supervisor_decision_mode="supervisor_model_only"
    )
    monkeypatch.setattr(bridge_app.state, "settings", settings)
    monkeypatch.setattr(bridge_app.state, "pipeline", SimpleNamespace(model=object()))
    monkeypatch.setattr(bridge_app.state, "supervisor_api_key_present", True)
    monkeypatch.setattr(bridge_app.state, "supervisor_credential_status", "configured")
    monkeypatch.setattr(bridge_app.state, "supervisor_error", None)
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("preparation")
        raise AssertionError("activation must not schedule provider preparation")

    monkeypatch.setattr(bridge_app, "_prepare_saved_supervisor_choice", forbidden)
    await bridge_app._activate_saved_supervisor_choice(None, 0)
    assert bridge_app.state.pipeline.model is None
    assert bridge_app.state.supervisor_error == "ModelOnlyTransportUnqualified"
    assert bridge_app.state.supervisor_api_key_present is False
    assert calls == []


@pytest.mark.asyncio
async def test_configuration_endpoint_reports_unsupported_before_preparation(monkeypatch, tmp_path):
    from fastapi import HTTPException
    from pex_bridge import app as bridge_app

    monkeypatch.setattr(
        bridge_app.state,
        "settings",
        Settings.for_test(
            require_auth=False, home=tmp_path, supervisor_decision_mode="supervisor_model_only"
        ),
    )
    app = bridge_app.create_app()
    endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/v1/supervisor"
        and "PATCH" in getattr(route, "methods", set())
    )
    with pytest.raises(HTTPException) as caught:
        await endpoint(bridge_app.SupervisorIn(), None)
    assert caught.value.status_code == 409
    assert caught.value.detail == "model_only_transport_unqualified"


def test_remote_request_is_refused_before_runtime_model_loading(monkeypatch):
    from pex_supervisor import runtime

    from tests.unit.test_agentcore_runtime import _payload, _request

    value = _request()
    value.supervisor_decision_mode = "supervisor_model_only"
    calls = []

    def forbidden(*args, **kwargs):
        calls.append("runtime model")
        raise AssertionError("remote model-only request must not load a model")

    monkeypatch.setattr(runtime, "_runtime_model", forbidden)
    with pytest.raises(ValueError, match="model_only_remote_transport_unqualified"):
        runtime.handle_payload(_payload(value))
    assert calls == []
