from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.agentcore import transport_invocation_id
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import IndependentVerifierReceipt, SupervisorResult
from pex_supervisor.evidence_observations import EvidenceObservationCollector
from pex_supervisor.evidence_tools import build_evidence_tools


class _FailedRemoteSupervisor:
    async def decide(self, request, *, local_model):
        del local_model
        return SupervisorResult(
            action=ProposedAction(
                type=InterventionType.NOOP,
                session_id=request.session.id,
                goal_id=request.goal.id if request.goal else None,
                rationale="Remote semantic supervision failed closed.",
                evidence=["agentcore_unavailable"],
            ),
            diagnosis="agentcore_unavailable:transport failure",
            inference_status="failed",
            execution_mode="agentcore",
            transport="bedrock-agentcore",
            transport_invocation_id=transport_invocation_id(request),
            transport_status="failed",
        )


async def _bound_session(
    store: Store,
    tmp_path,
    *,
    vendor_session_id: str,
    now: datetime,
) -> HarnessSession:
    project_id = str(tmp_path.resolve())
    goal = Goal(
        id=f"goal-{vendor_session_id}",
        project_id=project_id,
        title="Preserve failed-closed supervision",
        objective="Keep a durable intervention receipt when semantic supervision fails.",
        created_at=now,
        updated_at=now,
    )
    session = HarnessSession(
        id=f"codex:{vendor_session_id}",
        harness_type=HarnessType.CODEX,
        vendor_session_id=vendor_session_id,
        project_id=project_id,
        goal_id=goal.id,
        cwd=project_id,
        status=SessionStatus.WORKING,
        last_activity=now,
    )
    await store.upsert_goal(goal)
    await store.upsert_session(session)
    return session


