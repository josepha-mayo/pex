from __future__ import annotations

import http.client
import json
import threading

import pytest

from benchmarks.worker_model_proxy import make_server


def completion():
    return {
        "id": "response-test",
        "created": 1,
        "model": "pinned",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-test",
                            "type": "function",
                            "function": {"name": "read", "arguments": '{"path":"solver.py"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
    }


@pytest.fixture
def proxy():
    calls = []

    def relay(path, body):
        calls.append((path, body))
        return completion()

    server = make_server("/model-relay.sock", model="pinned", relay=relay)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def post(proxy, body, *, path="/v1/chat/completions", headers=None):
    server, _ = proxy
    client = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        client.request("POST", path, body=body, headers=headers or {})
        response = client.getresponse()
        return response.status, response.getheader("Content-Type"), response.read()
    finally:
        client.close()


def body(**updates):
    return json.dumps(
        {
            "model": "pinned",
            "messages": [{"role": "user", "content": "fix"}],
            "max_tokens": 100,
            **updates,
        }
    )


def test_buffered_sse_preserves_tool_call_finish_and_usage(proxy):
    status, kind, raw = post(proxy, body(stream=True, stream_options={"include_usage": True}))
    assert status == 200 and kind == "text/event-stream"
    frames = [
        json.loads(line[6:])
        for line in raw.splitlines()
        if line.startswith(b"data: ") and line != b"data: [DONE]"
    ]
    tool = frames[0]["choices"][0]["delta"]["tool_calls"][0]
    assert tool == {**completion()["choices"][0]["message"]["tool_calls"][0], "index": 0}
    assert frames[1]["choices"][0]["finish_reason"] == "tool_calls"
    assert frames[2]["usage"] == completion()["usage"]
    assert raw.endswith(b"data: [DONE]\n\n")
    assert proxy[1][0][0] == "/model-relay.sock"
    assert proxy[1][0][1]["stream"] is False
    assert "stream_options" not in proxy[1][0][1]


def test_nonstream_response_and_loopback_binding(proxy):
    assert proxy[0].server_address[0] == "127.0.0.1"
    status, kind, raw = post(proxy, body())
    assert status == 200 and kind == "application/json"
    assert json.loads(raw) == completion()


@pytest.mark.parametrize(
    "raw",
    [
        '{"model":"pinned","model":"other"}',
        body(model="other"),
        body(stream="true"),
        body(stream=False, stream_options={"include_usage": True}),
        body(stream=True, stream_options={"include_usage": False}),
        "[]",
        "NaN",
    ],
)
def test_rejected_requests_never_reach_relay(proxy, raw):
    assert post(proxy, raw)[0] == 502
    assert proxy[1] == []


@pytest.mark.parametrize(
    "path,headers",
    [
        ("/v1/responses", {}),
        ("/v1/chat/completions?endpoint=other", {}),
        ("/v1/chat/completions", {"Authorization": "Bearer real-provider-secret"}),
        ("/v1/chat/completions", {"Transfer-Encoding": "chunked"}),
    ],
)
def test_routes_credentials_and_chunked_input_rejected(proxy, path, headers):
    assert post(proxy, body(), path=path, headers=headers)[0] == 502
    assert proxy[1] == []
