"""Controller-side OpenCode review IPC beside the pinned model relay.

Worker messages are untrusted observations. The supplied review callback must
verify the public workspace independently and run PEX in its separate boundary.
This transport does not establish task success or benchmark eligibility.
"""

import asyncio
import hashlib
import re
import time
from collections.abc import Awaitable, Callable

from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads

from benchmarks.async_budget import await_with_budget
from benchmarks.model_relay import MAX_REQUEST_BYTES, PinnedModelRelay
from benchmarks.opencode_session import REPAIR_ACTIONS

REVIEW_SCHEMA = "pex.opencode-review.v1"


class OpenCodeControlRelay(PinnedModelRelay):
    def __init__(
        self, *, review: Callable[[str, tuple[str, ...]], Awaitable[dict]] | None = None,
        max_reviews: int = 3, **model_options,
    ):
        super().__init__(**model_options)
        if type(max_reviews) is not int or not 1 <= max_reviews <= 11:
            raise ValueError("review budget must be between one and eleven")
        self.review = review
        self.max_reviews = max_reviews
        self.review_audit = []
        self._review_ids = set()
        self._vendor_session = None
        self._review_inflight = False

    async def dispatch(self, raw: bytes) -> dict:
        try:
            if not 0 < len(raw) <= MAX_REQUEST_BYTES:
                raise ValueError("request exceeds bound")
            envelope = strict_json_loads(raw)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return await super().dispatch(raw)
        if not isinstance(envelope, dict) or envelope.get("schema") != REVIEW_SCHEMA:
            return await super().dispatch(raw)
        invalid = {"schema": REVIEW_SCHEMA, "ok": False, "error": "invalid_request"}
        if set(envelope) != {"schema", "request_id", "vendor_session_id", "agent_messages"}:
            return invalid
        request_id = envelope["request_id"]
        vendor = envelope["vendor_session_id"]
        messages = envelope["agent_messages"]
        if (
            not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", request_id)
            or not isinstance(vendor, str) or not 1 <= len(vendor) <= 256 or "\x00" in vendor
            or not isinstance(messages, list) or len(messages) > 100
            or any(not isinstance(text, str) or len(text) > 20_000 or "\x00" in text
                   for text in messages)
        ):
            return invalid
        result = {"schema": REVIEW_SCHEMA, "request_id": request_id, "ok": False}
        if self.review is None:
            error = "reviews_disabled"
        elif request_id in self._review_ids:
            error = "duplicate_request"
        elif self._vendor_session is not None and vendor != self._vendor_session:
            error = "session_mismatch"
        elif self._review_inflight:
            error = "review_in_progress"
        elif len(self._review_ids) >= self.max_reviews:
            error = "review_budget_exhausted"
        elif time.perf_counter() >= self.deadline:
            error = "deadline_expired"
        else:
            error = None
        if error:
            return {**result, "error": error}
        # Reserve before yielding. Failed/cancelled review attempts consume budget;
        # the caller must abort rather than retry an uncertain decision.
        self._review_ids.add(request_id)
        self._vendor_session = vendor
        self._review_inflight = True
        receipt = {
            "request_id": request_id, "vendor_session_id": vendor,
            "request_sha256": hashlib.sha256(raw).hexdigest(), "status": "reserved",
        }
        self.review_audit.append(receipt)
        try:
            decision = await await_with_budget(
                lambda: self.review(vendor, tuple(messages)),
                budget=max(0, self.deadline - time.perf_counter()),
            )
            if time.perf_counter() >= self.deadline:
                raise TimeoutError("review returned after task deadline")
            if not isinstance(decision, dict) or decision.get("type") not in REPAIR_ACTIONS | {
                "NOOP",
            }:
                raise ValueError("review returned unsupported action")
            action = {"type": decision["type"]}
            if action["type"] != "NOOP":
                payload = decision.get("payload")
                text = payload.get("text") if isinstance(payload, dict) else None
                if (not isinstance(text, str) or not text.strip() or len(text) > 20_000
                        or "\x00" in text):
                    raise ValueError("review returned unbounded instruction")
                action["payload"] = {"text": text}
            response = {**result, "ok": True, "action": action}
            encoded = strict_json_dumps(response).encode("utf-8")
            receipt.update(status="completed", response_sha256=hashlib.sha256(encoded).hexdigest())
            return response
        except asyncio.CancelledError:
            receipt["status"] = "cancelled_uncertain"
            raise
        except Exception:
            receipt["status"] = "failed_uncertain"
            return {**result, "error": "review_failed_uncertain"}
        finally:
            self._review_inflight = False
