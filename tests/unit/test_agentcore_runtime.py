from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest, SupervisorResult
from pex_supervisor import runtime


def _request() -> SupervisorRequest:
    now = datetime.now(UTC)
    session = HarnessSession(
        id="session_runtime",
        harness_type=HarnessType.CODEX,
        vendor_session_id="vendor_runtime",
        project_id="project_runtime",
        goal_id="goal_runtime",
        status=SessionStatus.STOPPED,
    )
    goal = Goal(
        id="goal_runtime",
        project_id="project_runtime",
        title="Runtime goal",
        objective="Return a typed decision",
        created_at=now,
        updated_at=now,
    )
    event = HarnessEvent(
        event_id="event_runtime",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        event_type=EventType.STOP,
    )
    return SupervisorRequest(session=session, goal=goal, event=event)


def _result(request: SupervisorRequest) -> SupervisorResult:
    return SupervisorResult(
        action=ProposedAction(
            type=InterventionType.NOOP,
            session_id=request.session.id,
            goal_id=request.goal.id,
            rationale="runtime test",
        ),
        used_llm=True,
        runtime="strands-agents",
        inference_status="completed",
        model_call_count=1,
    )


def _payload(request: SupervisorRequest) -> dict:
    return {
        "schema_version": 1,
        "invocation_id": "pexinv_" + "a" * 32,
        "request": request.model_dump(mode="json"),
    }


@pytest.mark.parametrize("version", [True, 1.0, "1", None, False, 2])
def test_runtime_schema_version_is_an_exact_integer_before_model_loading(monkeypatch, version):
    payload = _payload(_request())
    payload["schema_version"] = version
    monkeypatch.setattr(runtime, "_runtime_model", lambda: pytest.fail("must not load model"))
    with pytest.raises(ValueError, match="schema version"):
        runtime.handle_payload(payload)


def test_handle_payload_passes_configured_model_and_returns_versioned_result(monkeypatch):
    request = _request()
    sentinel = object()
    captured = {}

    def fake_decide(seen, model=None, force_llm=False):
        captured.update(request=seen, model=model, force_llm=force_llm)
        return _result(seen)

    monkeypatch.setattr(runtime, "decide", fake_decide)
    response = runtime.handle_payload(_payload(request), model=sentinel)

    assert response["schema_version"] == 1
    assert response["invocation_id"] == "pexinv_" + "a" * 32
    assert response["result"]["runtime"] == "strands-agents"
    assert captured["model"] is sentinel
    assert captured["request"].session.id == request.session.id


def test_handle_payload_loads_runtime_model_when_not_injected(monkeypatch):
    request = _request()
    sentinel = object()
    captured = {}
    monkeypatch.setattr(runtime, "_runtime_model", lambda: sentinel)

    def fake_decide(seen, model=None, force_llm=False):
        captured["model"] = model
        return _result(seen)

    monkeypatch.setattr(runtime, "decide", fake_decide)
    runtime.handle_payload(_payload(request))
    assert captured["model"] is sentinel


def test_agentcore_runtime_requires_an_explicit_constructible_model(monkeypatch):
    runtime._runtime_model.cache_clear()
    monkeypatch.delenv("PEX_SUPERVISOR_PROVIDER", raising=False)
    monkeypatch.delenv("PEX_SUPERVISOR_MODEL", raising=False)
    monkeypatch.setattr(
        runtime,
        "load_supervisor_model",
        lambda: pytest.fail("loader must not guess an AgentCore model"),
    )
    with pytest.raises(RuntimeError, match="explicit PEX_SUPERVISOR_PROVIDER"):
        runtime._runtime_model()

    runtime._runtime_model.cache_clear()
    monkeypatch.setenv("PEX_SUPERVISOR_PROVIDER", "bedrock")
    monkeypatch.setenv("PEX_SUPERVISOR_MODEL", "configured-model")
    monkeypatch.setattr(runtime, "load_supervisor_model", lambda: None)
    with pytest.raises(RuntimeError, match="could not be constructed"):
        runtime._runtime_model()
    runtime._runtime_model.cache_clear()


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"schema_version": 2, "request": {}},
        {"schema_version": 1, "request": {}},
        {
            "schema_version": 1,
            "invocation_id": "bad",
            "request": {},
        },
        {
            "schema_version": 1,
            "invocation_id": "pexinv_" + "a" * 32,
            "request": "bad",
        },
    ],
)
def test_handle_payload_rejects_invalid_contract(payload):
    with pytest.raises(ValueError):
        runtime.handle_payload(payload, model=None)


