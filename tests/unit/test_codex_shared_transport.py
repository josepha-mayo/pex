from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from pex_bridge.adapters.codex_shared import (
    CodexSharedAppServerTransport,
    SharedCodexDeliveryUncertainError,
    SharedCodexProtocolError,
)
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads
from websockets.frames import Frame, Opcode
from websockets.http11 import Request
from websockets.server import ServerProtocol


class MemoryAppServerChannel:
    """In-memory WebSocket server; no listener, proxy, or provider process."""

    def __init__(self, *, withhold: set[str] | None = None) -> None:
        self.server = ServerProtocol(max_size=1_048_576)
        self.incoming: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.remainder = b""
        self.messages: list[dict[str, Any]] = []
        self.argv: tuple[str, ...] | None = None
        self.closed = False
        self.withhold = withhold or set()
        self._fragment = bytearray()

    async def write(self, data: bytes) -> None:
        if self.closed:
            raise ConnectionError("closed")
        self.server.receive_data(data)
        for event in self.server.events_received():
            if isinstance(event, Request):
                self.server.send_response(self.server.accept(event))
                await self._flush()
                continue
            if not isinstance(event, Frame):
                continue
            if event.opcode is Opcode.TEXT:
                self._fragment = bytearray(event.data)
            elif event.opcode is Opcode.CONT:
                self._fragment.extend(event.data)
            else:
                continue
            if not event.fin:
                continue
            message = strict_json_loads(bytes(self._fragment).decode("utf-8"))
            self._fragment.clear()
            assert isinstance(message, dict)
            self.messages.append(message)
            method = message.get("method")
            if "id" not in message or method in self.withhold:
                continue
            if method == "initialize":
                result = {"serverInfo": {"name": "memory-codex"}}
            elif method == "thread/read":
                result = {"thread": {"id": message["params"]["threadId"], "turns": []}}
            elif method == "thread/resume":
                result = {"thread": {"id": message["params"]["threadId"]}
                }
            elif method == "thread/unsubscribe":
                result = {}
            else:
                result = {}
            self.server.send_text(
                strict_json_dumps({"id": message["id"], "result": result}).encode()
            )
            await self._flush()

    async def _flush(self) -> None:
        for chunk in self.server.data_to_send():
            if chunk:
                await self.incoming.put(chunk)

    async def read(self, limit: int) -> bytes:
        if self.remainder:
            result, self.remainder = self.remainder[:limit], self.remainder[limit:]
            return result
        item = await self.incoming.get()
        if item is None:
            return b""
        result, self.remainder = item[:limit], item[limit:]
        return result

    async def emit(self, message: dict[str, Any], *, fragmented: bool = False) -> None:
        encoded = strict_json_dumps(message).encode()
        if fragmented:
            midpoint = max(1, len(encoded) // 2)
            self.server.send_frame(Frame(Opcode.TEXT, encoded[:midpoint], fin=False))
            self.server.send_frame(Frame(Opcode.CONT, encoded[midpoint:], fin=True))
        else:
            self.server.send_text(encoded)
        await self._flush()

    async def emit_unknown_response(self) -> None:
        self.server.send_text(b'{"id":9999,"result":{}}')
        await self._flush()

    async def close_peer(self) -> None:
        await self.incoming.put(None)

    async def close(self) -> None:
        self.closed = True
        await self.incoming.put(None)


def make_transport(
    tmp_path: Path,
    channel: MemoryAppServerChannel,
    *,
    request_timeout_s: float = 1,
) -> CodexSharedAppServerTransport:
    executable = tmp_path / "codex.exe"
    endpoint = tmp_path / "codex.sock"
    executable.write_bytes(b"fake executable never run")
    endpoint.write_bytes(b"fake rendezvous never opened")

    async def factory(argv: tuple[str, ...]) -> MemoryAppServerChannel:
        channel.argv = argv
        return channel

    return CodexSharedAppServerTransport(
        executable,
        endpoint,
        "thr_exact",
        channel_factory=factory,
        endpoint_validator=lambda _executable, _endpoint: None,
        connect_timeout_s=1,
        request_timeout_s=request_timeout_s,
    )


@pytest.mark.asyncio
async def test_initializes_once_over_fixed_proxy_argv(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)

    first = await transport.ensure_ready()
    second = await transport.ensure_ready()

    assert first == second == {"serverInfo": {"name": "memory-codex"}}
    assert [message["method"] for message in channel.messages] == ["initialize", "initialized"]
    assert channel.argv == (
        str(tmp_path / "codex.exe"),
        "app-server",
        "proxy",
        "--sock",
        str(tmp_path / "codex.sock"),
    )
    assert "--listen" not in channel.argv
    assert transport.shared_observe_only is True
    assert transport.connection_generation == 1
    await transport.close()


@pytest.mark.asyncio
async def test_exact_thread_read_resume_and_unsubscribe(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)

    read = await transport.request(
        "thread/read", {"threadId": "thr_exact", "includeTurns": True}
    )
    resumed = await transport.request("thread/resume", {"threadId": "thr_exact"})
    unsubscribed = await transport.request(
        "thread/unsubscribe", {"threadId": "thr_exact"}
    )

    assert read["thread"]["id"] == "thr_exact"
    assert resumed["thread"]["id"] == "thr_exact"
    assert unsubscribed == {}
    await transport.close()


@pytest.mark.asyncio
async def test_concurrent_responses_route_to_their_exact_requests(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)

    read, resumed = await asyncio.gather(
        transport.request("thread/read", {"threadId": "thr_exact"}),
        transport.request("thread/resume", {"threadId": "thr_exact"}),
    )

    assert read["thread"]["turns"] == []
    assert resumed["thread"]["id"] == "thr_exact"
    assert [message["method"] for message in channel.messages].count("initialize") == 1
    await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("turn/start", {"threadId": "thr_exact", "input": []}),
        ("turn/interrupt", {"threadId": "thr_exact"}),
        ("thread/start", {}),
        ("thread/fork", {"threadId": "thr_exact"}),
        ("item/commandExecution/requestApproval", {}),
        ("thread/read", {"threadId": "thr_other", "includeTurns": True}),
        ("thread/resume", {"threadId": "thr_exact", "model": "override"}),
    ],
)
async def test_rejects_mutation_wrong_thread_and_config_before_write(
    tmp_path: Path, method: str, params: dict[str, Any]
) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)

    with pytest.raises(PermissionError):
        await transport.request(method, params)

    assert channel.messages == []
    await transport.close()


