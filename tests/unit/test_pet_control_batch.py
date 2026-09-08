from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pex_bridge.app import state
from pex_bridge.store import Store
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.session import HarnessSession


def _session(suffix: str) -> HarnessSession:
    return HarnessSession(
        id=f"codex:{suffix}",
        harness_type=HarnessType.CODEX,
        vendor_session_id=suffix,
        status=SessionStatus.IDLE,
        last_activity=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_session_control_batch_returns_exact_canonical_receipts(tmp_path) -> None:
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        first = _session("batch-a")
        second = _session("batch-b")
        await store.upsert_session(first)
        await store.upsert_session(second)

        controls = await store.get_session_control_states(
            [first.id, second.id, first.id],
        )

        assert set(controls) == {first.id, second.id}
        assert controls[first.id] == await store.get_session_control_state(first.id)
        assert controls[second.id] == await store.get_session_control_state(second.id)
        assert await store.get_session_control_states([]) == {}
        with pytest.raises(ValueError, match="too many sessions"):
            await store.get_session_control_states(
                [f"codex:bounded-{index}" for index in range(1_001)],
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_live_pet_batches_session_control_projection(monkeypatch) -> None:
    sessions = [_session("live-a"), _session("live-b"), _session("live-c")]
    batch_calls: list[list[str]] = []

    class _Pipeline:
        async def refresh_desktop_sessions(self) -> None:
            return None

        async def pet_snapshot(self) -> dict:
            return {"sessions": [item.model_dump(mode="json") for item in sessions]}

    class _Store:
        async def get_session_control_states(self, session_ids: list[str]) -> dict:
            batch_calls.append(session_ids)
            return {
                session_id: {"revision": index + 3, "control_revision": index + 7}
                for index, session_id in enumerate(session_ids)
            }

    monkeypatch.setattr(state, "pipeline", _Pipeline())
    monkeypatch.setattr(state, "store", _Store())
    monkeypatch.setattr(state, "decorate_pet", lambda snapshot: snapshot)

    snapshot = await state.live_pet()

    assert batch_calls == [[item.id for item in sessions]]
    assert [item["revision"] for item in snapshot["sessions"]] == [3, 4, 5]
    assert [item["control_revision"] for item in snapshot["sessions"]] == [7, 8, 9]
