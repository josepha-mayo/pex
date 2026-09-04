import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import EventType, HarnessType, PolicyVerdict
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.project_identity import ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession

ORIGIN = ProjectOrigin(namespace="fingerprint-test", host="local")


def _model_metadata(model: str, reasoning_effort: str) -> dict[str, object]:
    model_settings = {"temperature": 0, "tool_mode": "auto"}
    payload = {
        "model": model,
        "reasoning_effort": reasoning_effort,
        "settings": model_settings,
    }
    settings_hash = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "model_settings": model_settings,
        "model_settings_hash": settings_hash,
        "project_class": "coding",
    }


async def _commit_fingerprint_intervention(
    store: Store,
    *,
    event: HarnessEvent,
    session: HarnessSession,
    intervention: Intervention,
) -> None:
    owner = f"fingerprint-owner-{event.event_id}"
    await store.claim_event_processing(event.event_id, owner=owner)
    await store.commit_event_plan(
        event_id=event.event_id,
        owner=owner,
        plan={
            "schema": "pex.event-plan.v1",
            "event_id": event.event_id,
            "session_id": event.session_id,
            "goal_id": event.goal_id,
            "project_id": event.project_id,
            "effect_kind": None,
            "intervention_id": intervention.id,
            "action": intervention.proposed_action.model_dump(mode="json"),
            "required_capability": None,
            "context_ids": [],
            "decision_ids": [],
            "intervention_update_ids": [],
        },
        session=session,
        intervention=intervention,
        receipt={
            "schema": "pex.event-processing.receipt.v1",
            "event_id": event.event_id,
            "status": "complete",
            "intervention": intervention.model_dump(mode="json"),
        },
    )


def _intervention(
    intervention_id: str,
    session_id: str,
    *,
    goal_id: str,
    verification_status: str | None = None,
    action_taken: str = "NOOP",
    action_type: InterventionType = InterventionType.NOOP,
    trigger: str = "stop",
    trigger_event_id: str | None = None,
) -> Intervention:
    metadata = {}
    if verification_status is not None:
        metadata = {"verification": {"status": verification_status}}
    if trigger_event_id is not None:
        metadata["trigger_event_id"] = trigger_event_id
    return Intervention(
        id=intervention_id,
        session_id=session_id,
        goal_id=goal_id,
        trigger=trigger,
        evidence=[],
        diagnosis="deterministic test",
        proposed_action=ProposedAction(
            type=action_type,
            session_id=session_id,
            goal_id=goal_id,
            rationale="deterministic test",
            risk=RiskLevel.NONE,
        ),
        risk="none",
        authority_required="local_policy",
        action_taken=action_taken,
        policy_verdict=PolicyVerdict.ALLOW,
        created_at=datetime.now(UTC),
        metadata=metadata,
    )


