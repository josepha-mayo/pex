"""Bounded worker-side review IPC; no credentials, retries, or host configuration."""

import math
import socket
import struct
import uuid
from time import monotonic

from benchmarks.opencode_session import REPAIR_ACTIONS
from benchmarks.worker_model_proxy import MAX_REQUEST_BYTES, _decode, _encode

REVIEW_SCHEMA = "pex.opencode-review.v1"


def review_request(
    socket_path: str, *, vendor_session_id: str, agent_messages: tuple[str, ...], deadline: float,
) -> dict:
    """Obtain one matching public action within the original task deadline.

    A failed or lost response is uncertain and must abort the caller's run.
    This function never retries a request that may already have been admitted.
    """
    if type(deadline) not in (float, int) or not math.isfinite(deadline):
        raise ValueError("review deadline must be finite")
    if (not isinstance(vendor_session_id, str) or not 1 <= len(vendor_session_id) <= 256
            or "\x00" in vendor_session_id or not isinstance(agent_messages, (tuple, list))
            or len(agent_messages) > 100
            or any(not isinstance(text, str) or len(text) > 20_000 or "\x00" in text
                   for text in agent_messages)):
        raise ValueError("review observations must be bounded")

    def remaining():
        budget = deadline - monotonic()
        if budget <= 0:
            raise TimeoutError("review exhausted the shared task deadline")
        return budget

    def receive(peer, size):
        result = bytearray()
        while len(result) < size:
            peer.settimeout(remaining())
            chunk = peer.recv(size - len(result))
            if not chunk:
                raise ValueError("incomplete review response")
            result.extend(chunk)
        remaining()
        return bytes(result)

    remaining()
    envelope = {
        "schema": REVIEW_SCHEMA, "request_id": uuid.uuid4().hex,
        "vendor_session_id": vendor_session_id, "agent_messages": list(agent_messages),
    }
    encoded = _encode(envelope)
    if len(encoded) > MAX_REQUEST_BYTES:
        raise ValueError("review request exceeds frame bound")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(remaining())
        peer.connect(socket_path)
        peer.settimeout(remaining())
        peer.sendall(struct.pack("!I", len(encoded)) + encoded)
        size = struct.unpack("!I", receive(peer, 4))[0]
        if not 0 < size <= MAX_REQUEST_BYTES:
            raise ValueError("review response exceeds frame bound")
        response = _decode(receive(peer, size))
    remaining()
    if (not isinstance(response, dict)
            or set(response) != {"schema", "request_id", "ok", "action"}
            or response["schema"] != REVIEW_SCHEMA
            or response["request_id"] != envelope["request_id"] or response["ok"] is not True):
        raise ValueError("review response does not match a successful request")
    action = response["action"]
    if (not isinstance(action, dict) or not isinstance(action.get("type"), str)
            or action["type"] not in REPAIR_ACTIONS | {"NOOP"}):
        raise ValueError("review response has an unsupported action")
    if action["type"] == "NOOP":
        if set(action) != {"type"}:
            raise ValueError("review NOOP contains unexpected fields")
    else:
        payload = action.get("payload")
        text = payload.get("text") if isinstance(payload, dict) else None
        if (set(action) != {"type", "payload"} or not isinstance(payload, dict)
                or set(payload) != {"text"} or not isinstance(text, str) or not text.strip()
                or len(text) > 20_000 or "\x00" in text):
            raise ValueError("review response has an unbounded instruction")
    remaining()
    return action
