"""Authored private-pilot admission/HTTP fixtures; external sockets forbidden."""
import hashlib
import importlib
import ipaddress
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pilot_process as pp
from test_managed_chat import no_network as no_network, rig as rig, response
from test_tool_protocol import request_fixture, final_arguments, ProposedAction, InterventionType
from test_tool_transport import payload


@pytest.fixture(autouse=True)
def authored_clock_and_cleanup(monkeypatch):
    class AuthoredClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 27, 10, 40, tzinfo=timezone.utc)
    monkeypatch.setattr(pp, "datetime", AuthoredClock)
    yield
    for runtime in list(pp._RUNTIMES.values()):
        runtime.ledger.close()
    pp._RUNTIMES.clear()


def private_config(tmp_path, request, **changes):
    tmp_path.chmod(0o700)
    key = tmp_path / "synthetic-key"
    key.write_text("fixture-no-real-provider-credential")
    key.chmod(0o600)
    config = dict(schema=1, approval_ref=pp.APPROVAL_REF, pilot_id=pp.PILOT_ID,
        expires_at=pp.EXECUTION_END, endpoint=pp.ENDPOINT, model=pp.MODEL,
        budget_nano_usd=250000000, max_attempts=12, input_rate=300, output_rate=900,
        pricing_provenance_sha256="d" * 64, key_path=str(key),
        key_sha256=hashlib.sha256(key.read_bytes()).hexdigest(),
        ledger_path=str(tmp_path / "supervisor-pilot.sqlite"),
        source_sha256={name: hashlib.sha256(Path(importlib.import_module(name).__file__).read_bytes()).hexdigest()
                       for name in pp.SOURCE_MODULES},
        request_binding=dict(goal_id=request.goal.id, session_id=request.session.id,
                             vendor_session_id=request.session.vendor_session_id))
    config.update(changes)
    path = tmp_path / "pilot.json"
    path.write_text(json.dumps(config, sort_keys=True))
    path.chmod(0o600)
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), config


@pytest.mark.asyncio
async def test_real_owned_pilot_protocol_authored_wire_and_shared_ledger(tmp_path, rig, monkeypatch):
    import managed_chat
    request = request_fixture(with_boundaries=True)
    path, digest, config = private_config(tmp_path, request)
    async def resolve(host, port):
        assert host == "api.tokenfactory.us-central1.nebius.com" and port == 443
        return ipaddress.ip_address("93.184.216.34")
    monkeypatch.setattr(managed_chat, "_resolve_public_address", resolve)
    for role in ("planner", "verifier"):
        proposal = ProposedAction(type=InterventionType.NOOP, session_id=request.session.id,
                                  goal_id=request.goal.id, rationale="Authored") if role == "verifier" else None
        model = pp.pilot_model(path, request, invocation_id="authored-pilot-"+role,
                               proposal=proposal, expected_config_sha256=digest)
        def handle(wire):
            body = json.loads(wire.content)
            assert body["n"] == 1 and body["model"] == pp.MODEL
            assert body["max_completion_tokens"] == (1200 if role == "planner" else 900)
            assert "service_tier" not in body
            data = payload("get_goal", '{"boundary_page":0}') if len(rig.calls) % 2 else payload(
                model.protocol.final_name, json.dumps(final_arguments(role)), "final")
            data["model"] = pp.MODEL
            return response(data)
        rig.handler = handle
        result = await model.invoke_async()
        assert result.structured_output is not None
        assert len(model.receipts) == 2
        assert all(r.outcome == "succeeded" and r.attempts == 1 for r in model.receipts)
    runtime = pp._RUNTIMES[(str(path), digest)]
    assert len(runtime.ledger.summary()) == 4
    assert sum(r["charged"] for r in runtime.ledger.summary()) == 25200
    assert len(rig.calls) == 4
    pp.close_pilot(path, expected_config_sha256=digest)
    with pytest.raises(ValueError, match="already closed"):
        pp.pilot_model(path, request, invocation_id="reuse", expected_config_sha256=digest)


