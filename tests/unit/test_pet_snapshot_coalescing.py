from __future__ import annotations

import asyncio

import pex_bridge.pipeline as pipeline_module
import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store


def _pipeline(tmp_path) -> Pipeline:
    return Pipeline(
        Store(tmp_path / "pex.sqlite"),
        AdapterRegistry(),
        EventBus(),
        Settings.for_test(require_auth=False, home=tmp_path, autonomy="observe"),
    )


@pytest.mark.asyncio
async def test_concurrent_pet_snapshots_share_one_build_and_return_independent_copies(
    tmp_path,
    monkeypatch,
):
    pipeline = _pipeline(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def build_snapshot() -> dict:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"sessions": [], "nested": {"values": []}}

    monkeypatch.setattr(pipeline, "_build_pet_snapshot", build_snapshot)
    tasks = [asyncio.create_task(pipeline.pet_snapshot()) for _ in range(24)]
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.sleep(0)
    assert calls == 1

    release.set()
    snapshots = await asyncio.gather(*tasks)
    assert calls == 1
    snapshots[0]["nested"]["values"].append("mutated")
    assert snapshots[1]["nested"]["values"] == []
    assert pipeline._pet_snapshot_task is None


@pytest.mark.asyncio
async def test_cancelled_pet_snapshot_waiter_does_not_cancel_shared_build(
    tmp_path,
    monkeypatch,
):
    pipeline = _pipeline(tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def build_snapshot() -> dict:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"sessions": [], "headline": "fresh"}

    monkeypatch.setattr(pipeline, "_build_pet_snapshot", build_snapshot)
    cancelled = asyncio.create_task(pipeline.pet_snapshot())
    await asyncio.wait_for(started.wait(), timeout=1)
    surviving = asyncio.create_task(pipeline.pet_snapshot())
    cancelled.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled
    assert calls == 1

    release.set()
    assert await surviving == {"sessions": [], "headline": "fresh"}
    assert calls == 1
    assert pipeline._pet_snapshot_task is None


@pytest.mark.asyncio
async def test_close_presentations_cancels_unowned_shared_snapshot_build(
    tmp_path,
    monkeypatch,
):
    pipeline = _pipeline(tmp_path)
    started = asyncio.Event()
    never = asyncio.Event()

    async def build_snapshot() -> dict:
        started.set()
        await never.wait()
        return {"sessions": []}

    monkeypatch.setattr(pipeline, "_build_pet_snapshot", build_snapshot)
    waiter = asyncio.create_task(pipeline.pet_snapshot())
    await asyncio.wait_for(started.wait(), timeout=1)

    await asyncio.wait_for(pipeline.close_presentations(), timeout=1)
    with pytest.raises(asyncio.CancelledError):
        await waiter
    assert pipeline._pet_snapshot_task is None
    assert not pipeline._presentation_tasks


@pytest.mark.asyncio
async def test_event_pet_publication_coalesces_burst_and_one_midflight_refresh(
    tmp_path,
    monkeypatch,
):
    pipeline = _pipeline(tmp_path)
    monkeypatch.setattr(pipeline_module, "PET_PUBLICATION_COALESCE_SECONDS", 0.0)
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    builds = 0
    published: list[int] = []

    async def build_snapshot() -> dict:
        nonlocal builds
        builds += 1
        if builds == 1:
            first_started.set()
            await release_first.wait()
        return {"build": builds, "sessions": []}

    def record_publication(topic: str, payload: dict) -> None:
        assert topic == "pet"
        published.append(payload["build"])

    monkeypatch.setattr(pipeline, "_build_pet_snapshot", build_snapshot)
    monkeypatch.setattr(pipeline, "_schedule_committed_publication", record_publication)

    for _ in range(24):
        await pipeline._publish_event_plan_commit(
            intervention_updates=[],
            intervention=None,
        )
    await asyncio.wait_for(first_started.wait(), timeout=1)
    for _ in range(12):
        await pipeline._publish_event_plan_commit(
            intervention_updates=[],
            intervention=None,
        )
    release_first.set()

    while pipeline._presentation_tasks:
        await asyncio.gather(*tuple(pipeline._presentation_tasks))

    assert builds == 2
    assert published == [1, 2]
    assert pipeline._event_pet_publication_task is None
