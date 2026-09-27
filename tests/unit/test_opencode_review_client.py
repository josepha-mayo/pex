import json
import struct

import pytest

from benchmarks import opencode_review_client as client
from benchmarks import worker_model_proxy


@pytest.fixture
def peer(monkeypatch):
    clock = [10.0]

    class Peer:
        connected = False
        closed = False
        calls = 0
        tick = 0
        timeouts = []
        pending = b""
        transform = staticmethod(lambda envelope: {
            "schema": client.REVIEW_SCHEMA, "request_id": envelope["request_id"], "ok": True,
            "action": {"type": "SEND_NUDGE", "payload": {"text": "Exact public repair"}},
        })

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def settimeout(self, value):
            self.timeouts.append(value)

        def connect(self, path):
            assert path == "/model-relay.sock"
            self.connected = True

        def sendall(self, frame):
            size = struct.unpack("!I", frame[:4])[0]
            assert size == len(frame[4:])
            envelope = json.loads(frame[4:])
            assert envelope["vendor_session_id"] == "vendor"
            raw = self.transform(envelope)
            raw = raw if isinstance(raw, bytes) else json.dumps(raw).encode()
            self.pending = struct.pack("!I", len(raw)) + raw
            self.calls += 1

        def recv(self, size):
            clock[0] += self.tick
            result, self.pending = self.pending[:min(size, 5)], self.pending[min(size, 5):]
            return result

    instance = Peer()
    monkeypatch.setattr(client.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(client.socket, "socket", lambda *args: instance)
    monkeypatch.setattr(client, "monotonic", lambda: clock[0])
    return instance, clock


def execute(**kwargs):
    return client.review_request(
        "/model-relay.sock", vendor_session_id="vendor", agent_messages=("Public observation",),
        deadline=kwargs.get("deadline", 20),
    )


def test_matching_review_survives_fragmentation_and_closes_socket(peer):
    connection, _ = peer
    assert execute() == {"type": "SEND_NUDGE", "payload": {"text": "Exact public repair"}}
    assert connection.connected and connection.closed and connection.calls == 1


@pytest.mark.parametrize("mutation", [
    lambda result: result.update(request_id="other"),
    lambda result: result.update(schema="other"),
    lambda result: result.update(ok=False),
    lambda result: result.update(private="must not cross boundary"),
    lambda result: result.update(action={"type": "MOVE_SESSION"}),
    lambda result: result.update(action={"type": "NOOP", "payload": {}}),
    lambda result: result["action"]["payload"].update(private="extra"),
    lambda result: result["action"]["payload"].update(text=" "),
    lambda result: result["action"]["payload"].update(text="x" * 20_001),
])
def test_mismatched_or_unbounded_reply_never_yields_action_or_retries(peer, mutation):
    connection, _ = peer
    original = connection.transform

    def transform(envelope):
        result = original(envelope)
        mutation(result)
        return result

    connection.transform = transform
    with pytest.raises(ValueError):
        execute()
    assert connection.closed and connection.calls == 1


def test_slow_fragmented_response_cannot_reset_original_deadline(peer):
    connection, _ = peer
    connection.tick = 0.01
    with pytest.raises(TimeoutError, match="shared task deadline"):
        execute(deadline=10.03)
    assert connection.closed and connection.calls == 1
    assert connection.timeouts[-1] < connection.timeouts[0]


def test_expired_review_refuses_connection(peer):
    connection, _ = peer
    with pytest.raises(TimeoutError):
        execute(deadline=10)
    assert not connection.connected and connection.calls == 0


def test_excess_response_frame_is_refused_before_decoding(peer, monkeypatch):
    connection, _ = peer
    monkeypatch.setattr(client, "MAX_REQUEST_BYTES", 200)
    connection.transform = lambda envelope: b"x" * 201
    with pytest.raises(ValueError, match="response exceeds"):
        execute()
    assert connection.closed and connection.calls == 1


@pytest.mark.parametrize("raw", [b'{"timestamp":1e999}', b'{"value":NaN}',
                                  b'{"key":1,"key":2}', '{"type":"NOOP"}'.encode("utf-16")])
def test_worker_json_rejects_nonfinite_duplicate_or_non_utf8_response(raw):
    with pytest.raises(ValueError):
        worker_model_proxy._decode(raw)
