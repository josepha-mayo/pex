from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import ProjectIdentityBlockedError, Store
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessEvent, HarnessSession


def _session(session_id: str, *, project_id: str | None = None) -> HarnessSession:
    now = datetime.now(UTC)
    return HarnessSession(
        id=session_id,
        harness_type=HarnessType.CODEX,
        vendor_session_id=session_id.removeprefix("codex:"),
        project_id=project_id,
        cwd=project_id,
        status=SessionStatus.IDLE,
        last_activity=now,
    )


@pytest.mark.asyncio
async def test_authority_session_batch_is_bounded_deduplicated_and_fail_closed(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    first = _session("codex:batch-first")
    second = _session("codex:batch-second")
    stale = _session("codex:batch-stale", project_id="batch-stale-project")
    await store.upsert_session(first)
    await store.upsert_session(second)
    await store.upsert_session(stale)
    await store.register_project_locator(
        legacy_project_id="batch-stale-project",
        locator=ProjectLocator.path(
            "/workspace/batch-stale-project",
            platform=PathPlatform.POSIX,
            origin=ProjectOrigin(namespace="machine", host="batch-test"),
        ),
    )

    try:
        selected = await store.get_sessions_for_authority(
            [second.id, first.id, second.id, "codex:batch-missing"]
        )
        assert list(selected) == [second.id, first.id]
        assert selected == {second.id: second, first.id: first}

        with pytest.raises(ProjectIdentityBlockedError):
            await store.get_sessions_for_authority([stale.id])
        assert await store.get_sessions_for_authority(
            [stale.id, first.id], omit_blocked=True
        ) == {first.id: first}

        with pytest.raises(ValueError, match="too many sessions"):
            await store.get_sessions_for_authority(
                [f"codex:batch-{index}" for index in range(1_001)]
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_current_projection_uses_one_order_preserving_authority_batch(tmp_path):
    first = _session("codex:projection-first")
    second = _session("codex:projection-second")

    class ProjectionStore:
        def __init__(self) -> None:
            self.calls: list[tuple[list[str], bool]] = []
            self.process_boot_id = "projection-batch-test"

        async def list_sessions(self, *, limit: int):
            assert limit == 3
            return [first, second]

        async def get_sessions_for_authority(
            self,
            session_ids: list[str],
            *,
            omit_blocked: bool = False,
        ):
            self.calls.append((session_ids, omit_blocked))
            # Deliberately return reverse insertion order: the projection must
            # retain list_sessions recency order, not mapping order.
            return {second.id: second, first.id: first}

    store = ProjectionStore()
    pipeline = Pipeline(
        store,  # type: ignore[arg-type]
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )

    projection = await pipeline.current_projection(
        session_limit=2,
        session_scan_limit=3,
        intervention_limit=0,
        event_limit=0,
    )

    assert store.calls == [([first.id, second.id], True)]
    assert [session.id for session in projection["sessions"]] == [first.id, second.id]
    assert projection["sessions_truncated"] is False


@pytest.mark.asyncio
async def test_pet_projection_enriches_only_collapsed_promptable_sessions(tmp_path, monkeypatch):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    now = datetime.now(UTC)
    goal = Goal(
        id="goal:pet-collapse",
        project_id=str(tmp_path),
        title="Show one current worker",
        objective="Collapse historical sessions before loading pet artifacts.",
        created_at=now,
        updated_at=now,
    )
    await store.upsert_goal(goal)
    older = _session("codex:pet-collapse-old", project_id=str(tmp_path)).model_copy(
        update={"goal_id": goal.id, "last_activity": now - timedelta(minutes=2)}
    )
    current = _session("codex:pet-collapse-current", project_id=str(tmp_path)).model_copy(
        update={"goal_id": goal.id, "last_activity": now}
    )
    await store.upsert_session(older)
    await store.upsert_session(current)

    intervention_calls: list[str] = []
    event_calls: list[str] = []
    original_interventions = store.list_interventions_for_authority
    original_events = store.recent_events_for_authority

    async def counted_interventions(session_id: str, **kwargs):
        intervention_calls.append(session_id)
        return await original_interventions(session_id, **kwargs)

    async def counted_events(session_id: str, **kwargs):
        event_calls.append(session_id)
        return await original_events(session_id, **kwargs)

    monkeypatch.setattr(store, "list_interventions_for_authority", counted_interventions)
    monkeypatch.setattr(store, "recent_events_for_authority", counted_events)
    pipeline = Pipeline(
        store,
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )

    try:
        snapshot = await pipeline.pet_snapshot()
    finally:
        await store.close()

    assert [session["id"] for session in snapshot["sessions"]] == [current.id]
    assert intervention_calls == [current.id]
    assert event_calls == [current.id]


@pytest.mark.asyncio
async def test_projection_drops_a_shared_goal_group_after_mid_read_authority_loss(tmp_path):
    now = datetime.now(UTC)
    goal = Goal(
        id="goal:projection-race",
        project_id=str(tmp_path),
        title="Keep canonical projection coherent",
        objective="Never retain sibling rows after their shared authority is lost.",
        created_at=now,
        updated_at=now,
    )
    first = _session("codex:projection-race-first", project_id=str(tmp_path)).model_copy(
        update={"goal_id": goal.id}
    )
    second = _session("codex:projection-race-second", project_id=str(tmp_path)).model_copy(
        update={"goal_id": goal.id}
    )
    first_event = HarnessEvent(
        event_id="event:projection-race-first",
        ts=now,
        harness_type=HarnessType.CODEX,
        session_id=first.id,
        goal_id=goal.id,
        event_type=EventType.FILE_EDIT,
        phase=EventPhase.AFTER,
    )

    class RacingStore:
        process_boot_id = "projection-race-test"

        async def list_sessions(self, *, limit: int):
            assert limit == 2
            return [first, second]

        async def get_sessions_for_authority(self, session_ids, *, omit_blocked=False):
            assert session_ids == [first.id, second.id]
            assert omit_blocked is True
            return {first.id: first, second.id: second}

        async def get_goal_for_authority(self, goal_id: str):
            assert goal_id == goal.id
            return goal

        async def recent_events_for_authority(self, session_id: str, **_kwargs):
            if session_id == second.id:
                raise ProjectIdentityBlockedError(
                    "project identity changed during projection",
                    code="project_identity_quarantined",
                )
            return [first_event]

    pipeline = Pipeline(
        RacingStore(),  # type: ignore[arg-type]
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )

    projection = await pipeline.current_projection(
        session_limit=2,
        session_scan_limit=2,
        intervention_limit=0,
        event_limit=2,
    )

    assert projection["sessions"] == []
    assert projection["goals"] == {}
    assert projection["events"] == []
