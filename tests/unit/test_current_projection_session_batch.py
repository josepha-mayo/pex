from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import ProjectIdentityBlockedError, Store
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.project_identity import PathPlatform, ProjectLocator, ProjectOrigin
from pex_protocol.session import HarnessSession


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
