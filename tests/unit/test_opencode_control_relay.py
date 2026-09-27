import asyncio
import time

import pytest
from pex_bridge.adapters.strict_json import strict_json_dumps

from benchmarks.opencode_control_relay import REVIEW_SCHEMA, OpenCodeControlRelay


def request(identity="review-1", vendor="vendor", messages=None):
    return strict_json_dumps({
        "schema": REVIEW_SCHEMA, "request_id": identity, "vendor_session_id": vendor,
        "agent_messages": ["The public artifact is incomplete."] if messages is None else messages,
    }).encode()


def relay(review=None, **options):
    async def backend(body):
        return {"model": "pinned", "choices": []}

    return OpenCodeControlRelay(
        review=review, model="pinned", max_calls=5,
        deadline=time.perf_counter() + 10, backend=backend, **options,
    )


async def test_baseline_refuses_review_without_reserving_a_model_call():
    controller = relay()
    result = await controller.dispatch(request())
    assert result["error"] == "reviews_disabled"
    assert controller.audit == controller.review_audit == []


async def test_review_returns_only_bounded_public_action_and_exact_hashes():
    calls = []

    async def review(vendor, messages):
        calls.append((vendor, messages))
        return {"type": "SEND_NUDGE", "payload": {"text": "Verify and fix the public test",
                                                  "private": "must not leave controller"},
                "private": "must not leave controller"}

    controller = relay(review)
    result = await controller.dispatch(request())
    assert result["action"] == {"type": "SEND_NUDGE",
                                "payload": {"text": "Verify and fix the public test"}}
    assert calls == [("vendor", ("The public artifact is incomplete.",))]
    assert controller.review_audit[0]["status"] == "completed"
    assert len(controller.review_audit[0]["response_sha256"]) == 64
    assert controller.audit == []


async def test_duplicate_cross_session_and_excess_reviews_cannot_dispatch():
    calls = []

    async def review(*args):
        calls.append(args)
        return {"type": "NOOP"}

    controller = relay(review, max_reviews=1)
    assert (await controller.dispatch(request()))["ok"]
    assert (await controller.dispatch(request()))["error"] == "duplicate_request"
    assert (await controller.dispatch(request("review-2", "other")))["error"] == "session_mismatch"
    assert (await controller.dispatch(request("review-2")))["error"] == "review_budget_exhausted"
    assert len(calls) == 1


async def test_concurrent_review_cannot_overlap_or_rebind_vendor():
    entered, release = asyncio.Event(), asyncio.Event()

    async def review(*args):
        entered.set()
        await release.wait()
        return {"type": "NOOP"}

    controller = relay(review)
    first = asyncio.create_task(controller.dispatch(request()))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        result = await controller.dispatch(request("review-2"))
        assert result["error"] == "review_in_progress"
    finally:
        release.set()
        await asyncio.wait_for(first, 1)
    assert len(controller.review_audit) == 1


async def test_cancelled_review_remains_consumed_and_uncertain():
    entered = asyncio.Event()

    async def review(*args):
        entered.set()
        await asyncio.Event().wait()

    controller = relay(review, max_reviews=1)
    task = asyncio.create_task(controller.dispatch(request()))
    try:
        await asyncio.wait_for(entered.wait(), 1)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert controller.review_audit[0]["status"] == "cancelled_uncertain"
    assert (await controller.dispatch(request("review-2")))["error"] == "review_budget_exhausted"


@pytest.mark.parametrize("action", [{"type": "MOVE_SESSION"}, {}, None,
                                  {"type": "SEND_NUDGE", "payload": {"text": " "}},
                                  {"type": "SEND_NUDGE", "payload": {"text": "a" * 20_001}}])
async def test_failed_review_never_returns_instruction_and_is_not_retried(action):
    async def review(*args):
        return action

    controller = relay(review, max_reviews=1)
    result = await controller.dispatch(request())
    assert result["error"] == "review_failed_uncertain"
    assert "action" not in result
    assert controller.review_audit[0]["status"] == "failed_uncertain"
    assert (await controller.dispatch(request()))["error"] == "duplicate_request"


async def test_review_after_deadline_never_returns_action(monkeypatch):
    clock = [10]
    monkeypatch.setattr("benchmarks.opencode_control_relay.time.perf_counter", lambda: clock[0])

    async def review(*args):
        clock[0] = 21
        return {"type": "NOOP"}

    controller = relay(review)
    assert (await controller.dispatch(request()))["error"] == "review_failed_uncertain"


@pytest.mark.parametrize("vendor,messages", [("", []), ("x\x00", []), ("x", [None]),
                                            ("x", ["a" * 20_001]), ("x", ["a"] * 101)])
async def test_unbounded_or_malformed_observations_are_refused(vendor, messages):
    async def forbidden(*args):
        pytest.fail("invalid review must not dispatch")

    controller = relay(forbidden)
    assert (await controller.dispatch(request(vendor=vendor, messages=messages)))["error"] == (
        "invalid_request"
    )
    assert controller.review_audit == []


async def test_normal_model_requests_still_use_pinned_model_relay():
    controller = relay()
    raw = strict_json_dumps({"schema": "pex.model-relay.v1", "request_id": "model-1",
                             "body": {"model": "pinned", "messages": [
                                 {"role": "user", "content": "Public task"}], "max_tokens": 10}})
    assert (await controller.dispatch(raw.encode()))["ok"]
    assert len(controller.audit) == 1
    assert controller.review_audit == []
