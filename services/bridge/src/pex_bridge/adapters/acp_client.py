"""Agent Client Protocol (JSON-RPC over a transport).

Used for Cursor CLI `agent acp`. Transports are injectable so tests never spawn
the real binary. On this machine the PATH `agent` command is Grok's binary, not
Cursor — callers must pass an explicit Cursor agent path.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pex_bridge.adapters.base import (
    DeliveryUncertainError,
    bounded_adapter_id,
    bounded_adapter_text,
    bounded_observed_mapping,
    bounded_observed_text,
)
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads

MAX_ACP_LINE_BYTES = 1_048_576
MAX_ACP_WRITE_BYTES = 1_048_576
MAX_ACP_EVENTS = 1_024
MAX_ACP_PENDING = 1_024
MAX_ACP_SESSIONS = 1_024
MAX_ACP_SESSION_PAGE = 256
MAX_ACP_SESSION_PAGES = 100
ACP_REQUEST_TIMEOUT_SECONDS = 30.0
ACP_PROMPT_TIMEOUT_SECONDS = 3_600.0
ACP_WRITE_TIMEOUT_SECONDS = 10.0
_ACP_MUTATING_METHODS = {
    "authenticate",
    "session/cancel",
    "session/load",
    "session/new",
    "session/prompt",
    "session/resume",
}


@dataclass(slots=True)
class AcpPermissionResponse:
    """One server-request result plus proof that it reached the stdio pipe."""

    result: dict[str, Any]
    delivered: asyncio.Future[None]


PermissionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | AcpPermissionResponse]]


class AcpRpcError(RuntimeError):
    """Structured ACP JSON-RPC failure without leaking arbitrary error data."""

    def __init__(self, code: int | None, message: str, data: Any = None) -> None:
        self.code = code
        # Arbitrary server error data frequently contains prompts, paths, or
        # provider diagnostics. Retain only the bounded public message.
        self.data = None
        safe_message = bounded_observed_text(
            message,
            field="ACP error message",
            max_chars=4_096,
        )
        super().__init__(safe_message or "ACP request failed")


class _AcpMalformedResult(ValueError):
    """A response arrived, but it was not an authoritative ACP result object."""


class AcpTransport(Protocol):
    async def request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    async def close(self) -> None: ...


class FakeAcpTransport:
    """In-process ACP stand-in for tests and demos."""

    def __init__(self) -> None:
        self.prompts: list[dict[str, Any]] = []
        self.sessions: list[dict[str, Any]] = [
            {"sessionId": "cursor-acp-demo", "cwd": "C:/proj", "title": "demo"}
        ]
        self.closed = False
        self.initialized = False
        self.authed = False
        self.loaded: list[dict[str, Any]] = []
        self.permission_replies: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []
        self.on_permission: PermissionHandler | None = None

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if method == "initialize":
            self.initialized = True
            return {
                "protocolVersion": 1,
                "agentCapabilities": {
                    "loadSession": True,
                    "sessionCapabilities": {"list": {}, "resume": {}},
                },
                "authMethods": [],
            }
        if method == "authenticate":
            self.authed = True
            return {}
        if method == "session/list":
            return {"sessions": list(self.sessions), "nextCursor": None}
        if method == "session/load":
            self.loaded.append(dict(params))
            return {"sessionId": params.get("sessionId")}
        if method == "session/resume":
            self.loaded.append(dict(params))
            return {"sessionId": params.get("sessionId")}
        if method == "session/new":
            sid = "cursor-acp-new"
            self.sessions.append({"sessionId": sid, "cwd": params.get("cwd")})
            return {"sessionId": sid}
        if method == "session/prompt":
            self.prompts.append(params)
            return {"stopReason": "end_turn"}
        if method == "session/cancel":
            return {}
        raise KeyError(method)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class StdioAcpTransport:
    def __init__(self, command: list[str]) -> None:
        if not command or len(command) > 64:
            raise ValueError("ACP command is missing or exceeds the safety bound")
        self.command = [
            bounded_adapter_text(arg, field="ACP command argument", max_chars=8_192)
            for arg in command
        ]
        executable = Path(self.command[0])
        if not executable.is_absolute() or not executable.is_file():
            raise ValueError("ACP executable must be an existing absolute file")
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._start_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._stderr_tail: deque[str] = deque(maxlen=100)
        self.on_permission: PermissionHandler | None = None
        self.events: deque[dict[str, Any]] = deque(maxlen=MAX_ACP_EVENTS)
        self._event_cursor = 0

    async def start(self) -> None:
        async with self._start_lock:
            if self._proc is not None:
                return
            self._proc = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_minimal_subprocess_env(),
                limit=MAX_ACP_LINE_BYTES,
            )
            self._reader_task = asyncio.create_task(self._read_loop(), name="acp-stdout")
            self._stderr_task = asyncio.create_task(self._drain_stderr(), name="acp-stderr")

    def _fail_pending(self, error: BaseException) -> None:
        pending = list(self._pending.values())
        self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(error)

    async def _drain_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                return
            # Drain to avoid deadlock, but never retain provider stderr, which
            # may contain paths, prompts, or credentials.
            self._stderr_tail.append("<redacted stderr line>")

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = strict_json_loads(line.decode("utf-8"))
                except (UnicodeDecodeError, ValueError, RecursionError):
                    continue
                if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                    continue
                if "id" in msg and ("result" in msg or "error" in msg):
                    request_id = msg["id"]
                    if isinstance(request_id, bool) or not isinstance(request_id, int):
                        continue
                    fut = self._pending.pop(request_id, None)
                    if fut and not fut.done():
                        if "error" in msg:
                            error = msg["error"]
                            if isinstance(error, dict):
                                raw_code = error.get("code")
                                code = raw_code if isinstance(raw_code, int) else None
                                message = bounded_observed_text(
                                    error.get("message"),
                                    field="ACP error message",
                                    max_chars=4_096,
                                ) or "ACP request failed"
                                fut.set_exception(AcpRpcError(code, message, error.get("data")))
                            else:
                                fut.set_exception(AcpRpcError(None, "ACP request failed"))
                        else:
                            result = msg.get("result")
                            if isinstance(result, dict):
                                fut.set_result(result)
                            else:
                                fut.set_exception(
                                    _AcpMalformedResult(
                                        "ACP server returned a malformed result"
                                    )
                                )
                    continue
                if msg.get("method") == "session/request_permission" and "id" in msg:
                    request_id = _validated_acp_rpc_id(msg.get("id"))
                    params = bounded_observed_mapping(msg.get("params"))
                    if request_id is None or params is None:
                        continue
                    decision = {"outcome": {"outcome": "cancelled"}}
                    delivery: asyncio.Future[None] | None = None
                    valid = True
                    if self.on_permission:
                        try:
                            proposed = await self.on_permission(params)
                            if isinstance(proposed, AcpPermissionResponse):
                                decision = proposed.result
                                delivery = proposed.delivered
                            elif isinstance(proposed, dict):
                                decision = proposed
                        except Exception:
                            # Permission mediation is fail-closed. The ACP turn is
                            # allowed to continue with an explicit cancellation.
                            decision = {"outcome": {"outcome": "cancelled"}}
                    outcome = decision.get("outcome") if isinstance(decision, dict) else None
                    if not isinstance(outcome, dict) or outcome.get("outcome") not in {
                        "cancelled",
                        "selected",
                    }:
                        valid = False
                        decision = {"outcome": {"outcome": "cancelled"}}
                    elif (
                        outcome.get("outcome") == "selected"
                        and not _valid_acp_option_id(outcome.get("optionId"))
                    ):
                        valid = False
                        decision = {"outcome": {"outcome": "cancelled"}}
                    try:
                        await self._write(
                            {"jsonrpc": "2.0", "id": request_id, "result": decision}
                        )
                    except BaseException as exc:
                        if delivery is not None and not delivery.done():
                            delivery.set_exception(exc)
                        raise
                    else:
                        if delivery is not None and not delivery.done():
                            if valid:
                                delivery.set_result(None)
                            else:
                                delivery.set_exception(
                                    RuntimeError("invalid ACP permission response was cancelled")
                                )
                    continue
                method = msg.get("method")
                params = bounded_observed_mapping(msg.get("params"))
                if isinstance(method, str) and params is not None:
                    try:
                        method = bounded_adapter_id(method, field="ACP event method")
                    except ValueError:
                        continue
                    self.events.append(
                        {"jsonrpc": "2.0", "method": method, "params": params}
                    )
                    self._event_cursor += 1
        finally:
            self._fail_pending(RuntimeError("ACP process closed its stdout"))

    async def _write(self, payload: dict[str, Any]) -> None:
        if self._proc is None:
            await self.start()
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("ACP process stdin is unavailable")
        encoded = (strict_json_dumps(payload, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        if len(encoded) > MAX_ACP_WRITE_BYTES:
            raise ValueError("ACP request exceeded the write safety bound")
        async with self._write_lock:
            self._proc.stdin.write(encoded)
            await self._proc.stdin.drain()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request(method, params)

    async def request_with_delivery(
        self,
        method: str,
        params: dict[str, Any] | None,
        delivered: asyncio.Future[None],
    ) -> dict[str, Any]:
        return await self._request(method, params, delivered=delivered)

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        delivered: asyncio.Future[None] | None = None,
    ) -> dict[str, Any]:
        method = bounded_adapter_id(method, field="ACP method")
        if len(self._pending) >= MAX_ACP_PENDING:
            raise RuntimeError("ACP pending request safety bound reached")
        req_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        write_started = False
        try:
            write_started = True
            await asyncio.wait_for(
                self._write(
                    {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
                ),
                timeout=ACP_WRITE_TIMEOUT_SECONDS,
            )
            if delivered is not None and not delivered.done():
                delivered.set_result(None)
            # A prompt request remains open for the complete agent turn. A fixed
            # 30-second timeout corrupts legitimate long turns and loses the only
            # authoritative ACP stopReason.
            timeout = (
                ACP_PROMPT_TIMEOUT_SECONDS
                if method == "session/prompt"
                else ACP_REQUEST_TIMEOUT_SECONDS
            )
            return await asyncio.wait_for(fut, timeout=timeout)
        except AcpRpcError:
            raise
        except asyncio.CancelledError:
            raise
        except _AcpMalformedResult as exc:
            if write_started and method in _ACP_MUTATING_METHODS:
                uncertain = DeliveryUncertainError(
                    "ACP mutation returned no authoritative result object"
                )
                if delivered is not None and not delivered.done():
                    delivered.set_exception(uncertain)
                raise uncertain from exc
            if delivered is not None and not delivered.done():
                delivered.set_exception(exc)
            raise
        except (TypeError, ValueError) as exc:
            if delivered is not None and not delivered.done():
                delivered.set_exception(exc)
            raise
        except BaseException as exc:
            if write_started and method in _ACP_MUTATING_METHODS:
                uncertain = DeliveryUncertainError(
                    "ACP mutation write began but no authoritative result was verified"
                )
                if delivered is not None and not delivered.done():
                    delivered.set_exception(uncertain)
                raise uncertain from exc
            if delivered is not None and not delivered.done():
                delivered.set_exception(exc)
            raise
        finally:
            self._pending.pop(req_id, None)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        method = bounded_adapter_id(method, field="ACP method")
        await asyncio.wait_for(
            self._write({"jsonrpc": "2.0", "method": method, "params": params or {}}),
            timeout=ACP_WRITE_TIMEOUT_SECONDS,
        )

    def events_since(self, cursor: int) -> tuple[int, list[dict[str, Any]], int]:
        if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
            raise ValueError("ACP event cursor must be a non-negative integer")
        latest = self._event_cursor
        if cursor >= latest:
            return latest, [], 0
        earliest = latest - len(self.events)
        dropped = max(0, earliest - cursor)
        start = max(cursor, earliest) - earliest
        return latest, list(self.events)[start:], dropped

    async def close(self) -> None:
        tasks = [task for task in (self._reader_task, self._stderr_task) if task]
        for task in tasks:
            task.cancel()
        proc = self._proc
        self._proc = None
        if proc is not None and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._reader_task = None
        self._stderr_task = None
        self._fail_pending(RuntimeError("ACP transport closed"))


class AcpClient:
    def __init__(self, transport: AcpTransport) -> None:
        self.transport = transport
        self.ready = False
        self.initialize_result: dict[str, Any] = {}
        self.agent_capabilities: dict[str, Any] = {}
        self.auth_methods: dict[str, dict[str, Any]] = {}
        self.active_sessions: set[str] = set()

    async def handshake(self) -> dict[str, Any]:
        if self.ready:
            return dict(self.initialize_result)
        init = await self.transport.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {
                    "fs": {"readTextFile": False, "writeTextFile": False},
                    "terminal": False,
                    "auth": {"terminal": False},
                },
                "clientInfo": {"name": "pex", "title": "PEX", "version": "0.1.0"},
            },
        )
        if not isinstance(init, dict):
            raise RuntimeError("ACP initialize returned a non-object result")
        if init.get("protocolVersion") != 1:
            raise RuntimeError("ACP agent negotiated an unsupported protocol version")
        self.initialize_result = init
        capabilities = init.get("agentCapabilities")
        self.agent_capabilities = capabilities if isinstance(capabilities, dict) else {}
        advertised_auth = init.get("authMethods", [])
        if not isinstance(advertised_auth, list):
            raise RuntimeError("ACP initialize returned malformed authMethods")
        if len(advertised_auth) > 64:
            raise RuntimeError("ACP initialize advertised too many auth methods")
        auth_methods: dict[str, dict[str, Any]] = {}
        for item in advertised_auth:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            method_id = bounded_adapter_id(item["id"], field="ACP auth method id")
            method_type = bounded_adapter_id(
                item.get("type") or "agent", field="ACP auth method type"
            )
            auth_methods[method_id] = {"id": method_id, "type": method_type}
        self.auth_methods = auth_methods
        # A passive probe must not trigger browser login, read a cached token, or
        # submit an API key. Authentication is an explicit caller action.
        self.ready = True
        return init

    async def authenticate(
        self, method_id: str, *, metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self.ready:
            await self.handshake()
        if method_id not in self.auth_methods:
            raise ValueError(f"ACP auth method is not advertised: {method_id}")
        method_type = str(self.auth_methods[method_id].get("type") or "agent")
        if method_type != "agent":
            raise ValueError(
                "ACP terminal or extension authentication cannot use the authenticate method"
            )
        params: dict[str, Any] = {"methodId": method_id}
        if metadata:
            params["_meta"] = dict(metadata)
        return await self.transport.request("authenticate", params)

    def supports_session_capability(self, capability: str) -> bool:
        session_caps = self.agent_capabilities.get("sessionCapabilities")
        return isinstance(session_caps, dict) and capability in session_caps

    @property
    def supports_load_session(self) -> bool:
        return self.agent_capabilities.get("loadSession") is True

    async def list_sessions(self) -> list[dict[str, Any]]:
        if not self.ready:
            await self.handshake()
        if not self.supports_session_capability("list"):
            raise RuntimeError("ACP agent does not advertise session/list")
        sessions: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(MAX_ACP_SESSION_PAGES):
            params = {"cursor": cursor} if cursor else {}
            result = await self.transport.request("session/list", params)
            if not isinstance(result, dict) or not isinstance(result.get("sessions"), list):
                raise RuntimeError("ACP session/list returned a malformed page")
            page = result["sessions"]
            if len(page) > MAX_ACP_SESSION_PAGE:
                raise RuntimeError("ACP session/list page exceeded the safety bound")
            for item in page:
                if not isinstance(item, dict):
                    continue
                session_id = bounded_adapter_id(
                    item.get("sessionId") or "", field="ACP session id"
                )
                record: dict[str, Any] = {"sessionId": session_id}
                for field, limit in (("cwd", 4_096), ("title", 4_096)):
                    value = item.get(field)
                    if value not in (None, ""):
                        if field == "title":
                            cleaned = bounded_observed_text(
                                value,
                                field="ACP session title",
                                max_chars=limit,
                            )
                            if cleaned is not None:
                                record[field] = cleaned
                        else:
                            record[field] = bounded_adapter_text(
                                value,
                                field="ACP session cwd",
                                max_chars=limit,
                            )
                sessions.append(record)
            if len(sessions) > MAX_ACP_SESSIONS:
                raise RuntimeError("ACP session/list exceeded the safety bound")
            next_cursor = result.get("nextCursor")
            if next_cursor is None or next_cursor == "":
                return sessions
            if not isinstance(next_cursor, str):
                raise RuntimeError("ACP session/list returned a malformed cursor")
            if next_cursor == cursor or next_cursor in seen_cursors:
                raise RuntimeError("ACP session/list pagination repeated a cursor")
            cursor = bounded_adapter_id(next_cursor, field="ACP pagination cursor")
            seen_cursors.add(cursor)
        raise RuntimeError("ACP session/list exceeded the pagination safety bound")

    @staticmethod
    def _session_setup_params(session_id: str, cwd: str) -> dict[str, Any]:
        session_id = bounded_adapter_id(session_id, field="ACP session id")
        cleaned = bounded_adapter_text(cwd, field="ACP cwd", max_chars=4_096).strip()
        if not cleaned or not Path(cleaned).is_absolute():
            raise ValueError("ACP session setup requires an absolute cwd")
        return {"sessionId": session_id, "cwd": cleaned, "mcpServers": []}

    async def load(self, session_id: str, cwd: str) -> dict[str, Any]:
        if not self.ready:
            await self.handshake()
        if not self.supports_load_session:
            raise RuntimeError("ACP agent does not advertise session/load")
        if len(self.active_sessions) >= MAX_ACP_SESSIONS and session_id not in self.active_sessions:
            raise RuntimeError("ACP active session safety bound reached")
        result = await self.transport.request(
            "session/load", self._session_setup_params(session_id, cwd)
        )
        self.active_sessions.add(session_id)
        return result

    async def resume(self, session_id: str, cwd: str) -> dict[str, Any]:
        if not self.ready:
            await self.handshake()
        if not self.supports_session_capability("resume"):
            raise RuntimeError("ACP agent does not advertise session/resume")
        if len(self.active_sessions) >= MAX_ACP_SESSIONS and session_id not in self.active_sessions:
            raise RuntimeError("ACP active session safety bound reached")
        result = await self.transport.request(
            "session/resume", self._session_setup_params(session_id, cwd)
        )
        self.active_sessions.add(session_id)
        return result

    async def activate(self, session_id: str, cwd: str) -> dict[str, Any]:
        if session_id in self.active_sessions:
            return {"sessionId": session_id}
        if not self.ready:
            await self.handshake()
        if self.supports_load_session:
            return await self.load(session_id, cwd)
        if self.supports_session_capability("resume"):
            return await self.resume(session_id, cwd)
        raise RuntimeError("ACP agent cannot attach to an existing session")

    async def prompt(
        self,
        session_id: str,
        text: str,
        *,
        delivered: asyncio.Future[None] | None = None,
    ) -> dict[str, Any]:
        if not self.ready:
            await self.handshake()
        if session_id not in self.active_sessions:
            raise RuntimeError("ACP session must be loaded or resumed before prompting")
        session_id = bounded_adapter_id(session_id, field="ACP session id")
        cleaned = bounded_adapter_text(text, field="ACP prompt text").strip()
        params = {"sessionId": session_id, "prompt": [{"type": "text", "text": cleaned}]}
        request_with_delivery = getattr(self.transport, "request_with_delivery", None)
        if delivered is not None and callable(request_with_delivery):
            return await request_with_delivery("session/prompt", params, delivered)
        result = await self.transport.request("session/prompt", params)
        if delivered is not None and not delivered.done():
            delivered.set_result(None)
        return result

    async def cancel(self, session_id: str) -> None:
        if session_id not in self.active_sessions:
            return
        await self.transport.request("session/cancel", {"sessionId": session_id})


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
        "PROGRAMDATA",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TERM",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def _validated_acp_rpc_id(value: object) -> int | str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return bounded_adapter_id(value, field="ACP JSON-RPC id")
        except ValueError:
            return None
    return None


def _valid_acp_option_id(value: object) -> bool:
    try:
        bounded_adapter_id(value, field="ACP permission option id")
    except ValueError:
        return False
    return True
