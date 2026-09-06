import asyncio
import hashlib
import hmac
import json
import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import create_app, state
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pets import ImportedPet, PetSettings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import (
    Authority,
    EventType,
    HarnessType,
    PolicyVerdict,
    SessionStatus,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession

PROJECTION_ORIGIN = ProjectOrigin(namespace="machine", host="projection-e2e")


@pytest.fixture
async def client(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage")
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = None
    state.pet_settings = PetSettings()
    state.pet_path = tmp_path / "pet.json"
    await store.connect()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1") as ac:
        yield ac
    await store.close()


async def _seed_projection_row(
    *,
    suffix: str,
    status: SessionStatus,
    action_type: InterventionType,
    created_at: datetime,
) -> tuple[Goal, HarnessSession, Intervention]:
    project_id = f"projection-{suffix}"
    await state.store.register_project_locator(
        legacy_project_id=project_id,
        locator=ProjectLocator.path(
            f"/work/{project_id}-a",
            platform=PathPlatform.POSIX,
            origin=PROJECTION_ORIGIN,
        ),
    )
    goal = Goal(
        id=f"goal-{suffix}",
        project_id=project_id,
        title=f"Projection {suffix}",
        objective="Keep current UI projections bound to live project authority.",
        created_at=created_at,
        updated_at=created_at,
    )
    await state.store.upsert_goal(goal)
    session = HarnessSession(
        id=f"synthetic:{suffix}",
        harness_type=HarnessType.SYNTHETIC,
        vendor_session_id=suffix,
        project_id=project_id,
        goal_id=goal.id,
        cwd=project_id,
        status=status,
        last_activity=created_at,
    )
    await state.store.upsert_session(session)
    await state.store.accept_pipeline_event(
        HarnessEvent(
            event_id=f"event-{suffix}",
            ts=created_at,
            harness_type=session.harness_type,
            session_id=session.id,
            project_id=project_id,
            goal_id=goal.id,
            event_type=EventType.AGENT_RESPONSE,
            message_delta=f"{suffix} current worker evidence",
        ),
        session_snapshot=session,
    )
    action = ProposedAction(
        type=action_type,
        session_id=session.id,
        goal_id=goal.id,
        rationale=f"Projection action for {suffix}.",
        evidence=[f"event:event-{suffix}"],
        risk=RiskLevel.NONE,
        authority_required=Authority.LOCAL_POLICY,
    )
    intervention = Intervention(
        id=f"intervention-{suffix}",
        session_id=session.id,
        goal_id=goal.id,
        trigger=EventType.STOP.value,
        evidence=action.evidence,
        diagnosis=f"{suffix} action",
        proposed_action=action,
        risk=action.risk.value,
        authority_required=action.authority_required.value,
        action_taken=action_type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="sent" if action_type == InterventionType.SEND_NUDGE else "noop",
        created_at=created_at,
    )
    await state.store.add_intervention(intervention)
    return goal, session, intervention


async def _invalidate_projection_project(project_id: str, *, rebound: bool) -> None:
    conflict = await state.store.register_project_locator(
        legacy_project_id=project_id,
        locator=ProjectLocator.path(
            f"/work/{project_id}-b",
            platform=PathPlatform.POSIX,
            origin=PROJECTION_ORIGIN,
        ),
    )
    assert conflict["outcome"] == "quarantined"
    if rebound:
        await state.store.resolve_project_identity_conflict(
            resolution_id=f"resolve-{project_id}-to-b",
            legacy_project_id=project_id,
            selected_identity_id=conflict["identity"].id,
            resolved_by="projection-e2e",
            rationale="Select the deliberately distinct B checkout.",
        )


@pytest.mark.asyncio
async def test_m0_event_to_action_roundtrip(client: AsyncClient):
    liveness = await client.get("/health/live")
    assert liveness.json() == {"ok": True, "service": "pex-bridge"}

    health = await client.get("/health")
    assert health.json()["ok"] is True

    session_resp = await client.post("/v1/synthetic/sessions")
    session = session_resp.json()
    session_id = session["id"]
    # The typed verifier binds execution to the exact discovered workspace.
    # The generic API session starts unbound, so M0 supplies the fixture root as
    # the synthetic harness's observed cwd before attaching a goal.
    bound_session = await state.store.get_session(session_id)
    assert bound_session is not None
    bound_session.cwd = str(state.settings.home)
    state.adapters.synthetic.sessions[session_id].cwd = str(state.settings.home)
    await state.store.upsert_session(bound_session)

    goal_resp = await client.post(
        "/v1/goals",
        json={
            "project_id": "demo",
            "title": "Eval pipeline",
            "objective": "Produce a complete evaluation with passing tests",
            "acceptance_criteria": ["tests pass", "results.json has 30 rows"],
            "evidence_requirements": ["pytest output"],
        },
    )
    goal_id = goal_resp.json()["id"]
    attached = await client.post(f"/v1/sessions/{session_id}/attach", json={"goal_id": goal_id})
    assert attached.status_code == 200

    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session_id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    body = stop.json()
    assert body["intervention"] is not None
    assert body["intervention"]["action_taken"] == "SEND_NUDGE"
    assert "results.json" in body["inbox"][-1]

    (state.settings.home / "results.json").write_text(
        json.dumps(list(range(30))),
        encoding="utf-8",
    )
    await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session_id,
            "event_type": EventType.FILE_EDIT.value,
            "file_paths": ["results.json"],
        },
    )
    stop = await client.post(
        "/v1/synthetic/events",
        json={
            "session_id": session_id,
            "event_type": EventType.STOP.value,
            "message": "All tests passed. I am done.",
        },
    )
    body = stop.json()
    assert body["intervention"]["action_taken"] == "REQUEST_VERIFICATION"
    claims = (body["intervention"].get("metadata") or {}).get("claims") or []
    assert any(item.get("kind") == "tests_pass" for item in claims)
    gathering = body["intervention"]["metadata"]["verification"]["evidence_gathering"]
    assert gathering["state"] == "attempted"
    assert gathering["probe"]["kind"] == "pytest"
    assert gathering["execution"] is None
    assert body["inbox"][-1].startswith("The test-backed completion criterion is unresolved:")
    assert "Run the full pytest suite from the current project root now." in body["inbox"][-1]

    pet = await client.get("/v1/pet")
    body = pet.json()
    assert body["mood"] == "observing"
    assert body["headline"] == "Verification requested → awaiting evidence"
    assert body.get("last_message")
    assert "All tests passed" in body["last_message"]

    adapters = await client.get("/v1/adapters")
    names = {item["name"] for item in adapters.json()}
    assert "synthetic" in names
    assert "cursor" in names
    assert "codex" in names
    asked = await client.post("/v1/ask", json={"question": "what needs me?"})
    assert "answer" in asked.json()
    pets = await client.get("/v1/pets")
    assert [pet["id"] for pet in pets.json()["starters"]] == [
        "pex",
        "ledger",
        "mesh",
        "nudge",
        "drift",
        "quiet",
        "ember",
        "von",
    ]
    assert all("spritesheet" not in pet for pet in pets.json()["catalog"])
    assert "imports" not in pets.json()["settings"]
    assert "imported_codex_dir" not in pets.json()["settings"]
    assert "spritesheet" not in body["appearance"]
    assert pets.json()["codex_contract"]["spriteVersionNumber"] == 2
    claude = await client.post(
        "/v1/hooks/claude_code",
        json={"session_id": "claude-demo", "hook_event_name": "Stop", "text": "done"},
    )
    assert claude.status_code == 200
    assert claude.json()["session_id"].startswith("claude_code:")
    assert "hookSpecificOutput" in claude.json() or claude.json().get("ok") is True


