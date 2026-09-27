import json
import time

from benchmarks.codex_control_relay import REVIEW_SCHEMA, CodexControlRelay
from benchmarks.model_relay import SCHEMA


async def test_responses_and_reviews_have_separate_budgets_and_bound_session():
    calls = []
    reviews = []

    async def backend(body):
        calls.append(body)
        return {"model": "pinned", "status": "completed", "output": []}

    async def review(vendor, messages):
        reviews.append((vendor, messages))
        return {"type": "SEND_NUDGE", "payload": {"text": "Verify public tests"}}

    relay = CodexControlRelay(model="pinned", max_calls=1, max_reviews=2,
                             deadline=time.perf_counter() + 5, backend=backend, review=review)

    def request(schema, identity, **body):
        return json.dumps({"schema": schema, "request_id": identity, **body}).encode()

    result = await relay.dispatch(request(SCHEMA, "model", body={
        "model": "pinned", "input": "Public task", "store": False, "max_output_tokens": 100,
    }))
    assert result["ok"] and len(calls) == 1
    result = await relay.dispatch(request(REVIEW_SCHEMA, "review", vendor_session_id="session",
                                          agent_messages=["Done"]))
    assert result["ok"] and result["schema"] == REVIEW_SCHEMA
    assert reviews == [("session", ("Done",))]
    assert (await relay.dispatch(request(REVIEW_SCHEMA, "review", vendor_session_id="session",
                                          agent_messages=[])))["error"] == "duplicate_request"
    assert (await relay.dispatch(request(REVIEW_SCHEMA, "other", vendor_session_id="other",
                                          agent_messages=[])))["error"] == "session_mismatch"
    assert (await relay.dispatch(request("pex.opencode-review.v1", "wrong",
                                          vendor_session_id="session",
                                          agent_messages=[])))["error"] == "invalid_request"
    assert len(relay.audit) == len(relay.review_audit) == 1


async def test_codex_control_keeps_completed_responses_guard():
    async def backend(_):
        return {"model": "other", "status": "completed", "output": []}

    relay = CodexControlRelay(model="pinned", max_calls=1,
                             deadline=time.perf_counter() + 5, backend=backend)
    result = await relay.dispatch(json.dumps({"schema": SCHEMA, "request_id": "model", "body": {
        "model": "pinned", "input": "Public task", "store": False, "max_output_tokens": 100,
    }}).encode())
    assert result["error"] == "backend_failed_uncertain"
    assert relay.audit[0]["status"] == "failed_uncertain"
