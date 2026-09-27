import asyncio
import json
import time

import pytest

from benchmarks.model_relay import SCHEMA
from benchmarks.responses_relay import PinnedResponsesRelay


def request(identity="first", **changes):
    return json.dumps({"schema": SCHEMA, "request_id": identity, "body": {
        "model": "pinned", "input": [{"role": "user", "content": "public task"}],
        "max_output_tokens": 1024, "store": False, **changes,
    }}).encode()


def completed(**changes):
    return {"model": "pinned", "status": "completed", "output": [], **changes}


async def test_self_contained_refusal_can_be_replayed():
    async def backend(body):
        return completed()

    relay = PinnedResponsesRelay(model="pinned", max_calls=1,
                                 deadline=time.perf_counter() + 5, backend=backend)
    result = await relay.dispatch(request(input=[{"role": "assistant", "content": [
        {"type": "refusal", "refusal": "Cannot comply"},
    ]}]))
    assert result["ok"] and relay.audit[0]["status"] == "completed"


async def test_responses_attempt_consumes_shared_budget_and_duplicate_identity():
    calls = []

    async def backend(body):
        calls.append(body)
        return completed()

    relay = PinnedResponsesRelay(model="pinned", max_calls=1,
                                 deadline=time.perf_counter() + 5, backend=backend)
    assert (await relay.dispatch(request()))["ok"]
    assert (await relay.dispatch(request()))["error"] == "duplicate_request"
    assert (await relay.dispatch(request("second")))["error"] == "call_budget_exhausted"
    assert len(calls) == 1 and relay.audit[0]["status"] == "completed"


@pytest.mark.parametrize("changes", [
    {"model": "other"}, {"stream": True}, {"store": True}, {"store": None},
    {"max_output_tokens": True}, {"max_output_tokens": 16385},
    {"previous_response_id": "other-arm"}, {"input": []},
    {"input": [{"type": "item_reference", "id": "private"}]},
    {"tools": [{"type": "web_search"}]}, {"tools": [{"type": "computer_use_preview"}]},
    {"client_metadata": {"key": 1}}, {"client_metadata": {"key": "x" * 4097}},
    {"input": [{"role": "user", "content": [{"type": "input_file", "file_id": "private"}]}]},
    {"input": [{"role": "user", "content": [
        {"type": "input_file", "file_url": "https://external.example/data"},
    ]}]},
    {"input": [{"type": "function_call_output", "call_id": "call", "output": [
        {"type": "input_image", "image_url": "https://external.example/image"},
    ]}]},
])
async def test_unsupported_or_unbounded_responses_never_reach_backend(changes):
    async def forbidden(_):
        pytest.fail("invalid request reached backend")

    relay = PinnedResponsesRelay(model="pinned", max_calls=1,
                                 deadline=time.perf_counter() + 5, backend=forbidden)
    assert (await relay.dispatch(request(**changes)))["error"] == "invalid_request"
    assert not relay.audit


async def test_codex_client_metadata_is_preserved():
    seen = []

    async def backend(body):
        seen.append(body)
        return completed()

    relay = PinnedResponsesRelay(model="pinned", max_calls=1,
                                 deadline=time.perf_counter() + 5, backend=backend)
    metadata = {"session_id": "public-isolated-session"}
    assert (await relay.dispatch(request(client_metadata=metadata)))["ok"]
    assert seen[0]["client_metadata"] == metadata


@pytest.mark.parametrize("result", [completed(model="other"), completed(status="incomplete"),
                                   completed(output=None)])
async def test_uncertain_backend_result_consumes_slot_without_success(result):
    async def backend(_):
        return result

    relay = PinnedResponsesRelay(model="pinned", max_calls=1,
                                 deadline=time.perf_counter() + 5, backend=backend)
    assert (await relay.dispatch(request()))["error"] == "backend_failed_uncertain"
    assert relay.audit[0]["status"] == "failed_uncertain"
    assert (await relay.dispatch(request("second")))["error"] == "call_budget_exhausted"


async def test_cancellation_suppressing_backend_never_returns_late_success():
    async def backend(_):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return completed()

    relay = PinnedResponsesRelay(model="pinned", max_calls=1,
                                 deadline=time.perf_counter() + 0.01, backend=backend)
    assert (await relay.dispatch(request()))["error"] == "backend_failed_uncertain"
    assert relay.audit[0]["status"] == "failed_uncertain"
