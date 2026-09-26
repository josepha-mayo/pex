import asyncio
import json
import struct
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from benchmarks.model_relay import MAX_REQUEST_BYTES, SCHEMA, PinnedModelRelay


def request(request_id="call_1", **body):
    return json.dumps({"schema": SCHEMA, "request_id": request_id, "body": {
        "model": "pinned", "messages": [{"role": "user", "content": "public task"}],
        "max_tokens": 128, **body,
    }}).encode()


@pytest.mark.asyncio
async def test_relay_reserves_shared_budget_before_concurrent_backend_calls():
    calls = []
    async def backend(body):
        calls.append(body)
        await asyncio.sleep(.01)
        return {"choices": []}
    relay = PinnedModelRelay(model="pinned", max_calls=1,
                            deadline=time.perf_counter()+5, backend=backend)
    results = await asyncio.gather(relay.dispatch(request()), relay.dispatch(request("call_2")))
    assert results[0]["ok"] is True
    assert results[1]["error"] == "call_budget_exhausted"
    assert len(calls) == 1
    assert (await relay.dispatch(request()))["error"] == "duplicate_request"
    assert relay.audit[0]["status"] == "completed"
    assert "body" not in relay.audit[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [
    request(model="other"), request(stream=True), request(max_tokens=True),
    request(base_url="https://untrusted.example"),
    request(messages=[]), b'{"schema":1,"schema":2}', b'{"value":NaN}',
    b"x" * (MAX_REQUEST_BYTES + 1),
], ids=["model", "stream", "tokens", "endpoint", "messages", "duplicate_keys", "nan", "oversize"])
async def test_relay_invalid_request_never_dispatches(raw):
    async def backend(_body):
        pytest.fail("invalid request dispatched")
    relay = PinnedModelRelay(model="pinned", max_calls=1,
                            deadline=time.perf_counter()+5, backend=backend)
    assert (await relay.dispatch(raw))["error"] == "invalid_request"
    assert relay.audit == []


@pytest.mark.asyncio
async def test_relay_failure_and_timeout_consume_attempt_without_retry_or_diagnostics():
    calls = []
    async def backend(_body):
        calls.append(1)
        raise RuntimeError("private-provider-key")
    relay = PinnedModelRelay(model="pinned", max_calls=1,
                            deadline=time.perf_counter()+5, backend=backend)
    result = await relay.dispatch(request())
    assert result["error"] == "backend_failed_uncertain"
    assert "private-provider-key" not in json.dumps(result)
    assert (await relay.dispatch(request()))["error"] == "duplicate_request"
    assert len(calls) == 1
    assert relay.audit[0]["status"] == "failed_uncertain"
    async def slow(_body):
        await asyncio.sleep(10)
    timed = PinnedModelRelay(model="pinned", max_calls=1,
                            deadline=time.perf_counter()+.01, backend=slow)
    assert (await timed.dispatch(request()))["error"] == "backend_failed_uncertain"
    assert len(timed.audit) == 1
    assert (await timed.dispatch(request("later")))["error"] == "call_budget_exhausted"


@pytest.mark.asyncio
async def test_expired_relay_refuses_before_backend_dispatch():
    async def backend(_body):
        pytest.fail("expired request dispatched")
    relay = PinnedModelRelay(model="pinned", max_calls=1,
                            deadline=time.perf_counter()-1, backend=backend)
    assert (await relay.dispatch(request()))["error"] == "deadline_expired"
    assert relay.audit == []


@pytest.mark.skipif(
    sys.platform != "linux" or not Path("/usr/bin/bwrap").is_file(),
    reason="Linux bwrap required",
)
def test_actual_unix_relay_preserves_framing_and_deduplicates():
    async def check():
        calls = []
        async def backend(_body):
            calls.append(1)
            return {"choices": [{"message": {"role": "assistant", "content": "local echo"}}]}
        relay = PinnedModelRelay(model="pinned", max_calls=2,
                                deadline=time.perf_counter()+5, backend=backend)
        with TemporaryDirectory(prefix="pex-model-") as root:
            path = Path(root) / "relay.sock"
            server = await relay.listen(path)
            assert path.stat().st_mode & 0o777 == 0o600
            try:
                for expected in (True, False):
                    reader, writer = await asyncio.open_unix_connection(str(path))
                    raw = request()
                    writer.write(struct.pack("!I", len(raw)) + raw)
                    await writer.drain()
                    size = struct.unpack("!I", await reader.readexactly(4))[0]
                    result = json.loads(await reader.readexactly(size))
                    assert result["ok"] is expected
                    if not expected:
                        assert result["error"] == "duplicate_request"
                    writer.close()
                    await writer.wait_closed()
                from benchmarks.linux_sandbox import worker_relay_command
                workspace = Path(root) / "worker"
                workspace.mkdir()
                raw = request("sandbox_call")
                script = (
                    "import socket,struct,json; s=socket.socket(socket.AF_UNIX); "
                    "s.settimeout(2); s.connect('/model-relay.sock'); "
                    f"raw={raw!r}; s.sendall(struct.pack('!I',len(raw))+raw); "
                    "header=s.makefile('rb'); size=struct.unpack('!I',header.read(4))[0]; "
                    "print(json.dumps(json.loads(header.read(size)))); s.close()"
                )
                proc = await asyncio.create_subprocess_exec(
                    *worker_relay_command(
                        workspace, ["/usr/bin/python3", "-I", "-c", script], path,
                    ),
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
                assert proc.returncode == 0, stderr.decode()
                content = json.loads(stdout)["body"]["choices"][0]["message"]["content"]
                assert content == "local echo"
            finally:
                server.close()
                await server.wait_closed()
            assert calls == [1, 1]
    asyncio.run(check())
