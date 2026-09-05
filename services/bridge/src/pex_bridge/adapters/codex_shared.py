"""Observe-only transport for a user-owned shared Codex App Server.

The transport owns a short-lived ``codex app-server proxy`` connector, never
the App Server or worker.  It is deliberately bound to one existing thread and
rejects worker mutations through its generic API. A separate internal text
dispatch primitive is inactive until a caller supplies durable control authority.
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import inspect
import math
import os
import stat
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from websockets.client import ClientProtocol
from websockets.frames import Frame, Opcode
from websockets.protocol import State
from websockets.uri import parse_uri

from pex_bridge.adapters.base import bounded_adapter_id, bounded_observed_mapping
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads

CLIENT_INFO = {"name": "pex", "title": "PEX", "version": "0.1.0"}
INIT_PARAMS = {"clientInfo": CLIENT_INFO, "capabilities": {}}
MAX_MESSAGE_BYTES = 1_048_576
MAX_PENDING = 1_024
MAX_NOTIFICATIONS = 1_024
MAX_PATH_CHARS = 4_096
MAX_DISPATCH_TEXT_BYTES = 65_536
CLEANUP_TIMEOUT_SECONDS = 3.5
_CONNECTOR_REAPERS: set[asyncio.Task[None]] = set()


class SharedCodexProtocolError(RuntimeError):
    """The shared endpoint violated the bounded App Server protocol."""


class SharedCodexRemoteError(RuntimeError):
    """The shared App Server explicitly rejected a request."""

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class SharedCodexDeliveryUncertainError(RuntimeError):
    """A permitted request was written but no response was verified."""


class SharedCodexTextDispatchRejected(PermissionError):
    """This text dispatch did not enqueue any worker-input bytes."""


class SharedCodexTextDispatchCancelled(asyncio.CancelledError):
    """Cancellation after enqueue: delivery is unknown, never safe to retry."""

    delivery_uncertain = True


class SharedCodexTextDispatchRemoteError(SharedCodexDeliveryUncertainError):
    """A matching vendor error arrived; it does not prove absence of side effects."""

    result_class = "returned_error"
    delivery_uncertain = True

    def __init__(self, *, code: int | None) -> None:
        super().__init__("text dispatch returned a vendor error; delivery remains uncertain")
        self.code = code


@dataclass(frozen=True)
class SharedCodexTextAcknowledgement:
    method: str
    thread_id: str
    turn_id: str
    client_user_message_id: str
    connection_token: tuple[str, int]
    received_revision_at_write: int
    received_revision_at_ack: int


class RawByteChannel(Protocol):
    async def read(self, limit: int) -> bytes: ...

    async def write(self, data: bytes) -> None: ...

    async def close(self) -> None: ...


ChannelFactory = Callable[[tuple[str, ...]], Awaitable[RawByteChannel]]
EndpointValidator = Callable[[Path, Path], None]


def _bounded_path(value: str | os.PathLike[str], *, label: str) -> Path:
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError(f"{label} must be a path")
    raw = os.fspath(value)
    if not raw or "\x00" in raw or len(raw) > MAX_PATH_CHARS:
        raise ValueError(f"{label} is invalid")
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError(f"{label} must be absolute")
    return path


def _reject_reparse_components(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except OSError as exc:
            raise ValueError("shared Codex endpoint path is unavailable") from exc
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("shared Codex endpoint path crosses a link")
        attributes = getattr(info, "st_file_attributes", 0)
        reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if attributes & reparse:
            raise ValueError("shared Codex endpoint path crosses a reparse point")


def _windows_owned_by_current_user(path: Path, *, protected_launch: bool = False) -> bool:
    """Check private endpoint ACLs, or trusted-owner/non-public-write launch ACLs.

    This conservative check deliberately rejects unsupported owners/ACE forms;
    it is not Authenticode verification or an atomic handle-based launch.
    """

    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    token_query = 0x0008
    token_user = 1
    owner_security_information = 0x00000001
    dacl_security_information = 0x00000004
    se_file_object = 1
    acl_size_information = 2
    access_allowed_ace_type = 0
    access_denied_ace_type = 1
    win_local_system_sid = 22
    win_builtin_administrators_sid = 26

    class AclSizeInformation(ctypes.Structure):
        _fields_ = [
            ("AceCount", wintypes.DWORD),
            ("AclBytesInUse", wintypes.DWORD),
            ("AclBytesFree", wintypes.DWORD),
        ]

    class AceHeader(ctypes.Structure):
        _fields_ = [
            ("AceType", ctypes.c_ubyte),
            ("AceFlags", ctypes.c_ubyte),
            ("AceSize", wintypes.WORD),
        ]
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
    advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi32.EqualSid.restype = wintypes.BOOL
    advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)
    ]
    advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    advapi32.CreateWellKnownSid.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.CreateWellKnownSid.restype = wintypes.BOOL
    advapi32.GetAclInformation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_int,
    ]
    advapi32.GetAclInformation.restype = wintypes.BOOL
    advapi32.GetAce.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetAce.restype = wintypes.BOOL
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), token_query, ctypes.byref(token)
    ):
        return False
    descriptor = ctypes.c_void_p()
    owner = ctypes.c_void_p()
    dacl = ctypes.c_void_p()
    allocated_sids: list[ctypes.c_void_p] = []
    try:
        needed = wintypes.DWORD()
        advapi32.GetTokenInformation(token, token_user, None, 0, ctypes.byref(needed))
        if not needed.value:
            return False
        token_data = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(
            token, token_user, token_data, needed, ctypes.byref(needed)
        ):
            return False
        token_sid = ctypes.cast(token_data, ctypes.POINTER(ctypes.c_void_p))[0]
        status = advapi32.GetNamedSecurityInfoW(
            str(path),
            se_file_object,
            owner_security_information | dacl_security_information,
            ctypes.byref(owner),
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if status != 0 or not owner.value or not token_sid or not dacl.value:
            return False
        trusted_sids = [token_sid]
        trusted_buffers: list[ctypes.Array[ctypes.c_char]] = []
        for sid_type in (win_local_system_sid, win_builtin_administrators_sid):
            sid_size = wintypes.DWORD(68)
            sid_buffer = ctypes.create_string_buffer(sid_size.value)
            if not advapi32.CreateWellKnownSid(
                sid_type, None, sid_buffer, ctypes.byref(sid_size)
            ):
                return False
            trusted_buffers.append(sid_buffer)
            trusted_sids.append(ctypes.cast(sid_buffer, ctypes.c_void_p).value)

        def parse_sid(value: str) -> ctypes.c_void_p | None:
            sid = ctypes.c_void_p()
            if not advapi32.ConvertStringSidToSidW(value, ctypes.byref(sid)):
                return None
            allocated_sids.append(sid)
            return sid

        # The Windows servicing account owns protected OS/package ancestors.
        if protected_launch:
            installer = parse_sid(
                "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
            )
            if installer is None:
                return False
            trusted_sids.append(installer.value)
        if not any(
            advapi32.EqualSid(owner, trusted)
            for trusted in (trusted_sids if protected_launch else [token_sid])
        ):
            return False
        # OWNER RIGHTS means the already-validated owner, not another user.
        owner_rights = parse_sid("S-1-3-4")
        if owner_rights is None:
            return False
        trusted_sids.append(owner_rights.value)
        acl_info = AclSizeInformation()
        if not advapi32.GetAclInformation(
            dacl,
            ctypes.byref(acl_info),
            ctypes.sizeof(acl_info),
            acl_size_information,
        ):
            return False
        for index in range(acl_info.AceCount):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)) or not ace.value:
                return False
            header = ctypes.cast(ace, ctypes.POINTER(AceHeader)).contents
            if header.AceFlags & 0x08:  # INHERIT_ONLY_ACE does not grant this object access.
                continue
            if header.AceType == access_denied_ace_type:
                continue
            if header.AceType != access_allowed_ace_type or header.AceSize < 12:
                return False
            ace_sid = ctypes.c_void_p(ace.value + 8)
            if not any(advapi32.EqualSid(ace_sid, trusted) for trusted in trusted_sids):
                mask = ctypes.c_uint32.from_address(ace.value + 4).value
                # Public read/execute is compatible with a protected executable.
                # Directory creation alone cannot replace an existing child;
                # DELETE_CHILD, delete, ownership and ACL writes can.
                mutation_mask = 0x500D0000 | (0x40 if path.is_dir() else 0x116)
                if not protected_launch or mask & mutation_mask:
                    return False
        return True
    finally:
        kernel32.CloseHandle(token)
        if descriptor.value:
            kernel32.LocalFree(descriptor)
        for sid in allocated_sids:
            kernel32.LocalFree(sid)


def validate_shared_endpoint(codex_bin: Path, socket_path: Path) -> None:
    """Fail closed unless executable and current-user endpoint are provable."""

    if not codex_bin.is_file():
        raise ValueError("Codex proxy executable must be an existing file")
    if sys.platform == "win32" and codex_bin.suffix.casefold() != ".exe":
        raise ValueError("Codex proxy requires a native executable, not a shell wrapper")
    _reject_reparse_components(codex_bin)
    try:
        endpoint_mode = socket_path.lstat().st_mode
    except OSError as exc:
        raise ValueError("shared Codex endpoint must exist") from exc
    if not (stat.S_ISREG(endpoint_mode) or stat.S_ISSOCK(endpoint_mode)):
        raise ValueError("shared Codex endpoint must be an existing rendezvous file")
    _reject_reparse_components(socket_path)
    if sys.platform == "win32":
        for launch_path in (codex_bin, *codex_bin.parents, *socket_path.parents):
            if not _windows_owned_by_current_user(launch_path, protected_launch=True):
                raise ValueError("shared Codex launch path is not protected")
        if not _windows_owned_by_current_user(socket_path.parent):
            raise ValueError("shared Codex endpoint ownership could not be verified")
        if not _windows_owned_by_current_user(socket_path):
            raise ValueError("shared Codex endpoint ownership could not be verified")
        return
    for launch_path in (codex_bin, *codex_bin.parents, *socket_path.parents):
        info = launch_path.stat()
        if info.st_uid not in {os.getuid(), 0} or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError("shared Codex launch path is not protected")
    if not os.access(codex_bin, os.X_OK):
        raise ValueError("Codex proxy executable is not executable")
    parent_info = socket_path.parent.stat()
    endpoint_info = socket_path.stat()
    if parent_info.st_uid != os.getuid() or endpoint_info.st_uid != os.getuid():
        raise ValueError("shared Codex endpoint is not owned by the current user")
    if stat.S_IMODE(parent_info.st_mode) & 0o077:
        raise ValueError("shared Codex endpoint directory is not private")


def _launch_identity(codex_bin: Path, socket_path: Path) -> tuple[Any, ...]:
    """Pin file identity and executable bytes, never rendezvous credentials.

    Rechecking narrows but cannot eliminate same-user/admin path replacement
    between validation and OS launch/connect. No vendor-authenticity claim.
    """
    _reject_reparse_components(codex_bin)
    _reject_reparse_components(socket_path)
    identities = []
    for path in (codex_bin, socket_path):
        info = path.stat()
        identities.append((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns))
    if identities[0][2] > 512 * 1024 * 1024:
        raise ValueError("Codex executable exceeds the identity hashing bound")
    digest = hashlib.sha256()
    with codex_bin.open("rb") as executable:
        while block := executable.read(1024 * 1024):
            digest.update(block)
    return (*identities, digest.hexdigest())


def _minimal_subprocess_env() -> dict[str, str]:
    allowed = {
        "APPDATA",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "LANG",
        "LC_ALL",
        "LOCALAPPDATA",
        "NO_COLOR",
        "PATH",
        "PATHEXT",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


class _ProxyProcessChannel:
    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process

    async def read(self, limit: int) -> bytes:
        if self._process.stdout is None:
            return b""
        return await self._process.stdout.read(limit)

    async def write(self, data: bytes) -> None:
        if self._process.stdin is None or self._process.returncode is not None:
            raise ConnectionError("Codex proxy channel is closed")
        self._process.stdin.write(data)
        await self._process.stdin.drain()

    async def close(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()
        try:
            await asyncio.wait_for(self._process.wait(), timeout=1)
            return
        except TimeoutError:
            pass
        try:
            self._process.terminate()
        except ProcessLookupError:
            return
        try:
            await asyncio.wait_for(self._process.wait(), timeout=1)
        except TimeoutError:
            try:
                self._process.kill()
            except ProcessLookupError:
                return
            await asyncio.wait_for(self._process.wait(), timeout=1)


async def _open_proxy_channel(argv: tuple[str, ...]) -> RawByteChannel:
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    spawn = asyncio.create_task(
        asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=_minimal_subprocess_env(),
            cwd=str(Path(argv[0]).parent),
            limit=MAX_MESSAGE_BYTES,
            **kwargs,
        )
    )
    try:
        process = await asyncio.shield(spawn)
    except BaseException:
        # OS spawn can finish after caller cancellation. Keep an explicit owner
        # to reap that connector; never terminate the user-owned App Server.
        async def reap_late_connector() -> None:
            try:
                late_process = await spawn
                await asyncio.wait_for(
                    _ProxyProcessChannel(late_process).close(),
                    timeout=CLEANUP_TIMEOUT_SECONDS,
                )
            except (Exception, asyncio.CancelledError):
                pass

        reaper = asyncio.create_task(reap_late_connector())
        _CONNECTOR_REAPERS.add(reaper)
        reaper.add_done_callback(_CONNECTOR_REAPERS.discard)
        raise
    return _ProxyProcessChannel(process)


class CodexSharedAppServerTransport:
    """One exact-thread, observe-only connection to an existing App Server."""

    shared_observe_only = True

    def __init__(
        self,
        codex_bin: str | os.PathLike[str],
        socket_path: str | os.PathLike[str],
        thread_id: str,
        *,
        channel_factory: ChannelFactory | None = None,
        endpoint_validator: EndpointValidator = validate_shared_endpoint,
        connect_timeout_s: float = 10,
        request_timeout_s: float = 45,
    ) -> None:
        self.codex_bin = _bounded_path(codex_bin, label="Codex executable")
        self.socket_path = _bounded_path(socket_path, label="shared Codex endpoint")
        endpoint_validator(self.codex_bin, self.socket_path)
        self.thread_id = bounded_adapter_id(thread_id, field="Codex existing thread id")
        if (
            isinstance(connect_timeout_s, bool)
            or not isinstance(connect_timeout_s, (int, float))
            or not math.isfinite(connect_timeout_s)
            or not 0 < connect_timeout_s <= 60
            or isinstance(request_timeout_s, bool)
            or not isinstance(request_timeout_s, (int, float))
            or not math.isfinite(request_timeout_s)
            or not 0 < request_timeout_s <= 120
        ):
            raise ValueError("shared Codex timeouts exceed the safety bound")
        self.connect_timeout_s = float(connect_timeout_s)
        self.request_timeout_s = float(request_timeout_s)
        self._endpoint_validator = endpoint_validator
        self._pinned_launch_identity = _launch_identity(self.codex_bin, self.socket_path)
        self._channel_factory = channel_factory or _open_proxy_channel
        self._argv = (
            str(self.codex_bin),
            "app-server",
            "proxy",
            "--sock",
            str(self.socket_path),
        )
        identity_material = "\0".join(
            ("pex-codex-shared-v1", os.path.normcase(str(self.socket_path.resolve())))
        )
        self.endpoint_identity = hashlib.sha256(identity_material.encode()).hexdigest()
        self.initialized = False
        self.connection_generation = 0
        self.init_result: dict[str, Any] | None = None
        self.notifications: list[dict[str, Any]] = []
        self.pending_approvals: dict[str, dict[str, Any]] = {}
        self._channel: RawByteChannel | None = None
        self._websocket: ClientProtocol | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._close_task: asyncio.Task[None] | None = None
        self._pending: dict[int | str, asyncio.Future[dict[str, Any]]] = {}
        self._text_pending: set[int] = set()
        self._next_id = 1
        self._initialize_lock = asyncio.Lock()
        self._protocol_lock = asyncio.Lock()
        self._text_dispatch_lock = asyncio.Lock()
        self._received_envelope_revision = 0
        self._closing = False
        self._close_revision = 0
        self._fragment_opcode: Opcode | None = None
        self._fragment = bytearray()

    def connection_token(self) -> tuple[str, int]:
        return self.endpoint_identity, self.connection_generation

    @property
    def received_envelope_revision(self) -> int:
        """Local complete-envelope count, not a server/global input revision."""
        return self._received_envelope_revision

    def drain_notifications(self, *, limit: int = 256) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 0 < limit <= 256:
            raise ValueError("notification drain limit exceeds the safety bound")
        drained = self.notifications[:limit]
        del self.notifications[: len(drained)]
        return drained

    async def _flush(
        self, websocket: ClientProtocol, channel: RawByteChannel
    ) -> None:
        for chunk in websocket.data_to_send():
            if chunk:
                await channel.write(chunk)

    @staticmethod
    async def _close_channel(channel: RawByteChannel) -> None:
        try:
            await asyncio.wait_for(channel.close(), timeout=CLEANUP_TIMEOUT_SECONDS)
        except (TimeoutError, OSError):
            # Authority has already been revoked. Never make cleanup unbounded.
            pass

    async def _open(self) -> None:
        if self._close_task is not None and not self._close_task.done():
            raise ConnectionError("shared Codex connector cleanup is still in progress")
        self._closing = False
        self.connection_generation += 1
        close_revision = self._close_revision
        channel: RawByteChannel | None = None
        try:
            self._endpoint_validator(self.codex_bin, self.socket_path)
            if _launch_identity(self.codex_bin, self.socket_path) != self._pinned_launch_identity:
                raise PermissionError("shared Codex launch identity changed")
            self._fragment.clear()
            self._fragment_opcode = None
            async with asyncio.timeout(self.connect_timeout_s):
                channel = await self._channel_factory(self._argv)
                if self._close_revision != close_revision:
                    raise ConnectionError("shared Codex open was superseded by close")
                self._channel = channel
                websocket = ClientProtocol(
                    parse_uri("ws://localhost/rpc"), max_size=MAX_MESSAGE_BYTES
                )
                self._websocket = websocket
                websocket.send_request(websocket.connect())
                await self._flush(websocket, channel)
                while websocket.state is State.CONNECTING:
                    data = await channel.read(64 * 1024)
                    if not data:
                        raise SharedCodexProtocolError("Codex proxy closed during upgrade")
                    async with self._protocol_lock:
                        websocket.receive_data(data)
                        events = websocket.events_received()
                        await self._flush(websocket, channel)
                    if any(isinstance(event, Frame) for event in events):
                        raise SharedCodexProtocolError(
                            "shared Codex sent data before initialization"
                        )
                if websocket.state is not State.OPEN:
                    raise SharedCodexProtocolError("Codex proxy rejected the WebSocket upgrade")
                if self._close_revision != close_revision:
                    raise ConnectionError("shared Codex open was superseded by close")
                self._reader_task = asyncio.create_task(self._read_loop(channel, websocket))
        except BaseException:
            if self._channel is channel:
                self._channel = None
                self._websocket = None
                self._invalidate(ConnectionError("shared Codex open failed"))
            if channel is not None:
                await self._close_channel(channel)
            raise

    async def _send_json(self, payload: dict[str, Any]) -> None:
        encoded = strict_json_dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise ValueError("shared Codex request exceeds the write safety bound")
        websocket, channel = self._websocket, self._channel
        if websocket is None or channel is None:
            raise ConnectionError("shared Codex channel is unavailable")
        async with self._protocol_lock:
            if self._channel is not channel:
                raise ConnectionError("shared Codex channel was replaced")
            websocket.send_text(encoded)
            await self._flush(websocket, channel)

    async def _read_loop(self, channel: RawByteChannel, websocket: ClientProtocol) -> None:
        failure: BaseException = ConnectionError("shared Codex channel closed")
        try:
            while True:
                data = await channel.read(64 * 1024)
                if not data:
                    break
                async with self._protocol_lock:
                    if self._channel is not channel:
                        break
                    websocket.receive_data(data)
                    events = websocket.events_received()
                    # Publish every complete envelope before releasing write
                    # serialization or awaiting a control-frame flush. Otherwise
                    # a writer can pass its freshness check ahead of input that
                    # this reader has already decoded.
                    for event in events:
                        if isinstance(event, Frame):
                            message = self._accept_frame(event)
                            if message is not None:
                                self._received_envelope_revision += 1
                                self._route_message(message)
                    async with asyncio.timeout(self.request_timeout_s):
                        await self._flush(websocket, channel)
                if websocket.state is State.CLOSED:
                    break
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            failure = SharedCodexProtocolError("shared Codex protocol reader failed")
            failure.__cause__ = exc
        finally:
            if self._channel is channel and not self._closing:
                self._channel = None
                self._websocket = None
                self._invalidate(failure)
                await self._close_channel(channel)

    def _accept_frame(self, frame: Frame) -> bytes | None:
        if frame.opcode in {Opcode.PING, Opcode.PONG, Opcode.CLOSE}:
            return None
        if frame.opcode is Opcode.TEXT:
            if self._fragment_opcode is not None:
                raise SharedCodexProtocolError("overlapping WebSocket messages")
            if frame.fin:
                return frame.data
            self._fragment_opcode = frame.opcode
            self._fragment = bytearray(frame.data)
            return None
        if frame.opcode is Opcode.CONT:
            if self._fragment_opcode is not Opcode.TEXT:
                raise SharedCodexProtocolError("unexpected WebSocket continuation")
            self._fragment.extend(frame.data)
            if len(self._fragment) > MAX_MESSAGE_BYTES:
                raise SharedCodexProtocolError("shared Codex message exceeds the safety bound")
            if not frame.fin:
                return None
            result = bytes(self._fragment)
            self._fragment.clear()
            self._fragment_opcode = None
            return result
        raise SharedCodexProtocolError("binary WebSocket messages are unsupported")

    def _route_message(self, encoded: bytes) -> None:
        if len(encoded) > MAX_MESSAGE_BYTES:
            raise SharedCodexProtocolError("shared Codex message exceeds the safety bound")
        try:
            message = strict_json_loads(encoded.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise SharedCodexProtocolError("shared Codex returned malformed JSON") from exc
        if not isinstance(message, dict):
            raise SharedCodexProtocolError("shared Codex returned a non-object message")
        raw_id = message.get("id")
        message_id = _validated_jsonrpc_id(raw_id)
        if raw_id is not None and message_id is None:
            raise SharedCodexProtocolError("shared Codex returned an invalid response id")
        if message_id is not None and ("result" in message or "error" in message):
            if "method" in message or ("result" in message and "error" in message):
                raise SharedCodexProtocolError("shared Codex returned an ambiguous response")
            future = self._pending.pop(message_id, None)
            if future is None:
                raise SharedCodexProtocolError("shared Codex returned an unknown response id")
            if "error" in message:
                error = message["error"]
                if message_id in self._text_pending and (
                    not isinstance(error, dict)
                    or type(error.get("code")) is not int
                    or not isinstance(error.get("message"), str)
                ):
                    future.set_exception(
                        SharedCodexProtocolError("shared Codex refusal is malformed")
                    )
                    raise SharedCodexProtocolError("shared Codex refusal is malformed")
                code = error.get("code") if isinstance(error, dict) else None
                future.set_exception(
                    SharedCodexRemoteError(
                        "shared Codex request failed", code=code if type(code) is int else None
                    )
                )
                return
            result = message.get("result")
            if not isinstance(result, dict):
                future.set_exception(
                    SharedCodexProtocolError("shared Codex returned a malformed result")
                )
                raise SharedCodexProtocolError("shared Codex returned a malformed result")
            future.set_result(result)
            return
        raw_method = message.get("method")
        if raw_method is None:
            raise SharedCodexProtocolError("shared Codex message has no route")
        method = bounded_adapter_id(raw_method, field="shared Codex event method")
        params = bounded_observed_mapping(message.get("params"))
        if params is None:
            raise SharedCodexProtocolError("shared Codex event has malformed params")
        event_thread_id = params.get("threadId")
        if event_thread_id is not None and event_thread_id != self.thread_id:
            raise SharedCodexProtocolError("shared Codex event targets the wrong thread")
        if len(self.notifications) >= MAX_NOTIFICATIONS:
            raise SharedCodexProtocolError("shared Codex notification bound reached")
        # Server requests are observations only. Never retain their request ID or
        # expose an approval response surface on this connection.
        self.notifications.append(
            {
                "method": method,
                "params": params,
                "shared_server_request": message_id is not None,
                "connection_generation": self.connection_generation,
            }
        )

    def _invalidate(self, failure: BaseException) -> None:
        self.initialized = False
        self.init_result = None
        self.connection_generation += 1
        self._fragment.clear()
        self._fragment_opcode = None
        for future in self._pending.values():
            if not future.done():
                future.set_exception(failure)
        self._pending.clear()

    async def _request_unchecked(
        self, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        if len(self._pending) >= MAX_PENDING:
            raise RuntimeError("shared Codex pending request bound reached")
        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            async with asyncio.timeout(self.request_timeout_s):
                await self._send_json({"id": request_id, "method": method, "params": params})
                return await future
        except SharedCodexRemoteError:
            raise
        except asyncio.CancelledError:
            await self.close()
            raise
        except BaseException as exc:
            # A failing drain may already have delivered bytes. There is no
            # safe transparent retry or continued use after an uncertain send.
            await self.close()
            raise SharedCodexDeliveryUncertainError(
                "shared Codex request was attempted without a verified response"
            ) from exc
        finally:
            self._pending.pop(request_id, None)
            if future.done() and not future.cancelled():
                future.exception()  # Consume any failure published during cleanup.

    async def ensure_ready(self) -> dict[str, Any]:
        if self.initialized and self.init_result is not None:
            return dict(self.init_result)
        async with self._initialize_lock:
            if self.initialized and self.init_result is not None:
                return dict(self.init_result)
            if self._channel is None:
                await self._open()
            channel, close_revision = self._channel, self._close_revision
            try:
                result = await self._request_unchecked("initialize", INIT_PARAMS)
                async with asyncio.timeout(self.request_timeout_s):
                    await self._send_json({"method": "initialized", "params": {}})
                if self._channel is not channel or self._close_revision != close_revision:
                    raise ConnectionError("shared Codex initialization was superseded")
            except BaseException:
                await self.close()
                raise
            self.initialized = True
            self.init_result = dict(result)
            return dict(result)

    async def _settle_text_dispatch_close(self) -> None:
        """Own the one cleanup task even through repeated caller cancellation."""
        self._invalidate(ConnectionError("shared Codex text delivery became uncertain"))
        closing = asyncio.create_task(self.close())
        while not closing.done():
            try:
                await asyncio.shield(closing)
            except asyncio.CancelledError:
                continue
            except BaseException:
                break
        if not closing.cancelled():
            try:
                closing.result()
            except BaseException:
                # Preserve the dispatch outcome, without claiming cleanup worked.
                pass

    async def _dispatch_text(
        self,
        *,
        thread_id: str,
        text: str,
        client_user_message_id: str,
        expected_connection_token: tuple[str, int],
        expected_received_revision: int,
        expected_turn_id: str | None,
        final_authority_check: Callable[[], None],
    ) -> SharedCodexTextAcknowledgement:
        """Send once on this connection under caller-owned durable authority.

        ``None`` selects start; an exact turn ID selects steer. This is not a
        capability grant and never initializes/reconnects. The mandatory final
        synchronous callback must validate current local policy/effect authority.
        No local check excludes another client's subsequent input: start has no
        server idle CAS, and steer fences only the turn ID, not its latest input.
        ``clientUserMessageId`` is correlation, not a vendor idempotency promise.
        """
        try:
            for value in (thread_id, client_user_message_id, expected_turn_id):
                if value is not None and (not isinstance(value, str) or value != value.strip()):
                    raise ValueError("dispatch identifiers must be exact")
            thread_id = bounded_adapter_id(thread_id, field="dispatch thread id")
            client_user_message_id = bounded_adapter_id(
                client_user_message_id, field="dispatch client message id"
            )
            if expected_turn_id is not None:
                expected_turn_id = bounded_adapter_id(
                    expected_turn_id, field="dispatch expected turn id"
                )
            if (
                thread_id != self.thread_id
                or not isinstance(text, str)
                or not text.strip()
                or "\x00" in text
                or len(text) > MAX_DISPATCH_TEXT_BYTES
                or len(text.encode("utf-8")) > MAX_DISPATCH_TEXT_BYTES
                or type(expected_received_revision) is not int
                or expected_received_revision < 0
                or not isinstance(expected_connection_token, tuple)
                or len(expected_connection_token) != 2
                or not isinstance(expected_connection_token[0], str)
                or type(expected_connection_token[1]) is not int
                or not callable(final_authority_check)
            ):
                raise ValueError("invalid dispatch inputs")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise SharedCodexTextDispatchRejected("invalid text dispatch binding") from exc

        method = "turn/start" if expected_turn_id is None else "turn/steer"
        params: dict[str, Any] = {
            "threadId": thread_id,
            "clientUserMessageId": client_user_message_id,
            "input": [{"type": "text", "text": text, "text_elements": []}],
        }
        if expected_turn_id is not None:
            params["expectedTurnId"] = expected_turn_id
        attempted = False
        future: asyncio.Future[dict[str, Any]] | None = None
        request_id: int | None = None

        def require_current() -> None:
            if (
                not self.initialized
                or self._closing
                or self.connection_token() != expected_connection_token
                or self.received_envelope_revision != expected_received_revision
                or self._channel is None
                or self._websocket is None
                or self._websocket.state is not State.OPEN
            ):
                raise SharedCodexTextDispatchRejected("text dispatch authority is stale")

        try:
            async with asyncio.timeout(self.request_timeout_s):
                async with self._text_dispatch_lock:
                    async with self._protocol_lock:
                        require_current()
                        if len(self._pending) >= MAX_PENDING:
                            raise SharedCodexTextDispatchRejected("dispatch pending bound reached")
                        request_id = self._next_id
                        self._next_id += 1
                        encoded = strict_json_dumps(
                            {"id": request_id, "method": method, "params": params},
                            separators=(",", ":"),
                        ).encode("utf-8")
                        if len(encoded) > MAX_MESSAGE_BYTES:
                            raise SharedCodexTextDispatchRejected("dispatch write bound reached")
                        try:
                            checked = final_authority_check()
                            if inspect.isawaitable(checked):
                                if inspect.iscoroutine(checked):
                                    checked.close()
                                raise ValueError("authority callback must be synchronous")
                            if checked is not None:
                                raise ValueError("authority callback must return None")
                        except Exception as exc:
                            raise SharedCodexTextDispatchRejected(
                                "text dispatch authority callback refused"
                            ) from exc
                        require_current()
                        channel, websocket = self._channel, self._websocket
                        assert channel is not None and websocket is not None
                        future = asyncio.get_running_loop().create_future()
                        self._pending[request_id] = future
                        self._text_pending.add(request_id)
                        # From enqueue onward a later flush may transmit bytes,
                        # even if this write raises or is cancelled.
                        attempted = True
                        websocket.send_text(encoded)
                        await self._flush(websocket, channel)
                    result = await future
                    if (
                        not self.initialized
                        or self.connection_token() != expected_connection_token
                        or self._channel is not channel
                    ):
                        raise SharedCodexProtocolError("dispatch acknowledgement lost its epoch")
                    if method == "turn/steer":
                        turn_id = bounded_adapter_id(result.get("turnId"), field="ack turn id")
                        if (
                            turn_id != result.get("turnId")
                            or turn_id != expected_turn_id
                            or set(result) != {"turnId"}
                        ):
                            raise SharedCodexProtocolError("steer acknowledgement mismatched")
                    else:
                        turn = result.get("turn")
                        if (
                            set(result) != {"turn"}
                            or not isinstance(turn, dict)
                            or turn.get("status") != "inProgress"
                        ):
                            raise SharedCodexProtocolError("start acknowledgement malformed")
                        turn_id = bounded_adapter_id(turn.get("id"), field="ack turn id")
                        if turn_id != turn.get("id") or (
                            "threadId" in turn and turn["threadId"] != thread_id
                        ):
                            raise SharedCodexProtocolError("start acknowledgement mismatched")
                    return SharedCodexTextAcknowledgement(
                        method=method,
                        thread_id=thread_id,
                        turn_id=turn_id,
                        client_user_message_id=client_user_message_id,
                        connection_token=expected_connection_token,
                        received_revision_at_write=expected_received_revision,
                        received_revision_at_ack=self.received_envelope_revision,
                    )
        except SharedCodexRemoteError as exc:
            # JSON-RPC failure (especially internal error) does not establish
            # that the vendor had not already accepted/enqueued worker input.
            await self._settle_text_dispatch_close()
            raise SharedCodexTextDispatchRemoteError(code=exc.code) from exc
        except asyncio.CancelledError as exc:
            if attempted:
                await self._settle_text_dispatch_close()
                raise SharedCodexTextDispatchCancelled(
                    "text dispatch cancelled after enqueue; delivery unknown"
                ) from exc
            raise
        except BaseException as exc:
            if attempted:
                await self._settle_text_dispatch_close()
                raise SharedCodexDeliveryUncertainError(
                    "text dispatch attempted without a verified acknowledgement"
                ) from exc
            if isinstance(exc, SharedCodexTextDispatchRejected):
                raise
            raise SharedCodexTextDispatchRejected("text dispatch refused before enqueue") from exc
        finally:
            if request_id is not None:
                self._pending.pop(request_id, None)
                self._text_pending.discard(request_id)
            if future is not None and future.done() and not future.cancelled():
                future.exception()

    def _validated_read_params(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "thread/read":
            if set(params) - {"threadId", "includeTurns"}:
                raise PermissionError("shared Codex read parameters contain overrides")
            if params.get("threadId") != self.thread_id:
                raise PermissionError("shared Codex read targets the wrong thread")
            include_turns = params.get("includeTurns", False)
            if not isinstance(include_turns, bool):
                raise ValueError("includeTurns must be boolean")
            return {"threadId": self.thread_id, "includeTurns": include_turns}
        if method in {"thread/resume", "thread/unsubscribe"}:
            if params != {"threadId": self.thread_id}:
                raise PermissionError("shared Codex subscription parameters must bind exactly")
            return {"threadId": self.thread_id}
        raise PermissionError("shared Codex observe-only transport rejected a worker mutation")

    async def request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        method = bounded_adapter_id(method, field="shared Codex method")
        if method == "initialize":
            raise PermissionError("shared Codex initialization is transport-owned")
        if params is not None and not isinstance(params, dict):
            raise ValueError("shared Codex params must be an object")
        clean_params = self._validated_read_params(method, params or {})
        await self.ensure_ready()
        return await self._request_unchecked(method, clean_params)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        del method, params
        raise PermissionError("shared Codex observe-only transport rejects notifications")

    async def respond_approval(self, request_id: str, decision: str) -> None:
        del request_id, decision
        raise PermissionError("shared Codex observe-only transport rejects approval responses")

    async def close(self) -> None:
        self._close_revision += 1
        self._closing = True
        closing = self._close_task
        if closing is None or closing.done():
            reader = self._reader_task
            self._reader_task = None
            channel = self._channel
            self._channel = None
            self._websocket = None
            if reader is asyncio.current_task():
                reader = None

            async def finish_close() -> None:
                if reader is not None:
                    # If the reader already detached the channel on EOF/error,
                    # it owns cleanup. Join it instead of cancelling that cleanup.
                    if channel is not None:
                        reader.cancel()
                    await asyncio.gather(reader, return_exceptions=True)
                if channel is not None:
                    await self._close_channel(channel)

            closing = asyncio.create_task(finish_close())
            self._close_task = closing
        # Revocation precedes the first await, including concurrent close calls.
        self._invalidate(ConnectionError("shared Codex transport closed"))
        self.notifications.clear()
        cancelled: asyncio.CancelledError | None = None
        while not closing.done():
            try:
                await asyncio.shield(closing)
            except asyncio.CancelledError as exc:
                cancelled = exc
            except BaseException:
                break
        if cancelled is not None:
            if not closing.cancelled():
                closing.exception()
            raise cancelled
        closing.result()


def _validated_jsonrpc_id(value: object) -> int | str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return bounded_adapter_id(value, field="shared Codex JSON-RPC id")
        except ValueError:
            return None
    return None
