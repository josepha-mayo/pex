"""Responses HTTP framing preserves actual output through the bounded relay."""

import http.client
import json
import threading

import pytest

from benchmarks.worker_model_proxy import make_server, responses_sse


def completed():
    return {
        "id": "resp-test", "object": "response", "model": "pinned", "status": "completed",
        "output": [{"id": "msg-test", "type": "message", "role": "assistant",
                    "status": "completed", "content": [
                        {"type": "output_text", "text": "Verified text", "annotations": []}]}],
        "usage": {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
    }


@pytest.fixture
def proxy():
    calls = []

    def relay(path, body):
        calls.append(body)
        return completed()

    server = make_server("/model.sock", model="pinned", relay=relay, wire_api="responses")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def post(proxy, **updates):
    server, _ = proxy
    peer = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        peer.request("POST", "/v1/responses", json.dumps({
            "model": "pinned", "input": "Public input", **updates,
        }))
        response = peer.getresponse()
        return response.status, response.read()
    finally:
        peer.close()


def test_completed_response_and_explicit_controller_bounds(proxy):
    status, raw = post(proxy)
    assert status == 200 and json.loads(raw) == completed()
    assert proxy[1] == [{"model": "pinned", "input": "Public input", "stream": False,
                        "max_output_tokens": 4096, "store": False}]


def test_stream_preserves_text_usage_and_sequence(proxy):
    status, raw = post(proxy, stream=True, max_output_tokens=100)
    assert status == 200
    events = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith(b"data: ")]
    assert [event["sequence_number"] for event in events] == list(range(len(events)))
    assert events[-1] == {"type": "response.completed", "response": completed(),
                          "sequence_number": len(events) - 1}
    deltas = [event["delta"] for event in events
              if event["type"] == "response.output_text.delta"]
    assert deltas == ["Verified text"]
    assert proxy[1][0]["max_output_tokens"] == 100
    assert proxy[1][0]["stream"] is False


@pytest.mark.parametrize("updates", [{"store": True}, {"store": None}, {"stream": 1},
                                    {"model": "unpinned"}])
def test_invalid_transport_does_not_dispatch(proxy, updates):
    assert post(proxy, **updates)[0] == 502
    assert proxy[1] == []


def test_refusal_preserves_completed_response():
    result = completed()
    result["output"][0]["content"] = [{"type": "refusal", "refusal": "Cannot comply"}]
    raw = responses_sse(result)
    events = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith(b"data: ")]
    assert next(event for event in events if event["type"] == "response.refusal.delta")[
        "delta"
    ] == "Cannot comply"
    assert events[-1]["response"] == result