@pytest.mark.asyncio
async def test_unimplemented_generic_hook_surfaces_are_rejected(client: AsyncClient):
    for harness in ("pi", "prime", "zcode", "deepseek", "grok_build", "kimi", "omp"):
        response = await client.post(
            f"/v1/hooks/{harness}",
            json={"session_id": "fabricated", "hook_event_name": "Stop"},
        )
        assert response.status_code == 404, (harness, response.text)
    assert await state.store.list_sessions() == []
    discovered = await client.get("/v1/discover")
    assert "found" in discovered.json()
    deck = await client.get("/v1/deck")
    names = {item["name"] for item in deck.json()["adapters"]}
    assert "opencode" in names
    assert "qwen" in names
    sheet = await client.get("/v1/pets/pex/spritesheet")
    assert sheet.status_code == 200
    assert sheet.headers["content-type"].startswith("image/")
    traj = await client.get("/v1/demo/trajectories")
    ids = {item["id"] for item in traj.json()["fixtures"]}
    assert "premature_stop_eval" in ids
    live_decide = AsyncMock(side_effect=AssertionError("live supervisor used during replay"))
    state.pipeline.supervisor.decide = live_decide
    replay = await client.post("/v1/demo/replay", json={"fixture": "premature_stop_eval"})
    assert replay.status_code == 200
    assert replay.json()["replay"] is True
    assert replay.json()["not_live_control"] is True
    live_decide.assert_not_awaited()
    patched = await client.patch(
        "/v1/pets/settings",
        json={"custom_name": "Ledgerbot", "selected_id": "ledger"},
    )
    assert patched.status_code == 200
    shown = await client.get("/v1/pet")
    assert shown.json()["appearance"]["display_name"] == "Ledgerbot"
    click_through = await client.patch("/v1/pets/settings", json={"click_through": True})
    assert click_through.status_code == 200
    assert click_through.json()["click_through"] is True
    overlay = await client.get("/v1/pet")
    assert overlay.json()["settings"]["click_through"] is True