@pytest.mark.parametrize("change", [
    {"approval_ref":"other"}, {"budget_nano_usd":250000001}, {"max_attempts":13},
    {"endpoint":"https://other.invalid/v1/chat/completions"}, {"model":"other/model"},
    {"expires_at":"2020-01-01T00:00:00+00:00"},
    {"expires_at":"2026-10-28T00:00:00+00:00"}, {"source_sha256":{}},
])
def test_private_admission_mismatch_before_transport(tmp_path, rig, change):
    request = request_fixture(with_boundaries=True)
    path, digest, _ = private_config(tmp_path, request, **change)
    with pytest.raises((ValueError, RuntimeError)):
        pp.pilot_model(path, request, invocation_id="refused", expected_config_sha256=digest)
    assert not rig.created and not rig.calls
    assert not (tmp_path / "supervisor-pilot.sqlite").exists()


def test_private_digest_required_and_request_bound(tmp_path, rig):
    request = request_fixture(with_boundaries=True)
    path, digest, _ = private_config(tmp_path, request)
    for expected in (None, "a" * 64):
        with pytest.raises(ValueError):
            pp.pilot_model(path, request, invocation_id="refused", expected_config_sha256=expected)
    request.session.vendor_session_id = "other-worker"
    with pytest.raises(ValueError, match="outside approved"):
        pp.pilot_model(path, request, invocation_id="refused", expected_config_sha256=digest)
    assert not rig.created and not rig.calls


@pytest.mark.asyncio
async def test_changed_private_key_never_dispatches(tmp_path, rig):
    request = request_fixture(with_boundaries=True)
    path, digest, config = private_config(tmp_path, request)
    model = pp.pilot_model(path, request, invocation_id="changed-key", expected_config_sha256=digest)
    Path(config["key_path"]).write_text("another-synthetic-key")
    with pytest.raises(ValueError, match="credential identity"):
        await model.invoke_async()
    assert not rig.created and not rig.calls
    assert pp._RUNTIMES[(str(path), digest)].ledger.summary() == []


@pytest.mark.parametrize("target", ["config", "key", "parent"])
@pytest.mark.asyncio
async def test_public_permissions_refused(tmp_path, rig, target):
    request = request_fixture(with_boundaries=True)
    path, digest, config = private_config(tmp_path, request)
    if target == "config": path.chmod(0o644)
    elif target == "key": Path(config["key_path"]).chmod(0o644)
    else: tmp_path.chmod(0o755)
    with pytest.raises(ValueError, match="permissions"):
        model = pp.pilot_model(path, request, invocation_id="bad-mode", expected_config_sha256=digest)
        await model.invoke_async()
    assert not rig.created and not rig.calls


def test_source_digest_mismatch_refused(tmp_path, rig):
    request = request_fixture(with_boundaries=True)
    path, _, config = private_config(tmp_path, request)
    config["source_sha256"]["accounting"] = "0" * 64
    path.write_text(json.dumps(config))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="source identity"):
        pp.pilot_model(path, request, invocation_id="bad-source", expected_config_sha256=digest)
    assert not rig.created and not rig.calls


@pytest.mark.asyncio
async def test_budget_terminal_type_survives_actual_owned_agent(tmp_path, rig):
    from accounting import PilotBudgetExhausted
    request = request_fixture(with_boundaries=True)
    path, digest, _ = private_config(tmp_path, request)
    model = pp.pilot_model(path, request, invocation_id="budget-terminal", expected_config_sha256=digest)
    runtime = pp._RUNTIMES[(str(path), digest)]
    for index in range(3):
        runtime.ledger.reserve(f"uncertain-{index}", runtime.routes[index % 2])
    with pytest.raises(PilotBudgetExhausted) as exc:
        await model.invoke_async()
    assert exc.value.code == "budget_reservation_refused"
    assert not rig.created and not rig.calls
    assert sum(row["charged"] for row in runtime.ledger.summary()) == 246988800