@pytest.mark.asyncio
async def test_agent_fingerprint_counts_only_verified_premature_sessions(tmp_path: Path):
    store = Store(tmp_path / "fingerprints.sqlite")
    await store.connect()
    try:
        now = datetime.now(UTC)
        goal = Goal(
            id="goal-fingerprints",
            project_id="fingerprint-project",
            title="Agent fingerprints",
            objective="Count verification outcomes for bound agent sessions.",
            created_at=now,
            updated_at=now,
        )
        await store.upsert_goal(goal)
        await store.upsert_session(
            HarnessSession(
                id="cursor:one",
                harness_type=HarnessType.CURSOR,
                vendor_session_id="one",
                project_id=goal.project_id,
                goal_id=goal.id,
                model="model-b",
            )
        )
        await store.upsert_session(
            HarnessSession(
                id="cursor:two",
                harness_type=HarnessType.CURSOR,
                vendor_session_id="two",
                project_id=goal.project_id,
                goal_id=goal.id,
                model="model-a",
            )
        )
        await store.upsert_session(
            HarnessSession(
                id="cursor:three",
                harness_type=HarnessType.CURSOR,
                vendor_session_id="three",
                project_id=goal.project_id,
                goal_id=goal.id,
                model="model-a",
            )
        )
        await store.add_intervention(
            _intervention(
                "supported",
                "cursor:one",
                goal_id=goal.id,
                verification_status="supported",
            )
        )
        await store.add_intervention(
            _intervention(
                "gap-one",
                "cursor:two",
                goal_id=goal.id,
                verification_status="acceptance_gap",
            )
        )
        await store.add_intervention(
            _intervention(
                "gap-duplicate",
                "cursor:two",
                goal_id=goal.id,
                verification_status="contradicted",
            )
        )
        await store.add_intervention(
            _intervention(
                "overlay",
                "cursor:two",
                goal_id=goal.id,
                verification_status="acceptance_gap",
                action_taken="APPLY_OVERLAY",
                action_type=InterventionType.APPLY_OVERLAY,
                trigger="stop",
            )
        )
        await store.add_intervention(
            _intervention(
                "uncertain",
                "cursor:three",
                goal_id=goal.id,
                verification_status="uncertain",
            )
        )

        cursor = await store.db.execute("SELECT json FROM interventions ORDER BY id")
        envelopes = [json.loads(row["json"]) for row in await cursor.fetchall()]
        assert {row["schema"] for row in envelopes} == {"pex.intervention-bound.v1"}

        assert await store.agent_fingerprint_stats() == [
            {
                "harness": "cursor",
                "observed_sessions": 3,
                "models": ["model-a", "model-b"],
                "premature_stop_sessions": 1,
                "verified_stop_sessions": 1,
                "overlay_sessions": 1,
                "inspected_stop_sessions": 2,
            }
        ]
        assert await store.agent_fingerprint_stats(session_id="cursor:two") == []
        assert await store.agent_fingerprint_stats(session_id="missing") == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_planner_fingerprint_cohort_isolates_project_model_and_reasoning(tmp_path: Path):
    store = Store(tmp_path / "fingerprint-cohorts.sqlite")
    await store.connect()
    try:
        now = datetime.now(UTC)
        goal_a = Goal(
            id="goal-cohort-a",
            project_id="cohort-project-a",
            title="Cohort A",
            objective="Keep fingerprint evidence in project A.",
            created_at=now,
            updated_at=now,
        )
        goal_b = Goal(
            id="goal-cohort-b",
            project_id="cohort-project-b",
            title="Cohort B",
            objective="Keep fingerprint evidence in project B.",
            created_at=now,
            updated_at=now,
        )
        await store.register_project_locator(
            legacy_project_id=goal_a.project_id,
            locator=ProjectLocator.opaque("cohort-a", origin=ORIGIN),
        )
        await store.register_project_locator(
            legacy_project_id=goal_b.project_id,
            locator=ProjectLocator.opaque("cohort-b", origin=ORIGIN),
        )
        await store.upsert_goal(goal_a)
        await store.upsert_goal(goal_b)
        sessions = [
            HarnessSession(
                id="codex:a1",
                harness_type=HarnessType.CODEX,
                vendor_session_id="a1",
                project_id=goal_a.project_id,
                goal_id=goal_a.id,
                model="model-x",
                reasoning_effort="high",
                metadata=_model_metadata("model-x", "high"),
            ),
            HarnessSession(
                id="codex:a2",
                harness_type=HarnessType.CODEX,
                vendor_session_id="a2",
                project_id=goal_a.project_id,
                goal_id=goal_a.id,
                model="model-x",
                reasoning_effort="high",
                metadata=_model_metadata("model-x", "high"),
            ),
            HarnessSession(
                id="codex:other-project",
                harness_type=HarnessType.CODEX,
                vendor_session_id="other-project",
                project_id=goal_b.project_id,
                goal_id=goal_b.id,
                model="model-x",
                reasoning_effort="high",
                metadata=_model_metadata("model-x", "high"),
            ),
            HarnessSession(
                id="codex:other-reasoning",
                harness_type=HarnessType.CODEX,
                vendor_session_id="other-reasoning",
                project_id=goal_a.project_id,
                goal_id=goal_a.id,
                model="model-x",
                reasoning_effort="low",
                metadata=_model_metadata("model-x", "low"),
            ),
            HarnessSession(
                id="codex:other-model",
                harness_type=HarnessType.CODEX,
                vendor_session_id="other-model",
                project_id=goal_a.project_id,
                goal_id=goal_a.id,
                model="model-y",
                reasoning_effort="high",
                metadata=_model_metadata("model-y", "high"),
            ),
            HarnessSession(
                id="codex:orphan",
                harness_type=HarnessType.CODEX,
                vendor_session_id="orphan",
                project_id=goal_a.project_id,
                goal_id=goal_a.id,
                model="model-x",
                reasoning_effort="high",
                metadata=_model_metadata("model-x", "high"),
            ),
        ]
        event_ids: dict[str, str] = {}
        for session in sessions:
            await store.upsert_session(session)
            event_id = f"event-{session.vendor_session_id}"
            event_ids[session.id] = event_id
            event = HarnessEvent(
                event_id=event_id,
                ts=now,
                harness_type=session.harness_type,
                session_id=session.id,
                project_id=session.project_id,
                goal_id=session.goal_id,
                event_type=EventType.STOP,
            )
            await store.accept_pipeline_event(event, session_snapshot=session)
            intervention = _intervention(
                f"gap-{session.vendor_session_id}",
                session.id,
                goal_id=session.goal_id or "",
                verification_status="acceptance_gap",
                trigger_event_id=event_id,
            )
            if session.id == "codex:orphan":
                await store.add_intervention(intervention)
            else:
                await _commit_fingerprint_intervention(
                    store,
                    event=event,
                    session=session,
                    intervention=intervention,
                )

        mutated = sessions[0].model_copy(
            update={
                "model": "model-after-acceptance",
                "reasoning_effort": "low",
                "metadata": {
                    **_model_metadata("model-after-acceptance", "low"),
                    "project_class": "different",
                },
            }
        )
        await store.upsert_session(mutated)
        scoped = await store.agent_fingerprint_stats(
            session_id="codex:a1",
            accepted_event_id=event_ids["codex:a1"],
        )
        assert len(scoped) == 1
        assert scoped[0]["observed_sessions"] == 2
        assert scoped[0]["premature_stop_sessions"] == 2
        assert scoped[0]["inspected_stop_sessions"] == 2
        assert scoped[0]["model"] == "model-x"
        assert scoped[0]["cohort_scoped"] is True
        assert scoped[0]["cohort_history_immutable"] is True
        assert scoped[0]["settings_identity_verified"] is True
        assert scoped[0]["project_binding_typed"] is True

        from pex_bridge.fingerprints import fingerprint_score_features

        features = fingerprint_score_features(scoped[0])
        assert features["recommended_overlays"] == ["evidence-before-done"]
        assert features["fingerprint_model"] == "model-x"
        assert len(features["fingerprint_model_settings_hash"]) == 64
        assert features["fingerprint_sample_count"] == 2

        # Planner history is owned by the exact committed plan and bound envelope.
        # The orphan above never counted; corrupt legacy-shaped or malformed rows
        # also remain neutral instead of poisoning the aggregate query.
        await store.db.execute("DROP TRIGGER trg_interventions_bound_update")
        await store.db.execute(
            "UPDATE interventions SET json = ? WHERE id = ?",
            (
                json.dumps(
                    {
                        "schema": "forged.legacy-row.v1",
                        "trigger": "stop",
                        "metadata": {
                            "trigger_event_id": event_ids["codex:a1"],
                            "verification": {"status": "acceptance_gap"},
                        },
                    }
                ),
                "gap-a1",
            ),
        )
        await store.db.commit()
        forged = await store.agent_fingerprint_stats(
            session_id="codex:a1",
            accepted_event_id=event_ids["codex:a1"],
        )
        assert forged[0]["premature_stop_sessions"] == 1
        assert fingerprint_score_features(forged[0])["recommended_overlays"] == []

        await store.db.execute(
            "UPDATE interventions SET json = '{' WHERE id = ?",
            ("gap-a1",),
        )
        await store.db.commit()
        malformed = await store.agent_fingerprint_stats(
            session_id="codex:a1",
            accepted_event_id=event_ids["codex:a1"],
        )
        assert malformed[0]["premature_stop_sessions"] == 1
        assert await store.agent_fingerprint_stats()

        forged_snapshot = sessions[0].model_copy(update={"vendor_session_id": "forged-vendor"})
        await store.db.execute(
            "UPDATE event_processing SET accepted_session_json = ? WHERE event_id = ?",
            (forged_snapshot.model_dump_json(), event_ids["codex:a1"]),
        )
        await store.db.commit()
        assert (
            await store.agent_fingerprint_stats(
                session_id="codex:a1",
                accepted_event_id=event_ids["codex:a1"],
            )
            == []
        )

        nonfinite_snapshot = sessions[0].model_dump(mode="json")
        nonfinite_snapshot["metadata"]["model_settings"]["temperature"] = float("nan")
        await store.db.execute(
            "UPDATE event_processing SET accepted_session_json = ? WHERE event_id = ?",
            (
                json.dumps(nonfinite_snapshot, allow_nan=True),
                event_ids["codex:a1"],
            ),
        )
        await store.db.commit()
        assert (
            await store.agent_fingerprint_stats(
                session_id="codex:a1",
                accepted_event_id=event_ids["codex:a1"],
            )
            == []
        )
    finally:
        await store.close()