@pytest.mark.asyncio
async def test_agentcore_failure_noop_keeps_durable_transport_receipt(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    session = await _bound_session(
        store,
        tmp_path,
        vendor_session_id="agentcore-failure",
        now=now,
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    pipeline.supervisor = _FailedRemoteSupervisor()
    event = HarnessEvent(
        event_id="agentcore-failure-event",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="I think the task is complete.",
    )
    try:
        intervention = await pipeline.ingest_event(event, session)
        rows = await store.list_interventions(session.id)

        assert intervention is not None
        assert intervention.result == "noop"
        assert intervention.metadata["execution_mode"] == "agentcore"
        assert intervention.metadata["transport"] == "bedrock-agentcore"
        assert intervention.metadata["transport_status"] == "failed"
        assert intervention.metadata["transport_invocation_id"]
        assert len(rows) == 1
        assert rows[0].id == intervention.id
        audit = json.loads(store.audit_path.read_text(encoding="utf-8").splitlines()[0])
        assert audit["execution_mode"] == "agentcore"
        assert audit["transport"] == "bedrock-agentcore"
        assert audit["transport_status"] == "failed"
        assert audit["transport_invocation_id"]
    finally:
        await store.close()


class _CrashingSupervisor:
    async def decide(self, request, *, local_model):
        del request, local_model
        raise RuntimeError("supervisor exploded")


@pytest.mark.asyncio
@pytest.mark.parametrize("inference_status", ["completed", "failed", "timeout"])
@pytest.mark.parametrize("crash_after_receipt", [False, True])
async def test_exact_main_and_verifier_observations_survive_noop_and_replay(
    tmp_path, inference_status, crash_after_receipt,
):
    """Real file tools + Store, fake inference; this is not live model evidence."""
    observed = {}
    artifact = tmp_path / "report.txt"
    artifact.write_text("first observed file state", encoding="utf-8")

    class ObservingSupervisor(_FailedRemoteSupervisor):
        calls = 0

        async def decide(self, request, *, local_model):
            self.calls += 1
            main = EvidenceObservationCollector(request, stage="main", invocation_id="pexinv_main")
            main_file = next(
                item for item in build_evidence_tools(request, [], collector=main)
                if item.tool_name == "inspect_file"
            )
            first_output = main_file("report.txt")
            artifact.write_text("second observed file state", encoding="utf-8")
            verifier = EvidenceObservationCollector(
                request, stage="verifier", invocation_id="pexver_independent",
            )
            verifier_file = next(
                item for item in build_evidence_tools(request, [], collector=verifier)
                if item.tool_name == "inspect_file"
            )
            second_output = verifier_file("report.txt")
            observed.update(main=main, verifier=verifier, first=first_output, second=second_output)
            result = await super().decide(request, local_model=local_model)
            result.used_llm = True  # Simulated model telemetry, not a provider call.
            result.inference_status = inference_status
            result.local_invocation_id = main.invocation_id
            result.evidence_observations = list(main.observations)
            result.evidence_refs = [main.observations[0].observation_id]
            result.independent_verifier = IndependentVerifierReceipt(
                approved=False, status="rejected", invocation_id=verifier.invocation_id,
                evidence_observations=list(verifier.observations),
                evidence_refs=[verifier.observations[0].observation_id],
                model_call_count=1,
            )
            if inference_status == "timeout":
                result.action = ProposedAction(
                    type=InterventionType.SEND_NUDGE,
                    session_id=request.session.id,
                    goal_id=request.goal.id,
                    rationale="An ambiguous proposal must not be executed.",
                    payload={"message": "Do not send this timed-out proposal."},
                )
            return result

    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    pipeline = None
    try:
        now = datetime.now(UTC)
        session = await _bound_session(store, tmp_path, vendor_session_id="observations", now=now)
        pipeline = Pipeline(
            store, AdapterRegistry(), EventBus(),
            Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
        )
        supervisor = ObservingSupervisor()
        pipeline.supervisor = supervisor
        event = HarnessEvent(
            event_id="observations-event", ts=now, harness_type=HarnessType.CODEX,
            session_id=session.id, project_id=session.project_id, goal_id=session.goal_id,
            event_type=EventType.STOP, message_delta="Stopping for inspection.",
        )
        if crash_after_receipt:
            class SimulatedCrash(BaseException):
                pass

            async def crash_before_plan_commit(**kwargs):
                raise SimulatedCrash("receipt saved before the plan commit")

            store.commit_event_plan = crash_before_plan_commit
            with pytest.raises(SimulatedCrash):
                await pipeline.ingest_event(event, session)
            original_planner = await store.get_event_effect(event.event_id, "planner")
            await store.close()
            artifact.write_text("changed after crash", encoding="utf-8")
            store = Store(tmp_path / "pex.sqlite", process_boot_id="receipt-recovery-boot")
            await store.connect()
            pipeline = Pipeline(
                store, AdapterRegistry(), EventBus(),
                Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
            )
            pipeline.supervisor = supervisor
            assert await pipeline.recover_unfinished_events() == [event.event_id]
            assert (await store.get_event_effect(event.event_id, "planner"))["result"] == (
                original_planner["result"]
            )
        intervention = await pipeline.ingest_event(event, session)
        assert intervention is not None
        assert intervention.result == "noop"
        first = observed["main"].observations[0]
        second = observed["verifier"].observations[0]
        assert first.output == observed["first"]
        assert second.output == observed["second"]
        assert "first observed file state" in first.output
        assert "second observed file state" in second.output
        assert first.output_sha256 != second.output_sha256
        assert first.request_digest == second.request_digest
        assert first.invocation_id != second.invocation_id

        stored = (await store.list_interventions(session.id))[0]
        expected_main = [first.model_dump(mode="json")]
        assert stored.metadata["evidence_observations"] == expected_main
        assert stored.metadata["independent_verifier"]["evidence_observations"] == [
            second.model_dump(mode="json"),
        ]
        audit = json.loads(store.audit_path.read_text(encoding="utf-8").splitlines()[0])
        assert audit["evidence_observations"] == expected_main
        assert audit["independent_verifier"]["evidence_observations"][0]["output"] == second.output
        planner = await store.get_event_effect(event.event_id, "planner")
        assert planner["result"]["supervisor_result"]["evidence_observations"] == expected_main
        if inference_status == "timeout":
            assert planner["state"] == "delivery_uncertain"
            assert stored.metadata["inference_status"] == "timeout"
            assert planner["result"]["supervisor_result"]["action"]["type"] == "SEND_NUDGE"
            assert stored.proposed_action.type == InterventionType.NOOP
        artifact.write_text("later file change must not rewrite receipts", encoding="utf-8")
        assert await pipeline.ingest_event(event, session) == intervention
        assert supervisor.calls == 1
        replayed = await store.get_event_effect(event.event_id, "planner")
        assert replayed["result"] == planner["result"]
    finally:
        if pipeline is not None:
            while pipeline._presentation_tasks:
                import asyncio

                await asyncio.gather(*tuple(pipeline._presentation_tasks), return_exceptions=True)
        await store.close()


@pytest.mark.asyncio
async def test_independent_verifier_receipt_survives_pipeline_store_and_audit(tmp_path):
    receipt = IndependentVerifierReceipt(
        approved=False,
        status="rejected",
        rationale="The proposed correction lacked supporting evidence.",
        evidence=["observed test result was inconclusive"],
        evidence_tools=["get_recent_events"],
        model_call_count=2,
        input_tokens=17,
        output_tokens=9,
        latency_ms=12,
    )

    class ReviewedSupervisor(_FailedRemoteSupervisor):
        async def decide(self, request, *, local_model):
            result = await super().decide(request, local_model=local_model)
            result.used_llm = True
            result.inference_status = "completed"
            result.transport_status = "completed"
            result.model_call_count = 3
            result.independent_verifier = receipt
            result.diagnosis = "strands_structured_decision:independent_verifier_rejected"
            return result

    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        now = datetime.now(UTC)
        session = await _bound_session(store, tmp_path, vendor_session_id="reviewed", now=now)
        pipeline = Pipeline(
            store, AdapterRegistry(), EventBus(),
            Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
        )
        pipeline.supervisor = ReviewedSupervisor()
        event = HarnessEvent(
            event_id="reviewed-event", ts=now, harness_type=HarnessType.CODEX,
            session_id=session.id, project_id=session.project_id, goal_id=session.goal_id,
            event_type=EventType.STOP, message_delta="Stopping for review.",
        )
        intervention = await pipeline.ingest_event(event, session)
        expected = receipt.model_dump(mode="json")
        assert intervention is not None
        assert intervention.result == "noop"
        assert intervention.metadata["independent_verifier"] == expected
        rows = await store.list_interventions(session.id)
        assert len(rows) == 1
        assert rows[0].metadata["independent_verifier"] == expected
        audit = json.loads(store.audit_path.read_text(encoding="utf-8").splitlines()[0])
        assert audit["independent_verifier"] == expected
        assert audit["model_call_count"] == 3
        assert audit["independent_verifier"]["model_call_count"] == 2
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_unexpected_supervisor_failure_is_failed_closed_and_persisted(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    session = await _bound_session(
        store,
        tmp_path,
        vendor_session_id="supervisor-crash",
        now=now,
    )
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    pipeline.supervisor = _CrashingSupervisor()
    event = HarnessEvent(
        event_id="supervisor-crash-event",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=session.id,
        project_id=session.project_id,
        goal_id=session.goal_id,
        event_type=EventType.AGENT_RESPONSE,
        message_delta="Still working.",
    )
    try:
        intervention = await pipeline.ingest_event(event, session)
        rows = await store.list_interventions(session.id)

        assert intervention is not None
        assert intervention.proposed_action.type == InterventionType.NOOP
        assert intervention.result == "noop"
        assert intervention.metadata["inference_status"] == "failed"
        assert intervention.metadata["execution_mode"] == "deterministic_reconciliation"
        planner_effect = await store.get_event_effect(event.event_id, "planner")
        assert planner_effect is not None
        assert planner_effect["state"] == "delivery_uncertain"
        assert planner_effect["result"] == {
            "status": "delivery_uncertain",
            "code": "planner_failed_after_dispatch_marker",
        }
        assert len(rows) == 1
        assert "supervisor exploded" not in intervention.model_dump_json()
        assert "supervisor exploded" not in store.audit_path.read_text(encoding="utf-8")
    finally:
        await store.close()
