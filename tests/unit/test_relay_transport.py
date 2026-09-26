import asyncio
import json
import struct

import httpx
import openai
import pytest
from pex_supervisor.relay_transport import UnixChatRelayTransport, relay_supervisor_model


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["success", "wrong_id", "oversize", "failed"])
@pytest.mark.parametrize("adapter", ["sdk", "pex"])
async def test_real_sdk_uses_framed_relay_without_forwarding_credentials(
    monkeypatch, mode, adapter
):
    opened, frames = [], []
    reader = asyncio.StreamReader()

    class Writer:
        def write(self, data):
            size = struct.unpack("!I", data[:4])[0]
            envelope = json.loads(data[4:])
            assert size == len(data[4:])
            assert "sdk-placeholder-secret" not in data[4:].decode()
            frames.append(envelope)
            payload = {
                "schema": "pex.model-relay.v1",
                "request_id": envelope["request_id"],
                "ok": mode != "failed",
                "body": {
                    "id": "completion-local",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "pinned",
                    "choices": [
                        {
                            "index": 0,
                            "finish_reason": "stop",
                            "message": {"role": "assistant", "content": "verified local result"},
                        }
                    ],
                },
            }
            if mode == "wrong_id":
                payload["request_id"] = "unrelated"
            raw = json.dumps(payload).encode()
            reader.feed_data(struct.pack("!I", 1_048_577 if mode == "oversize" else len(raw)) + raw)
            reader.feed_eof()

        async def drain(self):
            pass

        def close(self):
            pass

        async def wait_closed(self):
            pass

    async def connect(path):
        opened.append(path)
        return reader, Writer()

    monkeypatch.setattr(asyncio, "open_unix_connection", connect, raising=False)
    if adapter == "pex":
        monkeypatch.setenv("OPENAI_API_KEY", "ambient-key-must-not-enter-frame")
        model = relay_supervisor_model(socket_path="/model-relay.sock", model="pinned")
        assert model._pex_provenance["auth_mode"] == "controller-held"
        messages = [{"role": "user", "content": [{"text": "public task"}]}]
        if mode == "success":
            chunks = [chunk async for chunk in model.stream(messages)]
            assert "verified local result" in json.dumps(chunks)
            # A second turn uses a fresh client instead of the one closed above.
            reader = asyncio.StreamReader()
            chunks = [chunk async for chunk in model.stream(messages)]
            assert "verified local result" in json.dumps(chunks)
            assert len(frames) == 2
        else:
            with pytest.raises(openai.APIConnectionError):
                _ = [chunk async for chunk in model.stream(messages)]
            assert len(frames) == 1
        assert all("ambient-key-must-not-enter-frame" not in json.dumps(frame) for frame in frames)
        return
    transport = UnixChatRelayTransport(socket_path="/model-relay.sock", model="pinned")
    async with openai.AsyncOpenAI(
        api_key="sdk-placeholder-secret",
        max_retries=0,
        base_url="http://pex-relay.invalid/v1",
        http_client=httpx.AsyncClient(transport=transport),
    ) as client:
        kwargs = dict(
            model="pinned",
            messages=[{"role": "user", "content": "public task"}],
            max_tokens=128,
            stream=False,
        )
        if mode == "success":
            result = await client.chat.completions.create(**kwargs)
            assert result.choices[0].message.content == "verified local result"
        else:
            with pytest.raises(openai.APIConnectionError):
                await client.chat.completions.create(**kwargs)
    assert opened == ["/model-relay.sock"]
    assert len(frames) == 1
    assert frames[0]["body"]["model"] == "pinned"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url,body",
    [
        ("https://provider.example/v1/chat/completions", {"model": "pinned"}),
        ("http://pex-relay.invalid/v1/chat/completions", {"model": "changed"}),
        ("http://pex-relay.invalid/v1/chat/completions", {"model": "pinned", "stream": True}),
    ],
)
async def test_relay_transport_refuses_route_model_and_stream_before_connect(
    monkeypatch, url, body
):
    async def forbidden(_path):
        pytest.fail("invalid request opened socket")

    monkeypatch.setattr(asyncio, "open_unix_connection", forbidden, raising=False)
    async with httpx.AsyncClient(
        transport=UnixChatRelayTransport(
            socket_path="/model-relay.sock",
            model="pinned",
        )
    ) as client:
        with pytest.raises(httpx.RequestError):
            await client.post(url, json=body)
