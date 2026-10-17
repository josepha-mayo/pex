from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta

import pytest
from pex_bridge.store import (
    MCP_VERIFY_CLAIM_TOOL,
    Store,
    claim_verification_request_fingerprint,
    claim_verification_subject_fingerprint,
    utcnow,
)
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextItem
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


async def _bound_store(tmp_path) -> tuple[Store, HarnessSession, Goal, dict]:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = utcnow()
    goal = Goal(
        id="goal-verify",
        project_id="C:/repo",
        title="Verification integrity",
        objective="Verify claims only from current bound evidence",
        acceptance_criteria=["tests pass"],
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id="codex:verifier",
        harness_type=HarnessType.CODEX,
        vendor_session_id="thread-verifier",
        project_id="C:/repo",
        goal_id=goal.id,
        last_activity=now,
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    token = "verify-token-visible-only-to-caller"
    issued_at = utcnow() - timedelta(seconds=1)
    principal = await store.issue_mcp_principal(
        principal_id="mcp-verify-principal",
        session_id=session.id,
        goal_id=goal.id,
        project_id="C:/repo",
        vendor_session_id=session.vendor_session_id,
        harness_type=session.harness_type.value,
        scopes=["mcp:read", MCP_VERIFY_CLAIM_TOOL],
        token_digest=hashlib.sha256(token.encode()).hexdigest(),
        issued_at=issued_at,
        expires_at=issued_at + timedelta(hours=1),
    )
    return store, session, goal, principal


def _pytest_event(
    event_id: str,
    session: HarnessSession,
    *,
    goal_id: str,
) -> HarnessEvent:
    return HarnessEvent(
        event_id=event_id,
        ts=utcnow(),
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=goal_id,
        event_type=EventType.SHELL,
        command="uv run pytest -q",
        process_state={"pytest": {"ok": True, "exit_code": 0}},
    )


def _verification_artifacts(
    suffix: str,
    session: HarnessSession,
    goal: Goal,
    *,
    principal_id: str,
    evidence_ids: tuple[str, ...] = (),
    statement: str = "All tests passed.",
    outcome: str = "supported",
):
    now = utcnow()
    event = HarnessEvent(
        event_id=f"mcp-verify-{suffix}",
        ts=now,
        harness_type=session.harness_type,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=goal.id,
        event_type=EventType.AGENT_RESPONSE,
        phase=EventPhase.AFTER,
        message_delta=statement,
    )
    extracted = {
        "statement": statement,
        "kind": "tests_pass",
        "polarity": "asserted",
        "confidence": 0.9,
        "source_event_id": event.event_id,
        "source_event_type": event.event_type.value,
    }
    claim = ContextItem(
        id=f"claim-verify-{suffix}",
        project_id=session.project_id or goal.project_id,
        goal_id=goal.id,
        kind=ContextKind.CLAIM,
        content=statement,
        source_refs=[event.event_id],
        provenance=SourceKind.HARNESS,
        confidence=0.9,
        relevance_tags=["tests_pass", "asserted"],
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
        metadata={
            **extracted,
            "source_session_id": session.id,
            "status": "reported",
            "verified": False,
        },
    )
    subject_fingerprint = claim_verification_subject_fingerprint(
        session_id=session.id,
        goal_id=goal.id,
        project_id=session.project_id or goal.project_id,
        claim=statement,
    )
    receipt = ContextItem(
        id=f"receipt-verify-{suffix}",
        project_id=session.project_id or goal.project_id,
        goal_id=goal.id,
        kind=ContextKind.RESULT,
        content=f"Claim verification outcome: {outcome}.",
        source_refs=[event.event_id, *evidence_ids],
        provenance=SourceKind.PEX,
        confidence=0.95 if outcome != "uncertain" else 0.5,
        relevance_tags=["claim_verification", outcome],
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
        metadata={
            "receipt_type": "mcp_claim_verification",
            "source_session_id": session.id,
            "status": outcome,
            "raw_status": outcome,
            "verified": False,
            "evidence": [],
            "correction": None,
            "claim_fingerprint": subject_fingerprint,
            "valid_as_of": now.isoformat(),
            "superseded": False,
            "superseded_by": None,
        },
    )
    results = [receipt]
    if outcome == "supported":
        assert evidence_ids
        results.append(
            ContextItem(
                id=f"result-verify-{suffix}",
                project_id=session.project_id or goal.project_id,
                goal_id=goal.id,
                kind=ContextKind.RESULT,
                content=f"{statement} Verified by: pytest_ok=True.",
                source_refs=[event.event_id, evidence_ids[-1]],
                provenance=SourceKind.TEST,
                confidence=0.95,
                relevance_tags=["tests_pass", "verified"],
                valid_from=now,
                sensitivity=Sensitivity.INTERNAL,
                metadata={
                    "verified": True,
                    "status": "supported",
                    "evidence": ["pytest_ok=True"],
                    "claim": extracted,
                    "source_session_id": session.id,
                    "claim_fingerprint": subject_fingerprint,
                    "valid_as_of": now.isoformat(),
                    "superseded": False,
                    "superseded_by": None,
                },
            )
        )
    contexts = [claim, *results]
    action_evidence = [f"event:{event.event_id}"] + [
        f"event:{event_id}" for event_id in evidence_ids
    ]
    action = ProposedAction(
        type=InterventionType.ANNOTATE,
        session_id=session.id,
        goal_id=goal.id,
        payload={
            "context_ids": [item.id for item in contexts],
            "verification_context_id": receipt.id,
            "channel": "mcp",
        },
        rationale="Persist a bounded claim-verification receipt with scoped evidence.",
        evidence=action_evidence[:12],
        confidence=0.95 if outcome != "uncertain" else 0.5,
        risk=RiskLevel.LOW,
        reversible=True,
        authority_required=Authority.LOCAL_POLICY,
    )
    verification = {
        "status": outcome,
        "raw_status": outcome,
        "evidence_event_ids": list(evidence_ids),
        "evidence": [],
        "correction": None,
    }
    intervention = Intervention(
        id=f"int-verify-{suffix}",
        session_id=session.id,
        goal_id=goal.id,
        trigger=event.event_type.value,
        evidence=action.evidence,
        diagnosis="mcp_claim_verification",
        proposed_action=action,
        confidence=action.confidence,
        risk=action.risk.value,
        reversible=action.reversible,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="annotated",
        outcome=f"claim_verification_{outcome}",
        created_at=now,
        metadata={
            "claims": [extracted],
            "verification": verification,
            "trigger_event_id": event.event_id,
        },
    )
    verified = [item for item in results if item.metadata.get("verified") is True]
    status = "verified" if outcome == "supported" else outcome
    response = {
        "status": status,
        "raw_status": outcome,
        "outcome": outcome,
        "verified": outcome == "supported",
        "valid_as_of": now.isoformat(),
        "claims": [extracted],
        "evidence": [],
        "correction": None,
        "verified_items": [item.model_dump(mode="json") for item in verified],
        "item": receipt.model_dump(mode="json"),
        "intervention": intervention.model_dump(mode="json"),
    }
    fingerprint = claim_verification_request_fingerprint(
        principal_id=principal_id,
        tool=MCP_VERIFY_CLAIM_TOOL,
        session_id=session.id,
        goal_id=goal.id,
        project_id=session.project_id or goal.project_id,
        claim=statement,
    )
    return event, [claim], results, intervention, response, fingerprint


async def _commit(
    store: Store,
    principal_id: str,
    request_id: str,
    evidence_ids: tuple[str, ...],
    artifacts,
):
    event, claims, results, intervention, response, fingerprint = artifacts
    return await store.commit_claim_verification(
        principal_id=principal_id,
        tool=MCP_VERIFY_CLAIM_TOOL,
        request_id=request_id,
        request_fingerprint=fingerprint,
        evidence_event_ids=evidence_ids,
        event=event,
        claim_items=claims,
        result_items=results,
        intervention=intervention,
        response=response,
    )


@pytest.mark.asyncio
async def test_claim_verification_commit_is_atomic_concurrent_and_replay_safe(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        proof = _pytest_event("pytest-proof", session, goal_id=goal.id)
        await store.add_event(proof)
        principal_id = principal["principal_id"]
        evidence_ids = (proof.event_id,)

        results = await asyncio.gather(
            _commit(
                store,
                principal_id,
                "verify-concurrent-0001",
                evidence_ids,
                _verification_artifacts(
                    "one",
                    session,
                    goal,
                    principal_id=principal_id,
                    evidence_ids=evidence_ids,
                ),
            ),
            _commit(
                store,
                principal_id,
                "verify-concurrent-0001",
                evidence_ids,
                _verification_artifacts(
                    "two",
                    session,
                    goal,
                    principal_id=principal_id,
                    evidence_ids=evidence_ids,
                ),
            ),
        )

        assert sorted(item["created"] for item in results) == [False, True]
        assert len({item["mutation_id"] for item in results}) == 1
        assert len({item["event_id"] for item in results}) == 1
        assert results[0]["response"] == results[1]["response"]
        for table in ("mcp_mutations", "interventions", "intervention_audit"):
            cursor = await store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
            assert int((await cursor.fetchone())["count"]) == 1

        replay = await _commit(
            store,
            principal_id,
            "verify-concurrent-0001",
            evidence_ids,
            _verification_artifacts(
                "replay",
                session,
                goal,
                principal_id=principal_id,
                evidence_ids=evidence_ids,
            ),
        )
        assert replay["created"] is False
        assert replay["event_id"] == results[0]["event_id"]

        changed = _verification_artifacts(
            "changed",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=evidence_ids,
            statement="The deployment is complete.",
        )
        with pytest.raises(ValueError, match="reused with new content"):
            await _commit(
                store,
                principal_id,
                "verify-concurrent-0001",
                evidence_ids,
                changed,
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_claim_verification_rejects_old_goal_evidence_at_final_transaction(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        old_goal = Goal(
            id="goal-old",
            project_id=goal.project_id,
            title="Old goal",
            objective="Old objective",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        await store.upsert_goal(old_goal)
        old_proof = _pytest_event("pytest-old-goal", session, goal_id=old_goal.id)
        await store.db.execute(
            "INSERT INTO events(event_id, session_id, ts, json) VALUES (?, ?, ?, ?)",
            (
                old_proof.event_id,
                old_proof.session_id,
                old_proof.ts.isoformat(),
                old_proof.model_dump_json(),
            ),
        )
        await store.db.commit()
        principal_id = principal["principal_id"]
        before = {}
        for table in ("events", "context_items", "interventions", "mcp_mutations"):
            cursor = await store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
            before[table] = int((await cursor.fetchone())["count"])

        artifacts = _verification_artifacts(
            "old-goal",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=(old_proof.event_id,),
        )
        with pytest.raises(ValueError, match="evidence event binding mismatch"):
            await _commit(
                store,
                principal_id,
                "verify-old-goal-0001",
                (old_proof.event_id,),
                artifacts,
            )

        for table, expected in before.items():
            cursor = await store.db.execute(f"SELECT COUNT(*) AS count FROM {table}")
            assert int((await cursor.fetchone())["count"]) == expected
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_claim_verification_goal_rebind_and_collision_leave_no_partial_rows(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        collision = _verification_artifacts(
            "collision",
            session,
            goal,
            principal_id=principal_id,
            outcome="uncertain",
        )
        await store.add_context(collision[2][0])
        with pytest.raises(ValueError, match="artifact id collision"):
            await _commit(
                store,
                principal_id,
                "verify-collision-0001",
                (),
                collision,
            )
        assert await store.get_event(collision[0].event_id) is None
        assert await store.get_context(collision[1][0].id) is None
        assert await store.get_intervention(collision[3].id) is None

        replacement = Goal(
            id="goal-replacement",
            project_id=goal.project_id,
            title="Replacement",
            objective="Replacement objective",
            supersedes=goal.id,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        await store.supersede_goal(goal.id, replacement)
        rebound = _verification_artifacts(
            "rebound",
            session,
            goal,
            principal_id=principal_id,
            outcome="uncertain",
        )
        with pytest.raises(
            PermissionError,
            match="expired or revoked|binding changed|superseded",
        ):
            await _commit(
                store,
                principal_id,
                "verify-rebound-0001",
                (),
                rebound,
            )
        assert await store.get_event(rebound[0].event_id) is None
        assert await store.get_context(rebound[1][0].id) is None
        assert await store.get_intervention(rebound[3].id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_non_supported_verification_cannot_smuggle_verified_context(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        artifacts = _verification_artifacts(
            "smuggled",
            session,
            goal,
            principal_id=principal_id,
            outcome="uncertain",
        )
        receipt = artifacts[2][0]
        receipt.metadata["verified"] = True
        artifacts[4]["verified_items"] = [receipt.model_dump(mode="json")]
        artifacts[4]["item"] = receipt.model_dump(mode="json")

        with pytest.raises(ValueError, match="only a supported outcome"):
            await _commit(
                store,
                principal_id,
                "verify-smuggled-0001",
                (),
                artifacts,
            )
        assert await store.get_event(artifacts[0].event_id) is None
        assert await store.get_context(receipt.id) is None
        assert await store.get_intervention(artifacts[3].id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_supported_verification_cannot_self_verify_pex_receipt(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        proof = _pytest_event("pytest-proof-self-verify", session, goal_id=goal.id)
        await store.add_event(proof)
        artifacts = _verification_artifacts(
            "self-verified-receipt",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=(proof.event_id,),
        )
        receipt = artifacts[2][0]
        receipt.metadata["verified"] = True
        artifacts[4]["item"] = receipt.model_dump(mode="json")
        artifacts[4]["verified_items"] = [
            item.model_dump(mode="json")
            for item in artifacts[2]
            if item.metadata.get("verified") is True
        ]

        with pytest.raises(
            ValueError,
            match="independent test or workspace provenance|receipt cannot be verified",
        ):
            await _commit(
                store,
                principal_id,
                "verify-self-receipt-0001",
                (proof.event_id,),
                artifacts,
            )
        assert await store.get_event(artifacts[0].event_id) is None
        assert await store.get_context(receipt.id) is None
        assert await store.get_intervention(artifacts[3].id) is None
    finally:
        await store.close()


def _convert_supported_result_to_workspace(artifacts) -> ContextItem:
    event, _claims, results, _intervention, response, _fingerprint = artifacts
    workspace_result = results[1]
    workspace_result.provenance = SourceKind.WORKSPACE
    workspace_result.source_refs = [
        event.event_id,
        f"workspace_snapshot:{event.event_id}",
    ]
    workspace_result.metadata["evidence"] = ["exists:README.md"]
    response["verified_items"] = [workspace_result.model_dump(mode="json")]
    return workspace_result


@pytest.mark.asyncio
async def test_verified_workspace_result_requires_durable_snapshot_receipt(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        proof = _pytest_event("workspace-unused-proof", session, goal_id=goal.id)
        await store.add_event(proof)
        artifacts = _verification_artifacts(
            "workspace-no-snapshot",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=(proof.event_id,),
        )
        workspace_result = _convert_supported_result_to_workspace(artifacts)

        with pytest.raises(ValueError, match="durable snapshot receipt"):
            await _commit(
                store,
                principal_id,
                "verify-workspace-no-snapshot-0001",
                (proof.event_id,),
                artifacts,
            )
        assert await store.get_event(artifacts[0].event_id) is None
        assert await store.get_context(workspace_result.id) is None
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_verified_workspace_result_is_bound_to_canonical_snapshot_receipt(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        proof = _pytest_event("workspace-bound-proof", session, goal_id=goal.id)
        await store.add_event(proof)
        artifacts = _verification_artifacts(
            "workspace-bound",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=(proof.event_id,),
        )
        workspace_result = _convert_supported_result_to_workspace(artifacts)
        artifacts[0].metadata["workspace_snapshot"] = {
            "source": "pex_workspace_snapshot",
            "captured_at": artifacts[0].ts.isoformat(),
            "sha256": "a" * 64,
            "evidence": ["exists:README.md"],
        }

        committed = await _commit(
            store,
            principal_id,
            "verify-workspace-bound-0001",
            (proof.event_id,),
            artifacts,
        )

        assert committed["created"] is True
        stored = await store.get_context(workspace_result.id)
        assert stored is not None
        assert stored.provenance == SourceKind.WORKSPACE
        assert stored.source_refs == workspace_result.source_refs
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_uncertain_does_not_supersede_standing_supported_receipt(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        proof = _pytest_event("pytest-proof-uncertain-guard", session, goal_id=goal.id)
        await store.add_event(proof)
        evidence_ids = (proof.event_id,)
        supported = _verification_artifacts(
            "supported-stands",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=evidence_ids,
        )
        await _commit(store, principal_id, "verify-stands-0001", evidence_ids, supported)
        supported_receipt_id = supported[2][0].id
        supported_verified_id = supported[2][1].id

        uncertain = _verification_artifacts(
            "uncertain-no-supersede",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=(),
            outcome="uncertain",
        )
        await _commit(store, principal_id, "verify-uncertain-0001", (), uncertain)

        stale_receipt = await store.get_context(supported_receipt_id)
        assert stale_receipt is not None
        assert stale_receipt.metadata["superseded"] is False
        assert stale_receipt.metadata["superseded_by"] is None
        stale_verified = await store.get_context(supported_verified_id)
        assert stale_verified is not None
        assert stale_verified.metadata["superseded"] is False
        assert stale_verified.metadata["superseded_by"] is None
        new_receipt = await store.get_context(uncertain[2][0].id)
        assert new_receipt is not None
        assert new_receipt.metadata["superseded"] is False
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_contradicted_supersedes_with_temporal_guard_and_timestamp(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        proof = _pytest_event("pytest-proof-temporal", session, goal_id=goal.id)
        await store.add_event(proof)
        evidence_ids = (proof.event_id,)
        supported = _verification_artifacts(
            "supported-temporal",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=evidence_ids,
        )
        await _commit(store, principal_id, "verify-temporal-0001", evidence_ids, supported)
        supported_receipt_id = supported[2][0].id
        supported_valid = supported[2][0].metadata["valid_as_of"]

        failed = _pytest_event("pytest-failed-temporal", session, goal_id=goal.id)
        failed.process_state = {"pytest": {"ok": False, "exit_code": 1}}
        await store.add_event(failed)
        contradicted = _verification_artifacts(
            "contradicted-temporal",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=(failed.event_id,),
            outcome="contradicted",
        )
        await _commit(store, principal_id, "verify-temporal-0002", (failed.event_id,), contradicted)
        new_receipt_id = contradicted[2][0].id
        new_valid = contradicted[2][0].metadata["valid_as_of"]
        assert supported_valid <= new_valid

        stale = await store.get_context(supported_receipt_id)
        assert stale is not None
        assert stale.metadata["superseded"] is True
        assert stale.metadata["superseded_by"] == new_receipt_id
        assert isinstance(stale.metadata.get("superseded_at"), str)
        # Commit-time retirement cannot precede the retiring receipt's validity.
        assert stale.metadata["superseded_at"] >= new_valid
        # Superseded receipts leave the handoff read path.
        listed = await store.list_context_for_authority(
            session.project_id or goal.project_id,
            goal_id=goal.id,
            observed_at=utcnow(),
            limit=1000,
        )
        listed_ids = {item.id for item in listed}
        assert supported_receipt_id not in listed_ids
        assert new_receipt_id in listed_ids
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_unicode_rephrased_contradiction_retires_same_subject_trail(tmp_path):
    """A unicode-punctuated restatement must supersede the standing receipt.

    Exercises the extended subject normalization and the in-txn subject
    fingerprint recompute: both commits pass through the live-row assertion,
    and the contradicted unicode restatement retires the ASCII receipt.
    """
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        proof = _pytest_event("pytest-proof-unicode-trail", session, goal_id=goal.id)
        await store.add_event(proof)
        evidence_ids = (proof.event_id,)
        supported = _verification_artifacts(
            "supported-unicode-trail",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=evidence_ids,
            statement="All tests passed.",
        )
        await _commit(store, principal_id, "verify-unicode-trail-0001", evidence_ids, supported)
        supported_receipt_id = supported[2][0].id

        failed = _pytest_event("pytest-failed-unicode-trail", session, goal_id=goal.id)
        failed.process_state = {"pytest": {"ok": False, "exit_code": 1}}
        await store.add_event(failed)
        contradicted = _verification_artifacts(
            "contradicted-unicode-trail",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=(failed.event_id,),
            statement="All tests passed\u2026",
            outcome="contradicted",
        )
        await _commit(
            store,
            principal_id,
            "verify-unicode-trail-0002",
            (failed.event_id,),
            contradicted,
        )

        stale = await store.get_context(supported_receipt_id)
        assert stale is not None
        assert stale.metadata["superseded"] is True
        assert stale.metadata["superseded_by"] == contradicted[2][0].id
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_handoff_read_path_excludes_claim_superseded_receipts(tmp_path):
    """Pin the idle-sibling handoff read path against retired receipts.

    ``Pipeline._maybe_auto_handoff`` lists context with include_project_wide
    and an observation time; a claim-superseded receipt must never re-enter
    selection there, mirroring the goal-succession exclusion.
    """
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        principal_id = principal["principal_id"]
        proof = _pytest_event("pytest-proof-handoff-path", session, goal_id=goal.id)
        await store.add_event(proof)
        evidence_ids = (proof.event_id,)
        supported = _verification_artifacts(
            "supported-handoff-path",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=evidence_ids,
        )
        await _commit(store, principal_id, "verify-handoff-path-0001", evidence_ids, supported)
        supported_receipt_id = supported[2][0].id

        failed = _pytest_event("pytest-failed-handoff-path", session, goal_id=goal.id)
        failed.process_state = {"pytest": {"ok": False, "exit_code": 1}}
        await store.add_event(failed)
        contradicted = _verification_artifacts(
            "contradicted-handoff-path",
            session,
            goal,
            principal_id=principal_id,
            evidence_ids=(failed.event_id,),
            outcome="contradicted",
        )
        await _commit(
            store,
            principal_id,
            "verify-handoff-path-0002",
            (failed.event_id,),
            contradicted,
        )
        new_receipt_id = contradicted[2][0].id

        listed = await store.list_context_for_authority(
            session.project_id or goal.project_id,
            goal_id=goal.id,
            include_project_wide=True,
            prioritize_human_commitments=True,
            observed_at=utcnow(),
            limit=1000,
        )
        listed_ids = {item.id for item in listed}
        assert supported_receipt_id not in listed_ids
        assert new_receipt_id in listed_ids
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_subject_fingerprint_normalization_and_isolation(tmp_path):
    store, session, goal, principal = await _bound_store(tmp_path)
    try:
        project = session.project_id or goal.project_id
        base = claim_verification_subject_fingerprint(
            session_id=session.id,
            goal_id=goal.id,
            project_id=project,
            claim="All tests passed.",
        )
        for variant in (
            "all tests passed",
            "ALL  TESTS   PASSED!",
            "  All Tests Passed...  ",
            "all tests passed?",
            # Unicode trailing-punctuation variants retire the same trail.
            "All tests passed\u2026",
            "ALL TESTS PASSED\u2026  ",
            "All tests passed\u2014",
            "All tests passed \u2013 ",
            "All tests passed\u2026\u201d",
            "\u201cAll tests passed.\u201d",
            "All tests passed. \u2026",
            "All tests passed\u3002",
        ):
            assert (
                claim_verification_subject_fingerprint(
                    session_id=session.id,
                    goal_id=goal.id,
                    project_id=project,
                    claim=variant,
                )
                == base
            )
        other = claim_verification_subject_fingerprint(
            session_id=session.id,
            goal_id=goal.id,
            project_id=project,
            claim="The deployment is complete.",
        )
        assert other != base
        other_session = claim_verification_subject_fingerprint(
            session_id="codex:other",
            goal_id=goal.id,
            project_id=project,
            claim="All tests passed.",
        )
        assert other_session != base
        # Principal rotation must not fork the subject trail.
        request_a = claim_verification_request_fingerprint(
            principal_id="mcp-verify-principal",
            tool=MCP_VERIFY_CLAIM_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=project,
            claim="All tests passed.",
        )
        request_b = claim_verification_request_fingerprint(
            principal_id="mcp-rotated-principal",
            tool=MCP_VERIFY_CLAIM_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=project,
            claim="All tests passed.",
        )
        assert request_a != request_b
        assert base == claim_verification_subject_fingerprint(
            session_id=session.id,
            goal_id=goal.id,
            project_id=project,
            claim="All tests passed.",
        )
        # The request fingerprint stays exact: cosmetic rephrasing that shares
        # a subject trail must still mint a distinct idempotent request.
        exact_a = claim_verification_request_fingerprint(
            principal_id="mcp-verify-principal",
            tool=MCP_VERIFY_CLAIM_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=project,
            claim="All tests passed.",
        )
        exact_b = claim_verification_request_fingerprint(
            principal_id="mcp-verify-principal",
            tool=MCP_VERIFY_CLAIM_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=project,
            claim="All tests passed\u2026",
        )
        assert exact_a != exact_b
        assert exact_a == request_a
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_commit_refuses_not_live_control_session(tmp_path):
    for seal_key in ("not_live_control", "observe_only", "replay"):
        store, session, goal, principal = await _bound_store(tmp_path / seal_key)
        try:
            principal_id = principal["principal_id"]
            sealed = session.model_copy(deep=True)
            sealed.metadata = {**(sealed.metadata or {}), seal_key: True}
            await store.upsert_session(sealed)
            artifacts = _verification_artifacts(
                f"sealed-{seal_key}",
                sealed,
                goal,
                principal_id=principal_id,
                outcome="uncertain",
            )
            with pytest.raises(ValueError, match="no live worker"):
                await _commit(store, principal_id, f"verify-sealed-{seal_key}", (), artifacts)
        finally:
            await store.close()


@pytest.mark.asyncio
async def test_pipeline_verify_refuses_not_live_control_session(tmp_path):
    from pex_bridge.adapters import AdapterRegistry
    from pex_bridge.bus import EventBus
    from pex_bridge.config import Settings
    from pex_bridge.mcp_auth import MCPPrincipal
    from pex_bridge.pipeline import Pipeline
    from pex_protocol.context import ClaimVerificationRequest

    store, session, goal, record = await _bound_store(tmp_path)
    try:
        pipeline = Pipeline(
            store,
            AdapterRegistry(),
            EventBus(),
            Settings.for_test(home=tmp_path, require_auth=False, autonomy="observe"),
            model=None,
        )
        now = utcnow()
        principal = MCPPrincipal.from_store_record(record, now=now)
        sealed = session.model_copy(deep=True)
        sealed.metadata = {**(sealed.metadata or {}), "not_live_control": True}
        await store.upsert_session(sealed)
        with pytest.raises(ValueError, match="no live worker"):
            await pipeline.verify_reported_claim(
                sealed,
                principal=principal,
                request=ClaimVerificationRequest(
                    idempotency_key="verify-pipeline-sealed-0001",
                    claim="All tests passed.",
                ),
            )
    finally:
        await store.close()