def test_handle_payload_rejects_oversized_input_before_decision(monkeypatch):
    request = _request()
    payload = _payload(request)
    payload["ignored_padding"] = "x" * runtime.MAX_RUNTIME_REQUEST_BYTES
    monkeypatch.setattr(
        runtime,
        "decide",
        lambda *args, **kwargs: pytest.fail("oversized input must not reach the model"),
    )

    with pytest.raises(ValueError, match="runtime byte limit"):
        runtime.handle_payload(payload, model=object())


@pytest.mark.parametrize("binding", ["event_harness", "event_project", "recent_harness"])
def test_runtime_rejects_cross_boundary_event_bindings(monkeypatch, binding):
    request = _request()
    if binding == "event_harness":
        request.event.harness_type = HarnessType.CURSOR
    elif binding == "event_project":
        request.event.project_id = "another-project"
    else:
        recent = request.event.model_copy(deep=True)
        recent.event_id = "recent-cross-harness"
        recent.harness_type = HarnessType.CURSOR
        request.recent_events = [recent]
    monkeypatch.setattr(
        runtime,
        "decide",
        lambda *args, **kwargs: pytest.fail("invalid binding must not reach the model"),
    )

    with pytest.raises(ValueError, match="failed protocol validation"):
        runtime.handle_payload(_payload(request), model=object())


def test_runtime_rejects_goal_when_session_has_no_project(monkeypatch):
    request = _request()
    request.session.project_id = None
    monkeypatch.setattr(
        runtime,
        "decide",
        lambda *args, **kwargs: pytest.fail("invalid binding must not reach the model"),
    )

    with pytest.raises(ValueError, match="failed protocol validation"):
        runtime.handle_payload(_payload(request), model=object())


def test_explicit_local_http_contract_matches_agentcore_envelope(monkeypatch):
    request = _request()
    monkeypatch.setattr(
        runtime,
        "decide",
        lambda seen, model=None, force_llm=False: _result(seen),
    )
    client = TestClient(runtime._fastapi_app(model=object()))

    ping = client.get("/ping")
    assert ping.status_code == 200
    assert ping.json()["status"] == "Healthy"
    assert ping.json()["model_configured"] is True

    invocation = client.post("/invocations", json=_payload(request))
    assert invocation.status_code == 200
    assert invocation.json()["schema_version"] == 1
    assert invocation.json()["result"]["action"]["session_id"] == request.session.id

    invalid = client.post("/invocations", json={"schema_version": 99})
    assert invalid.status_code == 400


def test_local_http_runs_the_real_deterministic_loop_outside_the_server_event_loop(
    monkeypatch,
):
    monkeypatch.delenv("PEX_FORCE_LLM", raising=False)
    client = TestClient(runtime._fastapi_app())

    invocation = client.post("/invocations", json=_payload(_request()))

    assert invocation.status_code == 200
    result = invocation.json()["result"]
    assert result["action"]["session_id"] == "session_runtime"
    assert result["used_llm"] is False
    assert result["diagnosis"] == "deterministic_triage_no_supervisor_model"


def test_local_http_bounds_body_and_does_not_echo_invalid_input(monkeypatch):
    client = TestClient(runtime._fastapi_app(model=object()))
    secret_marker = "DO_NOT_ECHO_THIS_SECRET"
    invalid = _payload(_request())
    invalid["request"]["session"]["id"] = {"secret": secret_marker}

    response = client.post("/invocations", json=invalid)
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid AgentCore invocation"}
    assert secret_marker not in response.text

    oversized = client.post(
        "/invocations",
        content=b"{" + b"x" * runtime.MAX_RUNTIME_REQUEST_BYTES + b"}",
        headers={"content-type": "application/json"},
    )
    assert oversized.status_code == 413

    wrong_type = client.post(
        "/invocations",
        content=b"{}",
        headers={"content-type": "text/plain"},
    )
    assert wrong_type.status_code == 415

    for malformed in (
        b'{"schema_version":1,"schema_version":1}',
        b'{"schema_version":1,"padding":NaN}',
    ):
        rejected = client.post(
            "/invocations",
            content=malformed,
            headers={"content-type": "application/json"},
        )
        assert rejected.status_code == 400
        assert rejected.json() == {"detail": "invalid JSON"}


