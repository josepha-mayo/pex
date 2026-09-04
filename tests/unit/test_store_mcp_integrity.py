from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta

import pytest
from pex_bridge.store import (
    MCP_REPORT_PROGRESS_TOOL,
    Store,
    reported_progress_request_fingerprint,
    utcnow,
)
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextItem, ProgressEvidenceReference
from pex_protocol.enums import (
    Authority,
    ContextKind,
    EventPhase,
    EventType,
    HarnessType,
    PolicyVerdict,
    Sensitivity,
    SourceKind,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession


async def _bound_store(tmp_path) -> tuple[Store, HarnessSession, Goal]:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = utcnow()
    goal = Goal(
        id="goal-progress",
        project_id="C:/repo",
        title="Progress integrity",
        objective="Accept only provenance-bound progress",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="codex:reporter",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-reporter",
        project_id="C:/repo",
        goal_id=goal.id,
        last_activity=now,
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    return store, session, goal


async def _issue(
    store: Store,
    session: HarnessSession,
    goal: Goal,
    *,
    principal_id: str = "mcp-principal",
    token: str = "only-the-caller-sees-this-token",
    issued_at=None,
) -> tuple[dict, str]:
    issued_at = issued_at or (utcnow() - timedelta(seconds=1))
    digest = hashlib.sha256(token.encode()).hexdigest()
    record = await store.issue_mcp_principal(
        principal_id=principal_id,
        session_id=session.id,
        goal_id=goal.id,
        project_id="C:/repo",
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        scopes=["mcp:read", MCP_REPORT_PROGRESS_TOOL],
        token_digest=digest,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    return record, digest


def _evidence_event(
    event_id: str,
    session: HarnessSession,
    *,
    project_id: str | None = None,
    goal_id: str | None = None,
) -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=utcnow(),
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=project_id,
        goal_id=goal_id,
        event_type=EventType.SHELL,
        command="pytest -q",
        process_state={"pytest": {"ok": True, "exit_code": 0}},
    )


def _progress_artifacts(
    suffix: str,
    session: HarnessSession,
    goal: Goal,
    refs: tuple[ProgressEvidenceReference, ...],
    *,
    summary: str = "Implemented the provenance-safe progress path.",
    intervention_id: str | None = None,
    principal_id: str = "mcp-principal",
):
    now = utcnow()
    canonical_refs = tuple(sorted(refs, key=lambda ref: (ref.type, ref.id)))
    labels = [f"{ref.type}:{ref.id}" for ref in canonical_refs]
    event = HarnessEvent(
        event_id=f"mcp-progress-{suffix}",
        ts=now,
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=goal.id,
        event_type=EventType.AGENT_RESPONSE,
        phase=EventPhase.AFTER,
        message_delta=summary,
    )
    item = ContextItem(
        id=f"ctx-progress-{suffix}",
        project_id=session.project_id or goal.project_id,
        goal_id=goal.id,
        kind=ContextKind.RESULT,
        content=summary,
        source_refs=labels,
        provenance=SourceKind.HARNESS,
        confidence=0.4,
        relevance_tags=["progress", "unverified"],
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
        metadata={"source_session_id": session.id, "status": "reported"},
    )
    action = ProposedAction(
        type=InterventionType.ANNOTATE,
        session_id=session.id,
        goal_id=goal.id,
        payload={"context_id": item.id, "channel": "mcp"},
        rationale="Worker reported progress with provenance references.",
        evidence=labels[:12],
        confidence=0.4,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
    )
    intervention = Intervention(
        id=intervention_id or f"int-progress-{suffix}",
        session_id=session.id,
        goal_id=goal.id,
        trigger=event.event_type.value,
        evidence=action.evidence,
        diagnosis="mcp_reported_progress",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="annotated",
        created_at=now,
        metadata={"progress_context_id": item.id, "trigger_event_id": event.event_id},
    )
    response = {
        "ok": True,
        "verified": False,
        "item": item.model_dump(mode="json"),
        "intervention": intervention.model_dump(mode="json"),
    }
    fingerprint = reported_progress_request_fingerprint(
        principal_id=principal_id,
        tool=MCP_REPORT_PROGRESS_TOOL,
        session_id=session.id,
        goal_id=goal.id,
        project_id=session.project_id or goal.project_id,
        summary=summary,
        evidence_refs=canonical_refs,
    )
    return event, item, intervention, response, fingerprint


@pytest.mark.asyncio
async def test_event_ingest_stamps_immutable_goal_and_project_bindings(tmp_path):
    store, session, goal = await _bound_store(tmp_path)
    try:
        event = _evidence_event("evt-bound", session)
        assert event.goal_id is None
        assert event.project_id is None
        assert await store.add_event(event) is True
        assert event.goal_id == goal.id
        assert event.project_id == session.project_id

        replay = _evidence_event("evt-bound", session)
        replay.ts = event.ts
        assert await store.add_event(replay) is False

        conflicting = _evidence_event(
            "evt-conflict",
            session,
            project_id="C:/foreign",
            goal_id="goal-foreign",
        )
        with pytest.raises(ValueError, match="project identity mismatch"):
            await store.add_event(conflicting)

        legacy = _evidence_event("evt-legacy", session)
        await store.db.execute(
            "INSERT INTO events(event_id, session_id, ts, json) VALUES (?, ?, ?, ?)",
            (legacy.event_id, legacy.session_id, legacy.ts.isoformat(), legacy.model_dump_json()),
        )
        await store.db.commit()
        assert await store.add_event(legacy.model_copy(deep=True)) is False
        stored_legacy = await store.get_event(legacy.event_id)
        assert stored_legacy is not None
        assert stored_legacy.goal_id is None
        assert stored_legacy.project_id is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_principal_issue_rotates_atomically_and_never_stores_raw_token(tmp_path):
    store, session, goal = await _bound_store(tmp_path)
    token_one = "raw-token-one-must-never-be-durable"
    token_two = "raw-token-two-must-never-be-durable"
    try:
        first, digest_one = await _issue(
            store,
            session,
            goal,
            principal_id="principal-one",
            token=token_one,
        )
        assert first["scopes"] == ["mcp:read", "pex.report_progress"]
        assert await store.get_mcp_principal_by_digest(digest_one) == first

        second_issued = utcnow()
        second, digest_two = await _issue(
            store,
            session,
            goal,
            principal_id="principal-two",
            token=token_two,
            issued_at=second_issued,
        )
        assert await store.get_mcp_principal_by_digest(digest_one) is None
        assert await store.get_mcp_principal_by_digest(digest_two) == second
        assert (
            await _issue(
                store,
                session,
                goal,
                principal_id="principal-two",
                token=token_two,
                issued_at=second_issued,
            )
        )[0] == second

        cursor = await store.db.execute("SELECT token_digest, json FROM mcp_principals")
        durable_text = "\n".join(
            f"{row['token_digest']} {row['json']}" for row in await cursor.fetchall()
        )
        assert token_one not in durable_text
        assert token_two not in durable_text
        assert digest_one in durable_text
        assert digest_two in durable_text

        assert await store.revoke_mcp_principals_for_session(
            session.id,
            revoked_at=second_issued + timedelta(seconds=1),
        ) == 1
        assert await store.get_mcp_principal_by_digest(digest_two) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_progress_commit_is_atomic_and_concurrent_retries_replay(tmp_path):
    store, session, goal = await _bound_store(tmp_path)
    try:
        principal, digest = await _issue(store, session, goal)
        evidence = _evidence_event("evt-proof", session)
        await store.add_event(evidence)
        evidence_context = ContextItem(
            id="ctx-proof",
            project_id=goal.project_id,
            goal_id=goal.id,
            kind=ContextKind.FACT,
            content="The implementation artifact exists.",
            valid_from=utcnow(),
            metadata={"source_session_id": session.id},
        )
        await store.add_context(evidence_context)
        refs = (
            ProgressEvidenceReference(type="event", id=evidence.event_id),
            ProgressEvidenceReference(type="context", id=evidence_context.id),
        )
        fingerprint_forward = reported_progress_request_fingerprint(
            principal_id=principal["principal_id"],
            tool=MCP_REPORT_PROGRESS_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=goal.project_id,
            summary="Implemented the provenance-safe progress path.",
            evidence_refs=refs,
        )
        fingerprint_reverse = reported_progress_request_fingerprint(
            principal_id=principal["principal_id"],
            tool=MCP_REPORT_PROGRESS_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=goal.project_id,
            summary="Implemented the provenance-safe progress path.",
            evidence_refs=tuple(reversed(refs)),
        )
        assert fingerprint_forward == fingerprint_reverse
        fingerprint_other_principal = reported_progress_request_fingerprint(
            principal_id="other-principal",
            tool=MCP_REPORT_PROGRESS_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=goal.project_id,
            summary="Implemented the provenance-safe progress path.",
            evidence_refs=refs,
        )
        assert fingerprint_other_principal != fingerprint_forward

        async def commit(suffix: str):
            event, item, intervention, response, fingerprint = _progress_artifacts(
                suffix,
                session,
                goal,
                refs,
            )
            assert item.source_refs == ["context:ctx-proof", "event:evt-proof"]
            return await store.commit_reported_progress(
                principal_id=principal["principal_id"],
                tool=MCP_REPORT_PROGRESS_TOOL,
                request_id="request-concurrent",
                request_fingerprint=fingerprint,
                evidence_refs=refs,
                event=event,
                context_item=item,
                intervention=intervention,
                response=response,
            )

        results = await asyncio.gather(commit("one"), commit("two"))
        assert sorted(result["created"] for result in results) == [False, True]
        assert len({result["mutation_id"] for result in results}) == 1
        assert len({result["event_id"] for result in results}) == 1
        assert results[0]["response"] == results[1]["response"]

        for table in ("mcp_mutations", "interventions", "intervention_audit"):
            cursor = await store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
            assert int((await cursor.fetchone())["count"]) == 1
        cursor = await store.db.execute(
            "SELECT COUNT(*) AS count FROM events WHERE event_id LIKE 'mcp-progress-%'"
        )
        assert int((await cursor.fetchone())["count"]) == 1
        cursor = await store.db.execute(
            "SELECT COUNT(*) AS count FROM context_items WHERE id LIKE 'ctx-progress-%'"
        )
        assert int((await cursor.fetchone())["count"]) == 1

        event, item, intervention, response, fingerprint = _progress_artifacts(
            "replay",
            session,
            goal,
            refs,
        )
        replay = await store.commit_reported_progress(
            principal_id=principal["principal_id"],
            tool=MCP_REPORT_PROGRESS_TOOL,
            request_id="request-concurrent",
            request_fingerprint=fingerprint,
            evidence_refs=refs,
            event=event,
            context_item=item,
            intervention=intervention,
            response=response,
        )
        assert replay["created"] is False
        assert replay["event_id"] == results[0]["event_id"]

        changed = _progress_artifacts(
            "changed",
            session,
            goal,
            refs,
            summary="This is materially different progress.",
        )
        with pytest.raises(ValueError, match="reused with new content"):
            await store.commit_reported_progress(
                principal_id=principal["principal_id"],
                tool=MCP_REPORT_PROGRESS_TOOL,
                request_id="request-concurrent",
                request_fingerprint=changed[4],
                evidence_refs=refs,
                event=changed[0],
                context_item=changed[1],
                intervention=changed[2],
                response=changed[3],
            )

        audit = json.loads(store.audit_path.read_text(encoding="utf-8").splitlines()[0])
        assert audit["mcp_principal_id"] == principal["principal_id"]
        assert audit["mcp_mutation_id"] == results[0]["mutation_id"]
        assert "token" not in json.dumps(audit).casefold()
        assert "fingerprint" not in json.dumps(audit).casefold()
        assert "request-concurrent" not in json.dumps(audit)
        assert digest not in json.dumps(audit)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_progress_commit_rolls_back_every_new_row_on_late_collision(tmp_path):
    store, session, goal = await _bound_store(tmp_path)
    try:
        principal, _digest = await _issue(store, session, goal)
        evidence = _evidence_event("evt-rollback-proof", session)
        await store.add_event(evidence)
        refs = (ProgressEvidenceReference(type="event", id=evidence.event_id),)
        conflict = _progress_artifacts("existing", session, goal, refs)[2]
        await store.add_intervention(conflict)
        before_audit = await store.db.execute("SELECT COUNT(*) AS count FROM intervention_audit")
        before_count = int((await before_audit.fetchone())["count"])

        event, item, intervention, response, fingerprint = _progress_artifacts(
            "rollback",
            session,
            goal,
            refs,
            intervention_id=conflict.id,
        )
        with pytest.raises(ValueError, match="artifact id collision"):
            await store.commit_reported_progress(
                principal_id=principal["principal_id"],
                tool=MCP_REPORT_PROGRESS_TOOL,
                request_id="request-rollback",
                request_fingerprint=fingerprint,
                evidence_refs=refs,
                event=event,
                context_item=item,
                intervention=intervention,
                response=response,
            )

        assert await store.get_event(event.event_id) is None
        assert await store.get_context(item.id) is None
        cursor = await store.db.execute(
            "SELECT COUNT(*) AS count FROM mcp_mutations WHERE request_id = ?",
            ("request-rollback",),
        )
        assert int((await cursor.fetchone())["count"]) == 0
        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM intervention_audit")
        assert int((await cursor.fetchone())["count"]) == before_count
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_progress_commit_rejects_foreign_private_stale_and_superseded_evidence(
    tmp_path,
):
    store, session, goal = await _bound_store(tmp_path)
    try:
        principal, _digest = await _issue(store, session, goal)
        foreign = HarnessSession(
            id="codex:foreign",
            harness_type=HarnessType.CODEX,
            vendor_session_id="foreign-thread",
            project_id=goal.project_id,
            goal_id=goal.id,
            last_activity=utcnow(),
        )
        await store.upsert_session(foreign)
        foreign_event = _evidence_event("evt-foreign", foreign)
        await store.add_event(foreign_event)
        unbound_event = _evidence_event("evt-unbound", session)
        wrong_project_event = _evidence_event(
            "evt-wrong-project",
            session,
            project_id="C:/foreign",
            goal_id=goal.id,
        )
        wrong_goal_event = _evidence_event(
            "evt-wrong-goal",
            session,
            project_id=goal.project_id,
            goal_id="goal-foreign",
        )
        await store.db.executemany(
            "INSERT INTO events(event_id, session_id, ts, json) VALUES (?, ?, ?, ?)",
            [
                (
                    event.event_id,
                    event.session_id,
                    event.ts.isoformat(),
                    event.model_dump_json(),
                )
                for event in (unbound_event, wrong_project_event, wrong_goal_event)
            ],
        )
        await store.db.commit()

        contexts = [
            ContextItem(
                id="ctx-secret-proof",
                project_id=goal.project_id,
                goal_id=goal.id,
                kind=ContextKind.FACT,
                content="secret proof",
                valid_from=utcnow(),
                sensitivity=Sensitivity.SECRET,
                metadata={"source_session_id": session.id},
            ),
            ContextItem(
                id="ctx-stale-proof",
                project_id=goal.project_id,
                goal_id=goal.id,
                kind=ContextKind.FACT,
                content="stale proof",
                valid_from=utcnow() - timedelta(hours=2),
                stale_after=utcnow() - timedelta(hours=1),
                metadata={"source_session_id": session.id},
            ),
            ContextItem(
                id="ctx-old-proof",
                project_id=goal.project_id,
                goal_id=goal.id,
                kind=ContextKind.FACT,
                content="old proof",
                valid_from=utcnow(),
                metadata={"source_session_id": session.id},
            ),
            ContextItem(
                id="ctx-foreign-source",
                project_id=goal.project_id,
                goal_id=goal.id,
                kind=ContextKind.FACT,
                content="foreign reporter proof",
                valid_from=utcnow(),
                metadata={"source_session_id": foreign.id},
            ),
            ContextItem(
                id="ctx-new-proof",
                project_id=goal.project_id,
                goal_id=goal.id,
                kind=ContextKind.FACT,
                content="replacement proof",
                valid_from=utcnow(),
                supersedes="ctx-old-proof",
                metadata={"source_session_id": session.id},
            ),
        ]
        for context in contexts:
            await store.add_context(context)

        cases = [
            ProgressEvidenceReference(type="event", id=foreign_event.event_id),
            ProgressEvidenceReference(type="event", id=unbound_event.event_id),
            ProgressEvidenceReference(type="event", id=wrong_project_event.event_id),
            ProgressEvidenceReference(type="event", id=wrong_goal_event.event_id),
            ProgressEvidenceReference(type="context", id="ctx-secret-proof"),
            ProgressEvidenceReference(type="context", id="ctx-stale-proof"),
            ProgressEvidenceReference(type="context", id="ctx-old-proof"),
            ProgressEvidenceReference(type="context", id="ctx-foreign-source"),
        ]
        for index, evidence_ref in enumerate(cases):
            refs = (evidence_ref,)
            event, item, intervention, response, fingerprint = _progress_artifacts(
                f"rejected-{index}",
                session,
                goal,
                refs,
            )
            with pytest.raises(ValueError, match="evidence"):
                await store.commit_reported_progress(
                    principal_id=principal["principal_id"],
                    tool=MCP_REPORT_PROGRESS_TOOL,
                    request_id=f"request-rejected-{index}",
                    request_fingerprint=fingerprint,
                    evidence_refs=refs,
                    event=event,
                    context_item=item,
                    intervention=intervention,
                    response=response,
                )
            assert await store.get_event(event.event_id) is None
            assert await store.get_context(item.id) is None

        cursor = await store.db.execute("SELECT COUNT(*) AS count FROM mcp_mutations")
        assert int((await cursor.fetchone())["count"]) == 0
    finally:
        await store.close()