def test_decorate_fingerprint_preserves_one_gap_without_recommending_from_one_sample():
    from pex_bridge.fingerprints import decorate_agent_fingerprint

    pretty = decorate_agent_fingerprint(
        {
            "harness": "cursor",
            "observed_sessions": 3,
            "models": ["model-a", "model-b"],
            "premature_stop_sessions": 1,
            "verified_stop_sessions": 1,
            "overlay_sessions": 1,
            "inspected_stop_sessions": 3,
        }
    )
    assert pretty["strengths"] == ["1 inspected STOP supported by the verifier"]
    assert pretty["failure_modes"] == ["1 inspected STOP contradicted or left an acceptance gap"]
    assert pretty["recommended_overlays"] == []
    assert pretty["verified_success_rate"] == pytest.approx(1 / 3)
    assert pretty["premature_stop_rate"] == pytest.approx(1 / 3)
    assert pretty["token_efficiency"] is None
    assert pretty["repeated_tool_rate"] is None
    from pex_bridge.fingerprints import fingerprint_score_features

    features = fingerprint_score_features(
        {
            "harness": "cursor",
            "observed_sessions": 3,
            "models": ["model-a", "model-b"],
            "premature_stop_sessions": 1,
            "verified_stop_sessions": 1,
            "overlay_sessions": 1,
            "inspected_stop_sessions": 3,
        }
    )
    assert features["recommended_overlays"] == []
    assert features["gap_stop_sessions"] == 0

    scoped_features = fingerprint_score_features(
        {
            "harness": "cursor",
            "observed_sessions": 3,
            "models": ["model-a"],
            "premature_stop_sessions": 1,
            "verified_stop_sessions": 1,
            "overlay_sessions": 1,
            "inspected_stop_sessions": 3,
            "cohort_scoped": True,
        }
    )
    assert scoped_features["gap_stop_sessions"] == 0
    assert scoped_features["fingerprint_model"] is None
    assert scoped_features["fingerprint_sample_count"] == 0
    assert scoped_features["fingerprint_confidence"] == 0.0


