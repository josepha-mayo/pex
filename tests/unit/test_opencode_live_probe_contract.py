"""Offline guards for the live-model probe; no provider or worker calls."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.contract.test_live_opencode_stop import _assert_completed_review, _close_probe


@pytest.mark.parametrize("status", [None, "failed", "timeout", "unavailable"])
def test_attempted_inference_is_not_a_completed_decision(status):
    with pytest.raises(AssertionError, match="completed model decision"):
        _assert_completed_review({"used_llm": True, "inference_status": status})


@pytest.mark.parametrize("used_llm", [False, None, "true", "false", 1])
def test_completed_review_requires_real_inference(used_llm):
    with pytest.raises(AssertionError, match="did not inspect"):
        _assert_completed_review({"used_llm": used_llm, "inference_status": "completed"})
    _assert_completed_review({"used_llm": True, "inference_status": "completed"})


@pytest.mark.asyncio
@pytest.mark.parametrize("presentation_fails", [False, True])
async def test_probe_cleanup_preserves_unrelated_tasks_and_closes_store(presentation_fails):
    pump = asyncio.create_task(asyncio.Event().wait())
    unrelated = asyncio.create_task(asyncio.Event().wait())
    pipeline = AsyncMock()
    store = AsyncMock()
    if presentation_fails:
        pipeline.close_presentations.side_effect = RuntimeError("presentation close failed")
    try:
        if presentation_fails:
            with pytest.raises(RuntimeError, match="presentation close failed"):
                await _close_probe(pump, pipeline, store)
        else:
            await _close_probe(pump, pipeline, store)
        assert pump.cancelled()
        assert not unrelated.done()
        pipeline.close_presentations.assert_awaited_once_with()
        store.close.assert_awaited_once_with()
    finally:
        unrelated.cancel()
        await asyncio.gather(unrelated, return_exceptions=True)