def test_runtime_rejects_oversized_model_response(monkeypatch):
    request = _request()
    result = _result(request)
    result.diagnosis = "x" * runtime.MAX_RUNTIME_RESPONSE_BYTES
    monkeypatch.setattr(
        runtime,
        "decide",
        lambda seen, model=None, force_llm=False: result,
    )

    with pytest.raises(ValueError, match="response exceeds"):
        runtime.handle_payload(_payload(request), model=object())


def test_local_http_smoke_never_loads_or_forces_ambient_model(monkeypatch):
    request = _request()
    captured = {}
    monkeypatch.setenv("PEX_FORCE_LLM", "1")
    monkeypatch.setattr(
        runtime,
        "load_supervisor_model",
        lambda: pytest.fail("local HTTP smoke must not load ambient model credentials"),
    )

    def fake_decide(seen, model=None, force_llm=False):
        captured.update(request=seen, model=model, force_llm=force_llm)
        return _result(seen)

    monkeypatch.setattr(runtime, "decide", fake_decide)
    client = TestClient(runtime._fastapi_app())
    response = client.post("/invocations", json=_payload(request))

    assert response.status_code == 200
    assert captured["model"] is None
    assert captured["force_llm"] is False


def test_runtime_rejects_a_result_bound_to_another_session(monkeypatch):
    request = _request()
    result = _result(request)
    result.action.session_id = "wrong-session"
    monkeypatch.setattr(
        runtime,
        "decide",
        lambda seen, model=None, force_llm=False: result,
    )

    with pytest.raises(ValueError, match="result.*different session"):
        runtime.handle_payload(_payload(request), model=object())


def test_real_agentcore_sdk_app_exposes_required_http_contract(monkeypatch):
    pytest.importorskip("bedrock_agentcore.runtime")
    request = _request()
    monkeypatch.setattr(
        runtime,
        "decide",
        lambda seen, model=None, force_llm=False: _result(seen),
    )
    client = TestClient(runtime._agentcore_app(model=object()))

    ping = client.get("/ping")
    invocation = client.post("/invocations", json=_payload(request))

    assert ping.status_code == 200
    assert ping.json()["status"] == "Healthy"
    assert invocation.status_code == 200
    assert invocation.headers["content-type"].startswith("application/json")
    assert invocation.json()["invocation_id"] == "pexinv_" + "a" * 32
    assert invocation.json()["result"]["action"]["session_id"] == request.session.id


def test_real_agentcore_sdk_runs_the_sync_entrypoint_outside_its_server_event_loop(
    monkeypatch,
):
    pytest.importorskip("bedrock_agentcore.runtime")
    monkeypatch.delenv("PEX_FORCE_LLM", raising=False)
    client = TestClient(runtime._agentcore_app(model=None))

    invocation = client.post("/invocations", json=_payload(_request()))

    assert invocation.status_code == 200
    result = invocation.json()["result"]
    assert result["action"]["session_id"] == "session_runtime"
    assert result["used_llm"] is False
    assert result["diagnosis"] == "deterministic_triage_no_supervisor_model"


def test_agentcore_server_failure_is_not_silently_replaced(monkeypatch):
    class BrokenApp:
        def run(self):
            raise RuntimeError("agentcore startup failed")

    monkeypatch.setenv("PEX_RUNTIME_SERVER", "agentcore")
    monkeypatch.setattr(runtime, "_agentcore_app", lambda: BrokenApp())
    monkeypatch.setattr(
        runtime,
        "_fastapi_app",
        lambda: pytest.fail("implicit local fallback must not start"),
    )
    with pytest.raises(RuntimeError, match="agentcore startup failed"):
        runtime.main()


def test_runtime_server_choice_is_explicit(monkeypatch):
    monkeypatch.setenv("PEX_RUNTIME_SERVER", "unknown")
    with pytest.raises(ValueError, match="agentcore or local_http"):
        runtime.main()