def test_decorate_fingerprint_recommends_after_two_distinct_gap_sessions():
    from pex_bridge.fingerprints import decorate_agent_fingerprint, fingerprint_score_features

    bucket = {
        "harness": "cursor",
        "observed_sessions": 3,
        "models": ["model-a"],
        "premature_stop_sessions": 2,
        "verified_stop_sessions": 1,
        "overlay_sessions": 0,
        "inspected_stop_sessions": 3,
        "model": "model-a",
        "model_settings_hash": "a" * 64,
        "cohort_scoped": True,
        "cohort_history_immutable": True,
        "settings_identity_verified": True,
        "project_binding_typed": True,
    }

    pretty = decorate_agent_fingerprint(bucket)
    assert pretty["failure_modes"] == ["2 inspected STOPs contradicted or left an acceptance gap"]
    assert pretty["recommended_overlays"] == []
    assert pretty["token_efficiency"] is None
    assert pretty["repeated_tool_rate"] is None

    features = fingerprint_score_features(bucket)
    assert features["recommended_overlays"] == []
    assert features["gap_stop_sessions"] == 0


def test_decorate_fingerprint_does_not_invent_strengths_without_verified_stops():
    from pex_bridge.fingerprints import decorate_agent_fingerprint

    pretty = decorate_agent_fingerprint(
        {
            "harness": "codex",
            "observed_sessions": 2,
            "models": [],
            "premature_stop_sessions": 0,
            "verified_stop_sessions": 0,
            "overlay_sessions": 0,
            "inspected_stop_sessions": 0,
        }
    )
    assert pretty["strengths"] == []
    assert pretty["failure_modes"] == []
    assert pretty["recommended_overlays"] == []
    assert pretty["verified_success_rate"] == 0.0
    assert pretty["token_efficiency"] is None


@pytest.mark.asyncio
async def test_session_listing_paginates_after_activity_ordering(tmp_path: Path):
    store = Store(tmp_path / "sessions.sqlite")
    await store.connect()
    try:
        for index in range(3):
            await store.upsert_session(
                HarnessSession(
                    id=f"codex:{index}",
                    harness_type=HarnessType.CODEX,
                    vendor_session_id=str(index),
                    last_activity=datetime(2026, 1, index + 1, tzinfo=UTC),
                )
            )
        page = await store.list_sessions(limit=1, offset=1)
        assert [session.id for session in page] == ["codex:1"]
        with pytest.raises(ValueError, match="positive"):
            await store.list_sessions(limit=0)
        with pytest.raises(ValueError, match="negative"):
            await store.list_sessions(offset=-1)
    finally:
        await store.close()