@pytest.mark.asyncio
async def test_command_deck_degrades_one_failed_adapter_probe(client: AsyncClient, monkeypatch):
    class BrokenAdapter:
        name = "broken"

        async def probe(self):
            raise RuntimeError("private vendor failure detail")

    monkeypatch.setattr(state.adapters, "all", lambda: [BrokenAdapter()])
    response = await client.get("/v1/deck")
    assert response.status_code == 200
    assert response.json()["adapters"] == [
        {
            "name": "broken",
            "capabilities": {
                "support_label": "unavailable",
                "notes": "Live capability probe timed out or failed; nothing was inferred.",
            },
        }
    ]
    assert "private vendor failure detail" not in response.text


@pytest.mark.asyncio
async def test_attention_metrics_api_is_versioned_exact_and_null_preserving(
    client: AsyncClient,
):
    response = await client.get("/v1/attention/metrics")
    assert response.status_code == 200
    metrics = response.json()
    assert metrics["schema"] == "pex.attention-metrics.v1"
    assert metrics["definition_version"] == 1
    assert metrics["scope"]["kind"] == "all_local_durable_history"
    assert metrics["window"]["aggregate_truncated"] is False
    assert metrics["authority"]["consistent_read_snapshot"] is True
    assert metrics["human_interventions"]["value"] is None
    assert metrics["human_interventions"]["coverage_complete"] is False
    assert metrics["human_active_seconds"]["value"] is None
    assert metrics["human_active_seconds"]["consent"] == "not_configured"
    assert metrics["unnecessary_alert_rate"]["value"] is None
    assert metrics["average_auto_resolution_confidence"]["value"] is None
    assert metrics["benchmark_evidence"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("rebound", [False, True], ids=["quarantine", "a-to-b"])
async def test_pet_and_deck_exclude_noncurrent_authority_from_counts_and_action(
    client: AsyncClient,
    rebound: bool,
):
    now = datetime.now(UTC)
    current_goal, current_session, current_action = await _seed_projection_row(
        suffix="current",
        status=SessionStatus.WORKING,
        action_type=InterventionType.NOOP,
        created_at=now - timedelta(seconds=30),
    )
    stale_goal, stale_session, stale_action = await _seed_projection_row(
        suffix="stale-rebound" if rebound else "stale-quarantined",
        status=SessionStatus.NEEDS_DECISION,
        action_type=InterventionType.SEND_NUDGE,
        created_at=now,
    )
    await _invalidate_projection_project(stale_goal.project_id, rebound=rebound)

    pet_response = await client.get("/v1/pet")
    assert pet_response.status_code == 200
    pet = pet_response.json()
    assert pet["working"] == 1
    assert pet["drifting"] == 0
    assert pet["needs_you"] == 0
    assert pet["headline"] == "1 working · 0 need you"
    assert [row["id"] for row in pet["sessions"]] == [current_session.id]
    assert pet["last_action"]["id"] == current_action.id
    assert pet["last_message"] == "current current worker evidence"

    deck_response = await client.get("/v1/deck")
    assert deck_response.status_code == 200
    deck = deck_response.json()
    assert [row["id"] for row in deck["sessions"]] == [current_session.id]
    assert [row["id"] for row in deck["interventions"]] == [current_action.id]
    assert deck["evidence_basis"]["sessions_returned"] == 1
    assert deck["evidence_basis"]["interventions_returned"] == 1
    assert "live Store authority only" in deck["evidence_basis"]["current_projection"]

    # The raw reads remain deliberately forensic even though the rows no longer
    # participate in the present-tense pet/deck projection.
    assert await state.store.get_goal(stale_goal.id) == stale_goal
    assert await state.store.get_session(stale_session.id) == stale_session
    assert [row.id for row in await state.store.list_interventions(stale_session.id)] == [
        stale_action.id
    ]
    assert await state.store.get_goal(current_goal.id) == current_goal


@pytest.mark.asyncio
async def test_command_deck_fingerprints_use_stop_verification_counts(client: AsyncClient):
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    goal = Goal(
        id="goal-command-deck-fingerprints",
        project_id=str(state.settings.home),
        title="Command deck fingerprints",
        objective="Summarize verification outcomes for bound agent sessions.",
        created_at=now,
        updated_at=now,
    )
    await state.store.upsert_goal(goal)
    await state.store.upsert_session(
        HarnessSession(
            id="cursor:supported",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="supported",
            project_id=goal.project_id,
            goal_id=goal.id,
            model="model-b",
        )
    )
    await state.store.upsert_session(
        HarnessSession(
            id="cursor:gap",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="gap",
            project_id=goal.project_id,
            goal_id=goal.id,
            model="model-a",
        )
    )
    await state.store.upsert_session(
        HarnessSession(
            id="cursor:gap-two",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="gap-two",
            project_id=goal.project_id,
            goal_id=goal.id,
            model="model-a",
        )
    )

    def intervention(intervention_id: str, session_id: str, status: str) -> Intervention:
        return Intervention(
            id=intervention_id,
            session_id=session_id,
            goal_id=goal.id,
            trigger="stop",
            evidence=[],
            diagnosis="deterministic test",
            proposed_action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=session_id,
                goal_id=goal.id,
                rationale="deterministic test",
                risk=RiskLevel.NONE,
            ),
            risk="none",
            authority_required="local_policy",
            action_taken="NOOP",
            policy_verdict=PolicyVerdict.ALLOW,
            created_at=now,
            metadata={"verification": {"status": status}},
        )

    await state.store.add_intervention(intervention("supported", "cursor:supported", "supported"))
    await state.store.add_intervention(intervention("gap", "cursor:gap", "acceptance_gap"))
    await state.store.add_intervention(intervention("gap-two", "cursor:gap-two", "acceptance_gap"))
    response = await client.get("/v1/deck")
    assert response.status_code == 200
    fingerprints = response.json()["fingerprints"]
    cursor = next(item for item in fingerprints if item["harness"] == "cursor")
    assert cursor["strengths"] == ["1 inspected STOP supported by the verifier"]
    assert cursor["failure_modes"] == ["2 inspected STOPs contradicted or left an acceptance gap"]
    assert cursor["recommended_overlays"] == []
    assert cursor["cohort_scoped"] is False
    assert cursor["verified_success_rate"] == pytest.approx(1 / 3)
    assert cursor["token_efficiency"] is None
    assert "good at" not in response.text.lower()