@pytest.mark.asyncio
async def test_rejects_notifications_and_approval_responses_before_connect(
    tmp_path: Path,
) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)

    with pytest.raises(PermissionError):
        await transport.notify("turn/start", {})
    with pytest.raises(PermissionError):
        await transport.respond_approval("7", "accept")

    assert channel.messages == []
    assert transport.pending_approvals == {}
    await transport.close()


@pytest.mark.asyncio
async def test_routes_fragmented_notifications_and_bounded_drain(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()

    await channel.emit(
        {"method": "turn/completed", "params": {"threadId": "thr_exact"}},
        fragmented=True,
    )
    for _ in range(20):
        if transport.notifications:
            break
        await asyncio.sleep(0)

    assert transport.drain_notifications(limit=1) == [
        {
            "method": "turn/completed",
            "params": {"threadId": "thr_exact"},
            "shared_server_request": False,
            "connection_generation": transport.connection_generation,
        }
    ]
    assert transport.notifications == []
    await transport.close()


@pytest.mark.asyncio
async def test_server_request_is_observed_without_response_authority(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()

    await channel.emit(
        {
            "id": "approval-1",
            "method": "item/commandExecution/requestApproval",
            "params": {"threadId": "thr_exact"},
        }
    )
    for _ in range(20):
        if transport.notifications:
            break
        await asyncio.sleep(0)

    assert transport.notifications[0]["shared_server_request"] is True
    assert "id" not in transport.notifications[0]
    assert transport.pending_approvals == {}
    assert not any(
        "result" in message and message.get("id") == "approval-1"
        for message in channel.messages
    )
    await transport.close()


@pytest.mark.asyncio
async def test_unknown_response_invalidates_generation_and_pending(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    original_token = transport.connection_token()

    await channel.emit_unknown_response()
    for _ in range(20):
        if not transport.initialized:
            break
        await asyncio.sleep(0)

    assert transport.initialized is False
    assert transport.connection_token()[1] > original_token[1]
    await transport.close()


@pytest.mark.asyncio
async def test_wrong_thread_notification_invalidates_connection(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()

    await channel.emit(
        {"method": "turn/completed", "params": {"threadId": "thr_other"}}
    )
    for _ in range(20):
        if not transport.initialized:
            break
        await asyncio.sleep(0)

    assert transport.initialized is False
    assert transport.notifications == []
    await transport.close()


@pytest.mark.asyncio
async def test_written_request_timeout_is_uncertain_and_not_retried(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel(withhold={"thread/resume"})
    transport = make_transport(tmp_path, channel, request_timeout_s=0.02)

    with pytest.raises(SharedCodexDeliveryUncertainError):
        await transport.request("thread/resume", {"threadId": "thr_exact"})

    assert [message["method"] for message in channel.messages].count("thread/resume") == 1
    await transport.close()


@pytest.mark.asyncio
async def test_peer_eof_invalidates_and_close_clears_observations(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    await channel.emit({"method": "thread/status/changed", "params": {}})
    for _ in range(20):
        if transport.notifications:
            break
        await asyncio.sleep(0)
    generation = transport.connection_generation

    await channel.close_peer()
    for _ in range(20):
        if not transport.initialized:
            break
        await asyncio.sleep(0)

    assert transport.initialized is False
    assert transport.connection_generation > generation
    assert transport.notifications[0]["connection_generation"] == generation
    await transport.close()
    assert transport.notifications == []
    assert channel.closed is True


def test_constructor_rejects_relative_paths_and_invalid_thread(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CodexSharedAppServerTransport(
            "codex.exe",
            tmp_path / "codex.sock",
            "thr_exact",
            endpoint_validator=lambda _executable, _endpoint: None,
        )
    with pytest.raises(ValueError):
        CodexSharedAppServerTransport(
            tmp_path / "codex.exe",
            tmp_path / "codex.sock",
            "thr_exact",
            request_timeout_s=True,
            endpoint_validator=lambda _executable, _endpoint: None,
        )
    with pytest.raises(ValueError):
        CodexSharedAppServerTransport(
            tmp_path / "codex.exe",
            tmp_path / "codex.sock",
            "\x00",
            endpoint_validator=lambda _executable, _endpoint: None,
        )


def test_endpoint_validator_runs_before_any_channel_factory(tmp_path: Path) -> None:
    executable = tmp_path / "codex.exe"
    endpoint = tmp_path / "codex.sock"
    executable.write_bytes(b"not executed")
    endpoint.write_bytes(b"not opened")
    factory_called = False

    async def factory(_argv: tuple[str, ...]) -> MemoryAppServerChannel:
        nonlocal factory_called
        factory_called = True
        return MemoryAppServerChannel()

    def reject(_executable: Path, _endpoint: Path) -> None:
        raise ValueError("ownership unavailable")

    with pytest.raises(ValueError, match="ownership unavailable"):
        CodexSharedAppServerTransport(
            executable,
            endpoint,
            "thr_exact",
            channel_factory=factory,
            endpoint_validator=reject,
        )
    assert factory_called is False


@pytest.mark.asyncio
async def test_initialize_timeout_closes_connector_and_does_not_retry(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel(withhold={"initialize"})
    transport = make_transport(tmp_path, channel, request_timeout_s=0.02)

    with pytest.raises(SharedCodexDeliveryUncertainError):
        await transport.ensure_ready()

    assert [message["method"] for message in channel.messages] == ["initialize"]
    assert channel.closed is True
    assert transport.initialized is False


@pytest.mark.asyncio
async def test_malformed_response_fails_closed_without_payload_in_error(tmp_path: Path) -> None:
    channel = MemoryAppServerChannel(withhold={"thread/read"})
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    task = asyncio.create_task(
        transport.request("thread/read", {"threadId": "thr_exact"})
    )
    for _ in range(20):
        if any(message.get("method") == "thread/read" for message in channel.messages):
            break
        await asyncio.sleep(0)
    channel.server.send_text(b'{"id":2,"result":{"secret":"unterminated}')
    await channel._flush()

    with pytest.raises(SharedCodexDeliveryUncertainError) as captured:
        await task
    assert "secret" not in str(captured.value)
    assert isinstance(captured.value.__cause__, SharedCodexProtocolError)
    await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["codex.exe", "codex.sock"])
async def test_replaced_launch_identity_rejected_before_channel_creation(tmp_path, target):
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)
    (tmp_path / target).write_bytes(b"replacement identity never executed")
    with pytest.raises(PermissionError, match="launch identity changed"):
        await transport.ensure_ready()
    assert channel.argv is None
    assert channel.messages == []
    await transport.close()


@pytest.mark.asyncio
async def test_endpoint_permissions_revalidated_on_reconnect(tmp_path):
    first, second = MemoryAppServerChannel(), MemoryAppServerChannel()
    transport = make_transport(tmp_path, first)
    calls = 0

    def validate(_exe, _endpoint):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("fixture permissions revoked")

    transport._endpoint_validator = validate
    await transport.ensure_ready()
    await transport.close()

    async def factory(_argv):
        pytest.fail("rejected endpoint must never construct another channel")

    transport._channel_factory = factory
    with pytest.raises(ValueError, match="permissions revoked"):
        await transport.ensure_ready()
    assert calls == 2
    assert second.messages == []


@pytest.mark.asyncio
async def test_partial_frame_eof_does_not_poison_next_connection(tmp_path):
    first, second = MemoryAppServerChannel(), MemoryAppServerChannel()
    transport = make_transport(tmp_path, first)
    await transport.ensure_ready()
    first.server.send_frame(Frame(Opcode.TEXT, b'{"method":', fin=False))
    await first._flush()
    await first.close_peer()
    for _ in range(100):
        if not transport.initialized:
            break
        await asyncio.sleep(0)
    assert not transport.initialized
    assert transport._fragment_opcode is None

    async def factory(_argv):
        return second

    transport._channel_factory = factory
    assert await transport.ensure_ready() == {"serverInfo": {"name": "memory-codex"}}
    await transport.close()


class FailingWriteChannel(MemoryAppServerChannel):
    write_mode = "normal"

    async def write(self, data):
        if self.write_mode == "block":
            await asyncio.Event().wait()
        await super().write(data)
        if self.write_mode == "partial-fail":
            raise ConnectionError("fixture drain failed after delivery")


@pytest.mark.asyncio
@pytest.mark.parametrize("write_mode", ["block", "partial-fail"])
async def test_write_failure_or_stall_is_bounded_uncertain_and_closes(tmp_path, write_mode):
    channel = FailingWriteChannel()
    transport = make_transport(tmp_path, channel, request_timeout_s=0.02)
    await transport.ensure_ready()
    channel.write_mode = write_mode
    with pytest.raises(SharedCodexDeliveryUncertainError):
        await asyncio.wait_for(
            transport.request("thread/resume", {"threadId": "thr_exact"}), timeout=1
        )
    assert not transport.initialized
    assert channel.closed
    if write_mode == "partial-fail":
        assert sum(message.get("method") == "thread/resume" for message in channel.messages) == 1
    assert transport._pending == {}


@pytest.mark.asyncio
async def test_request_cancellation_revokes_connection_and_closes(tmp_path):
    channel = MemoryAppServerChannel(withhold={"thread/resume"})
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    token = transport.connection_token()
    task = asyncio.create_task(transport.request("thread/resume", {"threadId": "thr_exact"}))
    for _ in range(100):
        if any(message.get("method") == "thread/resume" for message in channel.messages):
            break
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.connection_token() != token
    assert not transport.initialized
    assert channel.closed
    assert transport._pending == {}


@pytest.mark.asyncio
async def test_close_during_factory_cannot_resurrect_connection(tmp_path):
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)
    entered, release = asyncio.Event(), asyncio.Event()

    async def factory(_argv):
        entered.set()
        await release.wait()
        return channel

    transport._channel_factory = factory
    task = asyncio.create_task(transport.ensure_ready())
    await entered.wait()
    await transport.close()
    release.set()
    with pytest.raises(ConnectionError, match="superseded"):
        await task
    assert not transport.initialized
    assert transport._channel is None
    assert channel.closed
    assert channel.messages == []


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["blocked-write", "drip-read"])
async def test_whole_upgrade_has_one_deadline(tmp_path, mode):
    class UpgradeChannel(MemoryAppServerChannel):
        async def write(self, data):
            if mode == "blocked-write":
                await asyncio.Event().wait()

        async def read(self, limit):
            await asyncio.sleep(0.005)
            return b"H"

    channel = UpgradeChannel()
    transport = make_transport(tmp_path, channel)
    transport.connect_timeout_s = 0.03
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(transport.ensure_ready(), timeout=1)
    assert channel.closed
    assert transport._channel is None
    assert not transport.initialized


@pytest.mark.asyncio
@pytest.mark.parametrize("response_id", [True, 2.0, "2", None])
async def test_response_id_types_cannot_alias_pending_request(tmp_path, response_id):
    channel = MemoryAppServerChannel(withhold={"thread/read"})
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    task = asyncio.create_task(transport.request("thread/read", {"threadId": "thr_exact"}))
    for _ in range(100):
        if any(message.get("method") == "thread/read" for message in channel.messages):
            break
        await asyncio.sleep(0)
    await channel.emit({"id": response_id, "result": {"forged": True}})
    with pytest.raises(SharedCodexDeliveryUncertainError):
        await task
    assert not transport.initialized
    assert channel.closed


@pytest.mark.asyncio
async def test_ambiguous_response_cannot_resolve_pending_request(tmp_path):
    channel = MemoryAppServerChannel(withhold={"thread/read"})
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    task = asyncio.create_task(transport.request("thread/read", {"threadId": "thr_exact"}))
    for _ in range(100):
        if len(channel.messages) == 3:
            break
        await asyncio.sleep(0)
    await channel.emit({"id": 2, "result": {}, "error": {}})
    with pytest.raises(SharedCodexDeliveryUncertainError):
        await task
    assert not transport.initialized


@pytest.mark.asyncio
async def test_old_reader_cleanup_cannot_clear_replacement_channel(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class SlowCloseChannel(MemoryAppServerChannel):
        async def close(self):
            entered.set()
            await release.wait()
            await super().close()

    first, second = SlowCloseChannel(), MemoryAppServerChannel()
    transport = make_transport(tmp_path, first)
    await transport.ensure_ready()
    first_reader = transport._reader_task
    await first.close_peer()
    await entered.wait()

    async def factory(_argv):
        return second

    transport._channel_factory = factory
    await transport.ensure_ready()
    token = transport.connection_token()
    release.set()
    await first_reader
    assert transport.initialized
    assert transport._channel is second
    assert transport.connection_token() == token
    assert not second.closed
    await transport.close()


@pytest.mark.asyncio
async def test_notification_overflow_fails_closed_without_unbounded_queue(tmp_path, monkeypatch):
    import pex_bridge.adapters.codex_shared as shared

    monkeypatch.setattr(shared, "MAX_NOTIFICATIONS", 2)
    channel = MemoryAppServerChannel()
    transport = make_transport(tmp_path, channel)
    await transport.ensure_ready()
    for _ in range(3):
        await channel.emit({"method": "turn/completed", "params": {"threadId": "thr_exact"}})
    for _ in range(100):
        if not transport.initialized:
            break
        await asyncio.sleep(0)
    assert not transport.initialized
    assert len(transport.notifications) == 2
    assert channel.closed
    await transport.close()


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows ACL/resource check")
def test_native_private_temp_acl_check_does_not_leak_handles(tmp_path):
    import ctypes
    from ctypes import wintypes

    from pex_bridge.adapters.codex_shared import _windows_owned_by_current_user

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessHandleCount.restype = wintypes.BOOL

    def handles():
        count = wintypes.DWORD()
        assert kernel.GetProcessHandleCount(kernel.GetCurrentProcess(), ctypes.byref(count))
        return count.value

    # Warm native library/security initialization before checking repeated calls.
    assert _windows_owned_by_current_user(tmp_path)
    before = handles()
    for _ in range(25):
        assert _windows_owned_by_current_user(tmp_path)
    assert handles() <= before + 2


@pytest.mark.skipif(sys.platform != "win32", reason="native Windows launch path ACL check")
def test_native_private_leaf_does_not_bypass_unsafe_ancestor_acl(tmp_path):
    from pex_bridge.adapters.codex_shared import (
        _windows_owned_by_current_user,
        validate_shared_endpoint,
    )

    executable, endpoint = tmp_path / "never-run.exe", tmp_path / "never-open.sock"
    executable.write_bytes(b"fixture executable is never run")
    endpoint.write_bytes(b"fixture endpoint is never opened")
    assert _windows_owned_by_current_user(tmp_path)
    protected = all(
        _windows_owned_by_current_user(path, protected_launch=True)
        for path in (executable, *executable.parents)
    )
    if protected:
        validate_shared_endpoint(executable, endpoint)
    else:
        # This host can grant sandbox users Modify on AppData ancestors; a
        # private leaf must not be enough to override that failed launch gate.
        with pytest.raises(ValueError, match="launch path is not protected"):
            validate_shared_endpoint(executable, endpoint)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows shell-wrapper boundary")
def test_windows_launch_rejects_shell_wrapper_before_acl_or_execution(tmp_path):
    from pex_bridge.adapters.codex_shared import validate_shared_endpoint

    wrapper, endpoint = tmp_path / "codex.cmd", tmp_path / "endpoint.sock"
    wrapper.write_bytes(b"never executed")
    endpoint.write_bytes(b"never opened")
    with pytest.raises(ValueError, match="native executable"):
        validate_shared_endpoint(wrapper, endpoint)


@pytest.mark.asyncio
async def test_cancelled_process_creation_reaps_only_late_connector(tmp_path, monkeypatch):
    import pex_bridge.adapters.codex_shared as shared

    entered, release = asyncio.Event(), asyncio.Event()
    closed = False
    calls = []

    class FakeStdin:
        def close(self):
            nonlocal closed
            closed = True

    class FakeProcess:
        stdin = FakeStdin()
        returncode = 0

        async def wait(self):
            return 0

    async def fake_spawn(*argv, **kwargs):
        calls.append((argv, kwargs))
        entered.set()
        await release.wait()
        return FakeProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_spawn)
    binary = str(tmp_path / "never-run.exe")
    task = asyncio.create_task(shared._open_proxy_channel((binary, "app-server", "proxy")))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not closed
    release.set()
    await asyncio.gather(*tuple(shared._CONNECTOR_REAPERS))
    assert closed
    assert len(calls) == 1
    assert calls[0][1]["cwd"] == str(tmp_path)
