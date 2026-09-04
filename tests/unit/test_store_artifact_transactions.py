from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest
from pex_bridge.store import Store
from pex_protocol.context import ContextItem
from pex_protocol.enums import ContextKind, DecisionSource, DecisionStatus, Sensitivity, SourceKind
from pex_protocol.goal import Decision, Goal


def _pair() -> tuple[Decision, ContextItem]:
    now = datetime.now(UTC)
    decision = Decision(
        id="decision-override",
        goal_id="goal-artifact-transaction",
        statement="Use the operator's explicit replacement constraint.",
        rationale="The operator explicitly replaced the prior instruction.",
        source=DecisionSource.HUMAN,
        status=DecisionStatus.ACTIVE,
        created_at=now,
    )
    context = ContextItem(
        id="context-override",
        project_id="artifact-transaction-project",
        goal_id=decision.goal_id,
        kind=ContextKind.DECISION,
        content=decision.statement,
        source_refs=["event-override"],
        provenance=SourceKind.HUMAN,
        confidence=0.9,
        relevance_tags=["override", "decision"],
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
        metadata={"decision_id": decision.id},
    )
    return decision, context


async def _seed_goal(store: Store) -> None:
    now = datetime.now(UTC)
    await store.upsert_goal(
        Goal(
            id="goal-artifact-transaction",
            project_id="artifact-transaction-project",
            title="Atomic artifacts",
            objective="Never split a Decision from its Context projection.",
            created_at=now,
            updated_at=now,
        )
    )


@pytest.mark.asyncio
async def test_decision_context_pair_commits_and_exact_replay_is_idempotent(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_goal(store)
        decision, context = _pair()
        await store.add_decision_context_pair(decision, context)
        await store.add_decision_context_pair(decision, context)

        assert await store.list_decisions(decision.goal_id) == [decision]
        assert await store.get_context(context.id) == context
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_decision_context_pair_rolls_back_both_rows_on_projection_failure(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        await _seed_goal(store)
        decision, context = _pair()
        await store.db.execute(
            "CREATE TRIGGER fail_context_projection BEFORE INSERT ON context_items "
            "WHEN NEW.id = 'context-override' BEGIN "
            "SELECT RAISE(ABORT, 'forced context projection failure'); END"
        )
        await store.db.commit()

        with pytest.raises(sqlite3.IntegrityError, match="forced context projection failure"):
            await store.add_decision_context_pair(decision, context)

        decision_row = await store.db.execute(
            "SELECT 1 FROM decisions WHERE id = ?",
            (decision.id,),
        )
        context_row = await store.db.execute(
            "SELECT 1 FROM context_items WHERE id = ?",
            (context.id,),
        )
        assert await decision_row.fetchone() is None
        assert await context_row.fetchone() is None
    finally:
        await store.close()