@pytest.mark.asyncio
async def test_pet_atlas_loading_keeps_authenticated_identity_responsive(client, monkeypatch):
    release = threading.Event()
    entered = asyncio.Event()
    loop = asyncio.get_running_loop()
    payload = b"validated-atlas-test-bytes"

    def blocked_reader(_path):
        loop.call_soon_threadsafe(entered.set)
        release.wait(5)
        return payload

    monkeypatch.setattr("pex_bridge.app._read_pet_atlas", blocked_reader)
    monkeypatch.setattr("pex_bridge.pets.resolve_spritesheet", lambda _id: "fixture.webp")
    monkeypatch.setattr(state.settings, "require_auth", True)
    monkeypatch.setattr(state, "token", "unit-test-identity-token")
    requests = [
        asyncio.create_task(client.get(
            "/v1/pets/pex/spritesheet",
            headers={"Authorization": "Bearer unit-test-identity-token"},
        ))
        for _ in range(2)
    ]
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert all(not request.done() for request in requests)
        challenge = "a" * 64
        identity = await asyncio.wait_for(
            client.get("/health/identity", params={"challenge": challenge}), 1
        )
        assert identity.status_code == 200
        assert identity.json()["proof"] == hmac.new(
            b"unit-test-identity-token", challenge.encode(), hashlib.sha256
        ).hexdigest()
        assert all(not request.done() for request in requests)
    finally:
        release.set()
        responses = await asyncio.gather(*requests)
    assert all(response.status_code == 200 for response in responses)
    assert all(response.content == payload for response in responses)
    assert all(response.headers["content-type"] == "image/webp" for response in responses)


