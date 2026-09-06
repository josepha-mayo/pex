from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pex_bridge.pipeline as pipeline_module
import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from pex_protocol.context import ContextHandoffRequest, ContextItem
from pex_protocol.enums import ContextKind, Sensitivity, SourceKind
from pex_protocol.goal import Goal


@pytest.mark.asyncio
async def test_timed_out_handoff_is_durably_unresolved_and_never_redelivered(
    tmp_path,
    monkeypatch,
):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    adapters = AdapterRegistry()
    goal_id = "goal-handoff-timeout"
    source = adapters.synthetic.seed_session(
        vendor_id="timeout-source",
        project_id="demo",
        goal_id=goal_id,
    )
    target = adapters.synthetic.seed_session(
        vendor_id="timeout-target",
        project_id="demo",
        goal_id=goal_id,
    )
    now = datetime.now(UTC)
    goal = Goal(
        id=goal_id,
        project_id="demo",
        title="Preserve handoff delivery safety",
        objective="Share the verified parser artifact without duplicate delivery.",
        acceptance_criteria=["The target receives the verified parser artifact once."],
        created_at=now,
        updated_at=now,
    )
    pipeline = Pipeline(
        store,
        adapters,
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="manage"),
    )
    deliveries = []
    adapter_started = asyncio.Event()

    async def accepted_then_stalled(session, bundle):
        deliveries.append((session.id, bundle.model_dump(mode="json")))
        adapter_started.set()
        await asyncio.Event().wait()
        return True

    # Ten milliseconds is below a reliable Windows/full-suite scheduling
    # quantum: the outer timeout may fire before the adapter coroutine gets its
    # first instruction.  Explicitly prove that dispatch entered the adapter,
    # then exercise a still-bounded timeout without turning scheduler latency
    # into an assertion about delivery behavior.
    monkeypatch.setattr(pipeline_module, "HANDOFF_ADAPTER_TIMEOUT_SECONDS", 0.25)
    monkeypatch.setattr(adapters.synthetic, "inject_context", accepted_then_stalled)
    first_request: asyncio.Task | None = None

    try:
        await store.upsert_goal(goal)
        await store.upsert_session(source)
        await store.upsert_session(target)
        await store.add_context(
            ContextItem(
                id="ctx-timeout-artifact",
                project_id=goal.project_id,
                goal_id=goal.id,
                kind=ContextKind.RESULT,
                content="The verified parser artifact is artifacts/parser.json.",
                source_refs=["event-timeout-artifact"],
                provenance=SourceKind.HARNESS,
                confidence=0.95,
                relevance_tags=["verified", "parser", "artifact"],
                valid_from=now,
                sensitivity=Sensitivity.INTERNAL,
                metadata={
                    "source_session_id": source.id,
                    "verified": True,
                },
            )
        )

        request = ContextHandoffRequest(
            idempotency_key="handoff-timeout-0001",
            target_session_id=target.id,
            token_budget=2_000,
        )
        first_request = asyncio.create_task(
            pipeline.request_context_handoff(
                source,
                principal_id="test_handoff_timeout",
                request=request,
            )
        )
        await asyncio.wait_for(adapter_started.wait(), timeout=1.0)
        first = await first_request

        assert first["ok"] is False
        assert first["replayed"] is False
        assert len(deliveries) == 1
        receipt = await store.get_intervention(first["intervention"]["id"])
        assert receipt is not None
        assert receipt.result == "handoff_delivery_uncertain"
        assert receipt.metadata["handoff_delivery_status"] == "delivery_uncertain"

        # Replaying the same caller-owned request returns the immutable receipt
        # and never makes an ambiguous external delivery retryable.
        replay = await pipeline.request_context_handoff(
            source,
            principal_id="test_handoff_timeout",
            request=request,
        )
        assert replay["ok"] is False
        assert replay["status"] == "delivery_uncertain"
        assert replay["replayed"] is True
        assert replay["effect"] == first["effect"]

        assert len(deliveries) == 1
        rows = await store.list_interventions(target.id)
        assert len(rows) == 1
        assert rows[0].id == receipt.id
        assert rows[0].metadata["handoff_delivery_status"] == "delivery_uncertain"
    finally:
        if first_request is not None and not first_request.done():
            first_request.cancel()
            await asyncio.gather(first_request, return_exceptions=True)
        await store.close()
