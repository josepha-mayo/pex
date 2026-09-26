"""Worker-side loopback HTTP adapter for the controller's bounded chat relay.

Run inside the worker's network namespace with only the relay socket mounted.
The upstream call is non-streaming; SSE is an explicitly buffered translation,
not a claim of provider streaming latency or benchmark eligibility.
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

MAX_REQUEST_BYTES = 262_144
MAX_RESPONSE_BYTES = 1_048_576


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("non-finite JSON value")


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_object, parse_constant=_constant)


def _encode(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _read(sock, count):
    data = bytearray()
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise ValueError("incomplete relay frame")
        data.extend(chunk)
    return bytes(data)


def relay_request(socket_path: str, body: dict, *, timeout: float = 45) -> dict:
    envelope = {"schema": "pex.model-relay.v1", "request_id": uuid.uuid4().hex, "body": body}
    encoded = _encode(envelope)
    if not 0 < len(encoded) <= MAX_REQUEST_BYTES:
        raise ValueError("request exceeds relay frame limit")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(timeout)
        peer.connect(socket_path)
        peer.sendall(struct.pack("!I", len(encoded)) + encoded)
        length = struct.unpack("!I", _read(peer, 4))[0]
        if not 0 < length <= MAX_RESPONSE_BYTES:
            raise ValueError("response exceeds relay frame limit")
        result = _decode(_read(peer, length))
    if (
        not isinstance(result, dict)
        or result.get("schema") != envelope["schema"]
        or result.get("request_id") != envelope["request_id"]
        or result.get("ok") is not True
        or not isinstance(result.get("body"), dict)
    ):
        raise ValueError("relay did not return a matching successful response")
    return result["body"]


def buffered_sse(result: dict) -> bytes:
    """Translate a complete chat response without inventing tokens or tool calls."""
    base = {
        "id": result["id"],
        "object": "chat.completion.chunk",
        "created": result["created"],
        "model": result["model"],
    }
    frames = []
    for choice in result["choices"]:
        message = choice["message"]
        delta = {
            key: value
            for key, value in message.items()
            if key in {"role", "content", "refusal", "tool_calls"} and value is not None
        }
        if "tool_calls" in delta:
            delta["tool_calls"] = [
                {**call, "index": index} for index, call in enumerate(delta["tool_calls"])
            ]
        frames.append(
            {**base, "choices": [{"index": choice["index"], "delta": delta, "finish_reason": None}]}
        )
        frames.append(
            {
                **base,
                "choices": [
                    {
                        "index": choice["index"],
                        "delta": {},
                        "finish_reason": choice["finish_reason"],
                    }
                ],
            }
        )
    if "usage" in result:
        frames.append({**base, "choices": [], "usage": result["usage"]})
    return b"".join(b"data: " + _encode(frame) + b"\n\n" for frame in frames) + b"data: [DONE]\n\n"


def make_server(socket_path: str, *, model: str, relay=relay_request) -> HTTPServer:
    if not model or len(model) > 256:
        raise ValueError("a bounded pinned model is required")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def do_POST(self):
            try:
                lengths = self.headers.get_all("Content-Length", [])
                if (
                    self.path != "/v1/chat/completions"
                    or len(lengths) != 1
                    or self.headers.get("Transfer-Encoding") is not None
                    or self.headers.get("Authorization") not in {None, "Bearer pex-relay-local"}
                ):
                    raise ValueError("unsupported HTTP request")
                size = int(lengths[0])
                if not 0 < size <= MAX_REQUEST_BYTES:
                    raise ValueError("invalid HTTP request length")
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError("incomplete HTTP request")
                body = _decode(raw)
                if not isinstance(body, dict) or body.get("model") != model:
                    raise ValueError("request model is not pinned")
                streaming = body.get("stream", False)
                if type(streaming) is not bool:
                    raise ValueError("invalid streaming flag")
                if "stream_options" in body:
                    if body["stream_options"] != {"include_usage": True} or not streaming:
                        raise ValueError("unsupported stream options")
                    body.pop("stream_options")
                body["stream"] = False
                result = relay(socket_path, body)
                if result.get("model") != model:
                    raise ValueError("response model is not pinned")
                payload = buffered_sse(result) if streaming else _encode(result)
                if len(payload) > MAX_RESPONSE_BYTES:
                    raise ValueError("translated response exceeds bound")
            except Exception:
                self.send_error(502, "Bounded model relay request failed")
                return
            self.send_response(200)
            self.send_header(
                "Content-Type", "text/event-stream" if streaming else "application/json"
            )
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    return HTTPServer(("127.0.0.1", 0), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    server = make_server(args.socket, model=args.model)
    print(
        json.dumps(
            {"url": f"http://127.0.0.1:{server.server_port}/v1", "upstream_streaming": False}
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