@pytest.mark.asyncio
async def test_pet_spritesheet_route_fails_closed_for_missing_or_invalid_atlas(
    client: AsyncClient,
    tmp_path,
    monkeypatch,
):
    missing = tmp_path / "missing" / "spritesheet.webp"
    state.pet_settings.imports = [
        ImportedPet(
            id="import:missing",
            display_name="Missing",
            directory=str(missing.parent),
            spritesheet=str(missing),
        )
    ]
    imported = await client.get("/v1/pets/import:missing/spritesheet")
    assert imported.status_code == 409
    assert "unavailable" in imported.json()["detail"]

    monkeypatch.setattr("pex_bridge.pets.resolve_spritesheet", lambda _pet_id: None)
    missing_starter = await client.get("/v1/pets/pex/spritesheet")
    assert missing_starter.status_code == 409
    assert "unavailable" in missing_starter.json()["detail"]

    invalid = tmp_path / "invalid.webp"
    invalid.write_bytes(b"not-a-webp-atlas")
    monkeypatch.setattr("pex_bridge.pets.resolve_spritesheet", lambda _pet_id: str(invalid))
    starter = await client.get("/v1/pets/pex/spritesheet")
    assert starter.status_code == 409
    assert "WebP" in starter.json()["detail"]

    from PIL import Image

    transparent = tmp_path / "transparent.webp"
    Image.new("RGBA", (1536, 2288), (0, 0, 0, 0)).save(transparent, "WEBP", lossless=True)
    monkeypatch.setattr("pex_bridge.pets.resolve_spritesheet", lambda _pet_id: str(transparent))
    transparent_response = await client.get("/v1/pets/pex/spritesheet")
    assert transparent_response.status_code == 409
    assert "visible pixels" in transparent_response.json()["detail"]

    opaque = tmp_path / "opaque.webp"
    Image.new("RGBA", (1536, 2288), (1, 2, 3, 255)).save(opaque, "WEBP", lossless=True)
    monkeypatch.setattr("pex_bridge.pets.resolve_spritesheet", lambda _pet_id: str(opaque))
    opaque_response = await client.get("/v1/pets/pex/spritesheet")
    assert opaque_response.status_code == 409
    assert any(
        marker in opaque_response.json()["detail"]
        for marker in ("alpha channel", "transparent background")
    )


@pytest.mark.asyncio
async def test_claude_user_prompt_submit_rewrites_ambiguity_as_additional_context(
    client: AsyncClient,
):
    goal = await client.post(
        "/v1/goals",
        json={
            "project_id": "C:/proj",
            "title": "Eval",
            "objective": "Produce a complete evaluation",
            "acceptance_criteria": ["results.jsonl has 30 rows"],
        },
    )
    goal_id = goal.json()["id"]
    started = await client.post(
        "/v1/hooks/claude_code",
        json={
            "session_id": "claude-ambiguous",
            "hook_event_name": "SessionStart",
            "cwd": "C:/proj",
        },
    )
    assert started.status_code == 200
    attached = await client.post(
        "/v1/sessions/claude_code:claude-ambiguous/attach",
        json={"goal_id": goal_id},
    )
    assert attached.status_code == 200
    rewritten = await client.post(
        "/v1/hooks/claude_code",
        json={
            "session_id": "claude-ambiguous",
            "hook_event_name": "UserPromptSubmit",
            "cwd": "C:/proj",
            "prompt": "Just quickly hack whatever works.",
        },
    )
    body = rewritten.json()
    context = str((body.get("hookSpecificOutput") or {}).get("additionalContext") or "")
    assert "Eval" in context
    assert "ambiguous" in context.lower()
    assert not context.startswith("PEX:")
    assert body.get("decision") != "block"


@pytest.mark.asyncio
async def test_claude_precompact_injects_ledger_checkpoint_as_additional_context(
    client: AsyncClient,
):
    goal = await client.post(
        "/v1/goals",
        json={
            "project_id": "C:/proj",
            "title": "Eval",
            "objective": "Produce a complete evaluation",
            "acceptance_criteria": ["results.jsonl has 30 rows"],
            "constraints": ["Do not alter dataset preprocessing."],
        },
    )
    goal_id = goal.json()["id"]
    started = await client.post(
        "/v1/hooks/claude_code",
        json={
            "session_id": "claude-compact",
            "hook_event_name": "SessionStart",
            "cwd": "C:/proj",
        },
    )
    assert started.status_code == 200
    attached = await client.post(
        "/v1/sessions/claude_code:claude-compact/attach",
        json={"goal_id": goal_id},
    )
    assert attached.status_code == 200
    compacted = await client.post(
        "/v1/hooks/claude_code",
        json={
            "session_id": "claude-compact",
            "hook_event_name": "PreCompact",
            "cwd": "C:/proj",
            "prompt": "Compacting context.",
        },
    )
    body = compacted.json()
    context = str((body.get("hookSpecificOutput") or {}).get("additionalContext") or "")
    assert "Eval" in context
    assert "results.jsonl" in context
    assert "preprocessing" in context.lower()
    assert not context.startswith("PEX:")
    assert body.get("decision") != "block"
