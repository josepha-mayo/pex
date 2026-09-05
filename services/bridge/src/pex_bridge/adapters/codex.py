"""OpenAI Codex App Server JSON-RPC.

Wire format is newline-delimited JSON with the `"jsonrpc":"2.0"` header omitted.
Deep only after a live or injected transport completes `initialize` + `initialized`.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import subprocess
import sys
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pex_protocol.capabilities import (
    AdapterCapabilities,
    AdapterSupportLabel,
    ControlGranularity,
    PermissionResponseMode,
)
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import (
    MAX_ADAPTER_MESSAGE_CHARS,
    AdapterMessageResult,
    DeliveryUncertainError,
    HarnessAdapter,
    bounded_adapter_id,
    bounded_adapter_text,
    bounded_observed_mapping,
    bounded_observed_text,
    preserve_bridge_state,
    session_binding_matches,
)
from pex_bridge.adapters.codex_bin import app_server_command
from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads
from pex_bridge.shell_state import parse_pytest_process_state

CLIENT_INFO = {"name": "pex", "title": "PEX", "version": "0.1.0"}
INIT_PARAMS = {"clientInfo": CLIENT_INFO, "capabilities": {}}
MAX_CODEX_LINE_BYTES = 1_048_576
MAX_CODEX_WRITE_BYTES = 1_048_576
MAX_CODEX_RECORDS = 1_024
MAX_CODEX_PENDING = 1_024
MAX_CODEX_NOTIFICATIONS_PER_PASS = 256
MAX_CODEX_SESSIONS = 10_000
MAX_INBOX_MESSAGES = 1_000
MAX_PATH_CHARS = 4_096


class _CodexRemoteError(RuntimeError):
    """The App Server explicitly rejected a JSON-RPC request."""


def chatgpt_desktop_running() -> bool:
    from pex_bridge.adapters.desktop import desktop_process_running

    return desktop_process_running("ChatGPT.exe")


def is_chatgpt_observe_session(session: HarnessSession | None) -> bool:
    if session is None:
        return False
    return (
        session.id == "codex:desktop"
        or session.vendor_session_id == "desktop"
        or (session.metadata or {}).get("source") == "desktop"
        or (session.metadata or {}).get("process") == "ChatGPT.exe"
    )


COMMAND_APPROVALS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
}
LEGACY_APPROVALS = {"execCommandApproval", "applyPatchApproval"}
PERMISSION_APPROVAL = "item/permissions/requestApproval"
APPROVAL_METHODS = COMMAND_APPROVALS | LEGACY_APPROVALS | {PERMISSION_APPROVAL}


class CodexTransport(Protocol):
    initialized: bool
    connection_generation: int

    async def ensure_ready(self) -> dict[str, Any]: ...

    async def request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    async def respond_approval(self, request_id: str, decision: str) -> None: ...

    async def close(self) -> None: ...


def approval_result(
    method: str, decision: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Map PEX allow/deny onto Codex v2 (and legacy) approval payloads."""
    token = decision.lower().replace("-", "_").replace(" ", "_")
    session = token in {
        "allow_session",
        "accept_for_session",
        "acceptforsession",
        "approved_for_session",
    }
    accept = session or token in {"allow", "accept", "approve", "approved", "yes"}
    cancel = token in {"cancel", "abort"}
    if method in COMMAND_APPROVALS:
        if session:
            return {"decision": "acceptForSession"}
        if accept:
            return {"decision": "accept"}
        if cancel:
            return {"decision": "cancel"}
        return {"decision": "decline"}
    if method in LEGACY_APPROVALS:
        if session:
            return {"decision": "approved_for_session"}
        if accept:
            return {"decision": "approved"}
        if cancel:
            return {"decision": "abort"}
        return {"decision": {"denied": {"rejection": "pex"}}}
    if method == PERMISSION_APPROVAL:
        if accept:
            return {
                "permissions": (params or {}).get("permissions") or {},
                "scope": "session" if session else "turn",
            }
        return {"denied": True}
    if session:
        return {"decision": "acceptForSession"}
    if accept:
        return {"decision": "accept"}
    return {"decision": "decline"}


def _thread_rows(listed: dict[str, Any]) -> list[dict[str, Any]]:
    rows = listed.get("data")
    if isinstance(rows, list):
        return [row for row in rows[:MAX_CODEX_SESSIONS] if isinstance(row, dict)]
    rows = listed.get("threads")
    if isinstance(rows, list):
        return [row for row in rows[:MAX_CODEX_SESSIONS] if isinstance(row, dict)]
    return []


class CodexAppServerTransport:
    """In-process App Server stand-in. Not a live `codex` process."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.raw_capture: list[dict[str, Any]] = []
        self.approvals: list[dict[str, Any]] = []
        self.threads: list[dict[str, Any]] = [
            {"id": "thr_demo", "preview": "synthetic thread", "cwd": "C:/fake"}
        ]
        self.initialized = False
        self.connection_generation = 0
        self.pending_approvals: dict[str, dict[str, Any]] = {}

    def _append_notification(self, message: dict[str, Any]) -> None:
        if len(self.notifications) >= MAX_CODEX_RECORDS:
            raise RuntimeError("Codex notification retention safety bound reached")
        self.notifications.append(message)
        if len(self.raw_capture) < MAX_CODEX_RECORDS:
            self.raw_capture.append(dict(message))

    async def ensure_ready(self) -> dict[str, Any]:
        if self.initialized:
            return {"serverInfo": {"name": "codex-app-server-fake"}}
        return await self.request("initialize", INIT_PARAMS)

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if method != "initialize" and not self.initialized:
            raise RuntimeError("Not initialized")
        if method == "initialize":
            if self.initialized:
                raise RuntimeError("Already initialized")
            self.initialized = True
            self.connection_generation += 1
            return {
                "userAgent": "pex-fake",
                "codexHome": "/",
                "platformFamily": "test",
                "platformOs": "test",
                "serverInfo": {"name": "codex-app-server-fake"},
            }
        if method == "thread/list":
            return {"data": list(self.threads), "threads": list(self.threads)}
        if method == "thread/start":
            thread = {
                "id": f"thr_new_{len(self.threads)}",
                "cwd": params.get("cwd"),
                "name": params.get("name"),
            }
            self.threads.append(thread)
            return {"thread": thread}
        if method == "thread/resume":
            thread_id = params.get("threadId")
            thread = next((row for row in self.threads if row.get("id") == thread_id), None)
            if thread is None:
                raise KeyError(thread_id)
            resumed = dict(thread)
            return {
                "thread": resumed,
                "cwd": resumed.get("cwd"),
                "model": "test-model",
                "modelProvider": "test-provider",
            }
        if method == "turn/start":
            self.turns.append(params)
            turn = {"id": f"turn_{len(self.turns)}", "status": "completed", "items": []}
            self._append_notification(
                {
                    "method": "turn/completed",
                    "params": {"threadId": params.get("threadId"), "turn": turn},
                }
            )
            return {"turn": turn}
        raise KeyError(method)

    async def respond_approval(self, request_id: str, decision: str) -> None:
        pending = self.pending_approvals.get(str(request_id), {})
        method = str(pending.get("method") or "item/commandExecution/requestApproval")
        self.approvals.append(
            {
                "request_id": request_id,
                "decision": decision,
                "result": approval_result(method, decision, pending.get("params") or {}),
            }
        )
        self.pending_approvals.pop(str(request_id), None)

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        return None

    async def close(self) -> None:
        self.initialized = False


class CodexStdioTransport:
    """Live `codex app-server --listen stdio://` child process."""

    def __init__(self, command: str | list[str]) -> None:
        if isinstance(command, str):
            self.command = app_server_command(command)
        else:
            self.command = list(command)
        if not self.command or len(self.command) > 64:
            raise ValueError("Codex app-server command exceeds the safety bound")
        self.command = [
            bounded_adapter_text(arg, field="Codex command argument", max_chars=8_192)
            for arg in self.command
        ]
        executable = Path(self.command[0])
        if not executable.is_absolute() or not executable.is_file():
            raise ValueError("Codex app-server executable must be an existing absolute file")
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[Any, asyncio.Future] = {}
        self._next_id = 1
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self.initialized = False
        self.connection_generation = 0
        self.pending_approvals: dict[str, dict[str, Any]] = {}
        self.notifications: list[dict[str, Any]] = []
        self.raw_capture: list[dict[str, Any]] = []
        self.stderr_tail: list[str] = []
        self.init_result: dict[str, Any] | None = None
        self.approvals: list[dict[str, Any]] = []
        self.turns: list[dict[str, Any]] = []
        self._start_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._initialize_lock = asyncio.Lock()

    def _append_notification(self, message: dict[str, Any]) -> None:
        if len(self.notifications) >= MAX_CODEX_RECORDS:
            raise RuntimeError("Codex notification retention safety bound reached")
        self.notifications.append(message)
        if len(self.raw_capture) < MAX_CODEX_RECORDS:
            self.raw_capture.append(dict(message))

    async def start(self) -> None:
        if self._proc is not None:
            return
        async with self._start_lock:
            if self._proc is not None:
                return
            kwargs: dict[str, Any] = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            self._proc = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_minimal_subprocess_env(),
                limit=MAX_CODEX_LINE_BYTES,
                **kwargs,
            )
            self.connection_generation += 1
            self._reader_task = asyncio.create_task(self._read_loop())
            self._stderr_task = asyncio.create_task(self._stderr_loop())

    async def _stderr_loop(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break
            # Drain without retaining provider diagnostics, which can contain
            # prompts, workspace paths, or credentials.
            self.stderr_tail.append("<redacted stderr line>")
            self.stderr_tail = self.stderr_tail[-30:]

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
                if not isinstance(msg, dict):
                    continue
                raw_id = msg.get("id")
                msg_id = _validated_jsonrpc_id(raw_id)
                if raw_id is not None and msg_id is None:
                    continue
                if msg_id is not None and ("result" in msg or "error" in msg):
                    fut = self._pending.pop(msg_id, None)
                    if fut and not fut.done():
                        if "error" in msg:
                            fut.set_exception(_CodexRemoteError("codex app-server request failed"))
                        else:
                            result = msg.get("result")
                            if isinstance(result, dict):
                                fut.set_result(result)
                            else:
                                fut.set_exception(
                                    ValueError("Codex app-server returned a malformed result")
                                )
                    continue
                raw_method = msg.get("method")
                if raw_method is None:
                    continue
                try:
                    method = bounded_adapter_id(raw_method, field="Codex app-server event method")
                except ValueError:
                    continue
                params = bounded_observed_mapping(msg.get("params"))
                if params is None:
                    continue
                if method in APPROVAL_METHODS and msg_id is not None:
                    if len(self.pending_approvals) >= MAX_CODEX_PENDING:
                        raise RuntimeError("Codex approval retention safety bound reached")
                    self.pending_approvals[str(msg_id)] = {
                        "id": msg_id,
                        "method": method,
                        "params": params,
                    }
                    continue
                # Official turn/item events are notifications. Some builds still attach
                # an `id`; only documented approval methods are requests.
                # Pump consumers delete `notifications`; raw_capture is append-only.
                self._append_notification({"method": method, "params": params})
        finally:
            self._fail_pending(RuntimeError("codex app-server stdout closed"))

    async def _write(self, payload: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        encoded = (strict_json_dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) > MAX_CODEX_WRITE_BYTES:
            raise ValueError("Codex app-server request exceeded the write safety bound")
        async with self._write_lock:
            self._proc.stdin.write(encoded)
            await self._proc.stdin.drain()

    async def ensure_ready(self) -> dict[str, Any]:
        if self.initialized and self.init_result is not None:
            return self.init_result
        async with self._initialize_lock:
            if self.initialized and self.init_result is not None:
                return self.init_result
            if self._proc is None:
                await self.start()
            result = await self.request("initialize", INIT_PARAMS)
            await self.notify("initialized", {})
            self.initialized = True
            self.init_result = result
            return result

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        method = bounded_adapter_id(method, field="Codex app-server method")
        if self._proc is None:
            await self.start()
        if len(self._pending) >= MAX_CODEX_PENDING:
            raise RuntimeError("Codex pending request safety bound reached")
        req_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        delivered = False
        try:
            await self._write({"id": req_id, "method": method, "params": params or {}})
            delivered = True
            result = await asyncio.wait_for(fut, timeout=45)
        except _CodexRemoteError:
            raise
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if delivered:
                raise DeliveryUncertainError(
                    "Codex request was written but its receipt was not verified"
                ) from exc
            raise
        finally:
            self._pending.pop(req_id, None)
        if method == "turn/start":
            self.turns.append(params or {})
        return result

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        method = bounded_adapter_id(method, field="Codex app-server method")
        if self._proc is None:
            await self.start()
        await self._write({"method": method, "params": params or {}})

    async def respond_approval(self, request_id: str, decision: str) -> None:
        request_id = bounded_adapter_id(request_id, field="Codex approval request id")
        pending = self.pending_approvals.get(str(request_id), {})
        method = str(pending.get("method") or "item/commandExecution/requestApproval")
        result = approval_result(method, decision, pending.get("params") or {})
        payload_id: Any = pending.get("id", request_id)
        try:
            payload_id = int(payload_id)
        except (TypeError, ValueError):
            payload_id = request_id
        try:
            if result.get("denied"):
                await self._write(
                    {"id": payload_id, "error": {"code": -32001, "message": "denied by PEX"}}
                )
            else:
                await self._write({"id": payload_id, "result": result})
        except Exception as exc:
            raise DeliveryUncertainError(
                "Codex approval response may have been partially written"
            ) from exc
        self.pending_approvals.pop(str(request_id), None)
        if len(self.approvals) >= MAX_CODEX_RECORDS:
            del self.approvals[: len(self.approvals) - MAX_CODEX_RECORDS + 1]
        self.approvals.append({"request_id": request_id, "decision": decision, "result": result})

    async def close(self) -> None:
        tasks = [task for task in (self._reader_task, self._stderr_task) if task is not None]
        for task in tasks:
            if task:
                task.cancel()
        self._reader_task = None
        self._stderr_task = None
        if self._proc:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
            except Exception:
                pass
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (TimeoutError, ProcessLookupError):
                pass
            self._proc = None
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._fail_pending(RuntimeError("codex app-server transport closed"))
        self.initialized = False
        self.init_result = None

    def _fail_pending(self, exc: BaseException) -> None:
        pending = list(self._pending.values())
        self._pending.clear()
        for future in pending:
            if not future.done():
                future.set_exception(exc)


class IsolatedThreadError(RuntimeError):
    """thread/start reused an existing Codex thread or never created one."""


class CodexAdapter(HarnessAdapter):
    """OpenAI Codex via App Server JSON-RPC. Prefer this over UI automation."""

    name = "codex"

    def __init__(self, transport: CodexTransport | None = None) -> None:
        self.transport = transport
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.isolated_approval_decisions: list[dict[str, Any]] = []
        self.isolated_agent_messages: list[str] = []
        self.isolated_item_types: list[str] = []
        self.last_turn_params: dict[str, Any] | None = None
        self.last_turn_id: str | None = None
        self.last_pump_error: str | None = None
        self._pump_task: asyncio.Task | None = None
        self._cwd_probed: set[str] = set()
        self._event_namespace = uuid4().hex[:12]
        self._notification_sequence = 0
        self._approval_sequence = 0
        self._completed_turns: dict[tuple[str, str], dict[str, Any]] = {}
        self._completed_turn_order: deque[tuple[str, str]] = deque()
        self._turn_completion_waiters: dict[tuple[str, str], asyncio.Event] = {}
        self._loaded_thread_bindings: dict[str, tuple[tuple[int, int], tuple[str, str, str]]] = {}
        # One bounded mutation lock avoids unbounded per-thread lock retention and
        # keeps resume + turn/start atomic with respect to transport replacement.
        self._delivery_lock = asyncio.Lock()

    def attach_transport(self, transport: CodexTransport) -> None:
        if self._delivery_lock.locked():
            raise RuntimeError("cannot replace Codex transport during a delivery")
        if (
            self.transport is not None
            and self.transport is not transport
            and self._pump_task is not None
            and not self._pump_task.done()
        ):
            raise RuntimeError("detach the active Codex transport before replacing it")
        self.transport = transport
        self._completed_turns.clear()
        self._completed_turn_order.clear()
        self._loaded_thread_bindings.clear()

    @staticmethod
    def _thread_load_binding(session: HarnessSession) -> tuple[str, str, str]:
        if not session.cwd or not session.project_id:
            raise ValueError("Codex thread loading requires project and workspace bindings")
        try:
            resolved_cwd = Path(session.cwd).resolve()
        except (OSError, RuntimeError, ValueError):
            raise ValueError("Codex thread workspace could not be resolved") from None
        return (
            session.id,
            session.project_id,
            os.path.normcase(str(resolved_cwd)),
        )

    @staticmethod
    def _transport_connection_token(transport: CodexTransport) -> tuple[int, int]:
        generation = getattr(transport, "connection_generation", None)
        if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
            raise RuntimeError("Codex transport has no initialized connection generation")
        return (id(transport), generation)

    async def _ensure_thread_loaded(
        self, session: HarnessSession
    ) -> tuple[HarnessSession, CodexTransport]:
        """Resume a discovered thread before the first mutation on this transport."""

        bound = self.sessions.get(session.id)
        if (
            not session_binding_matches(bound, session, harness_type=HarnessType.CODEX)
            or session.id != f"codex:{session.vendor_session_id}"
        ):
            raise ValueError("Codex thread resume requires an exact session binding")
        binding = self._thread_load_binding(bound)
        goal_binding = bound.goal_id
        if not await self._ready():
            raise RuntimeError("codex app-server is not attached")
        transport = self.transport
        assert transport is not None
        connection_token = self._transport_connection_token(transport)
        cache_value = (connection_token, binding)
        if self._loaded_thread_bindings.get(session.vendor_session_id) == cache_value:
            return bound, transport

        resumed = await transport.request(
            "thread/resume",
            {"threadId": session.vendor_session_id, "excludeTurns": True},
        )
        if not isinstance(resumed, dict) or not isinstance(resumed.get("thread"), dict):
            raise DeliveryUncertainError(
                "Codex thread/resume returned no authoritative thread receipt"
            )
        thread = resumed["thread"]
        try:
            resumed_id = bounded_adapter_id(thread.get("id") or "", field="resumed Codex thread id")
        except ValueError:
            raise DeliveryUncertainError(
                "Codex thread/resume returned a malformed thread receipt"
            ) from None
        if resumed_id != session.vendor_session_id:
            raise DeliveryUncertainError(
                "Codex thread/resume receipt did not match the requested thread"
            )

        expected_cwd = Path(bound.cwd).resolve()
        observed_cwds: list[Path] = []
        for raw_cwd in (resumed.get("cwd"), thread.get("cwd")):
            if not isinstance(raw_cwd, str) or not raw_cwd:
                raise DeliveryUncertainError(
                    "Codex thread/resume returned no authoritative workspace"
                )
            try:
                observed_cwd = Path(raw_cwd)
                if not observed_cwd.is_absolute():
                    raise DeliveryUncertainError("Codex thread/resume workspace was not absolute")
                observed_cwds.append(observed_cwd.resolve())
            except DeliveryUncertainError:
                raise
            except (OSError, RuntimeError, ValueError):
                raise DeliveryUncertainError(
                    "Codex thread/resume workspace could not be verified"
                ) from None
        if any(observed_cwd != expected_cwd for observed_cwd in observed_cwds):
            raise DeliveryUncertainError(
                "Codex thread/resume workspace did not match the session binding"
            )
        if thread.get("canAcceptDirectInput") is False:
            raise DeliveryUncertainError("Codex thread cannot accept direct input")

        raw_model = resumed.get("model")
        raw_provider = resumed.get("modelProvider")
        if not isinstance(raw_model, str) or not raw_model:
            raise DeliveryUncertainError("Codex thread/resume returned no authoritative model")
        if not isinstance(raw_provider, str) or not raw_provider:
            raise DeliveryUncertainError(
                "Codex thread/resume returned no authoritative model provider"
            )
        try:
            model = bounded_adapter_id(raw_model, field="resumed Codex model")
            model_provider = bounded_adapter_id(raw_provider, field="resumed Codex model provider")
        except ValueError:
            raise DeliveryUncertainError(
                "Codex thread/resume model receipt was malformed"
            ) from None

        current = self.sessions.get(session.id)
        if (
            self.transport is not transport
            or self._transport_connection_token(transport) != connection_token
            or not session_binding_matches(current, session, harness_type=HarnessType.CODEX)
            or current is None
            or self._thread_load_binding(current) != binding
            or current.goal_id != goal_binding
        ):
            raise DeliveryUncertainError(
                "Codex session or transport changed while the thread was resuming"
            )
        current.metadata["resumed_model"] = model
        current.metadata["resumed_model_provider"] = model_provider
        self._loaded_thread_bindings[session.vendor_session_id] = cache_value
        return current, transport

    def _notification_identity(self, message: dict[str, Any]) -> str:
        existing = message.get("_pex_notification_identity")
        prefix = f"{self._event_namespace}:notification:"
        if isinstance(existing, str) and existing.startswith(prefix):
            return existing
        self._notification_sequence += 1
        identity = f"{prefix}{self._notification_sequence}"
        message["_pex_notification_identity"] = identity
        return identity

    def _approval_identity(self, request: dict[str, Any]) -> str:
        existing = request.get("_pex_approval_identity")
        prefix = f"{self._event_namespace}:approval:"
        if isinstance(existing, str) and existing.startswith(prefix):
            return existing
        self._approval_sequence += 1
        identity = f"{prefix}{self._approval_sequence}"
        request["_pex_approval_identity"] = identity
        return identity

    @staticmethod
    def _request_fingerprint(request: dict[str, Any]) -> str:
        public = {
            key: value
            for key, value in request.items()
            if isinstance(key, str) and not key.startswith("_pex_")
        }
        try:
            encoded = strict_json_dumps(
                public,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
            encoded = type(request).__name__
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]

    def _item_identity(
        self,
        session: HarnessSession,
        params: dict[str, Any],
        item: dict[str, Any],
        notification_identity: str,
    ) -> tuple[str, str]:
        raw_item_id = item.get("id")
        if isinstance(raw_item_id, str) and raw_item_id:
            item_id = bounded_adapter_id(raw_item_id, field="Codex item id")
            return f"{session.id}:{item_id}", item_id
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        raw_turn_id = params.get("turnId") or params.get("turn_id") or turn.get("id")
        try:
            turn_id = (
                bounded_adapter_id(raw_turn_id, field="Codex turn id")
                if isinstance(raw_turn_id, str) and raw_turn_id
                else ""
            )
        except ValueError:
            turn_id = ""
        if turn_id:
            try:
                encoded = strict_json_dumps(
                    item,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            except (TypeError, ValueError):
                encoded = notification_identity
            digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]
            suffix = f"anonymous:{turn_id}:{digest}"
        else:
            suffix = "anonymous:" + notification_identity.replace(":", "-")
        return f"{session.id}:{suffix}", suffix

    @staticmethod
    def _vendor_turn_id(
        params: dict[str, Any],
        item: dict[str, Any] | None = None,
    ) -> str | None:
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        raw_candidates = [
            turn.get("id"),
            params.get("turnId"),
            params.get("turn_id"),
            (item or {}).get("turnId"),
            (item or {}).get("turn_id"),
        ]
        try:
            candidates = {
                bounded_adapter_id(raw, field="Codex turn id")
                for raw in raw_candidates
                if isinstance(raw, str) and raw
            }
        except ValueError:
            return None
        return next(iter(candidates)) if len(candidates) == 1 else None

    @staticmethod
    def _raw_event_ref(
        session: HarnessSession,
        *,
        turn_id: str | None,
        item_id: str | None = None,
    ) -> str | None:
        if turn_id is None:
            return None
        payload = {
            "schema": "pex.codex-event-ref.v1",
            "thread_id": session.vendor_session_id,
            "turn_id": turn_id,
        }
        if item_id is not None:
            payload["item_id"] = item_id
        return strict_json_dumps(payload, sort_keys=True, separators=(",", ":"))

    def _remember_turn_completion(
        self,
        session: HarnessSession,
        turn: dict[str, Any],
    ) -> None:
        raw_turn_id = turn.get("id")
        if not isinstance(raw_turn_id, str) or not raw_turn_id:
            return
        try:
            turn_id = bounded_adapter_id(raw_turn_id, field="Codex turn id")
        except ValueError:
            return
        key = (session.vendor_session_id, turn_id)
        if key not in self._completed_turns:
            self._completed_turn_order.append(key)
        self._completed_turns[key] = dict(turn)
        while len(self._completed_turn_order) > MAX_CODEX_RECORDS:
            expired = self._completed_turn_order.popleft()
            self._completed_turns.pop(expired, None)
        waiter = self._turn_completion_waiters.get(key)
        if waiter is not None:
            waiter.set()

    def _session_for(self, params: dict[str, Any] | None = None) -> HarnessSession | None:
        params = params or {}
        thread_id = str(params.get("threadId") or params.get("thread_id") or "")
        if not thread_id:
            turn = params.get("turn")
            if isinstance(turn, dict):
                thread_id = str(turn.get("threadId") or turn.get("thread_id") or "")
        if not thread_id:
            return None
        try:
            thread_id = bounded_adapter_id(thread_id, field="Codex thread id")
        except ValueError:
            return None
        if thread_id.casefold() in {"desktop", "unknown", "none"}:
            return None
        session_id = f"codex:{thread_id}"
        session = self.sessions.get(session_id)
        if is_chatgpt_observe_session(session):
            return None
        cwd = params.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            cwd = None
        if session is None:
            # Notifications do not establish project identity. Discovery or
            # thread/start must bind the thread before events are accepted.
            return None
        if cwd and session.cwd and Path(cwd).resolve() != Path(session.cwd).resolve():
            return None
        if not session.cwd and cwd:
            session.goal_id = None
            session.supervision_paused = False
            session.cwd = cwd
            session.project_id = cwd
        return session

    async def existing_thread_ids(self) -> set[str]:
        if not await self._ready():
            return set()
        assert self.transport is not None
        found: set[str] = set()
        cursor: str | None = None
        seen_cursors: set[str] = set()
        for _ in range(100):
            params: dict[str, Any] = {"limit": 100}
            if cursor:
                params["cursor"] = cursor
            listed = await self.transport.request("thread/list", params)
            for row in _thread_rows(listed):
                if row.get("id"):
                    found.add(bounded_adapter_id(row["id"], field="Codex thread id"))
            if len(found) > MAX_CODEX_SESSIONS:
                raise RuntimeError("Codex thread listing exceeded the safety bound")
            next_cursor = listed.get("nextCursor") or listed.get("next_cursor")
            if not next_cursor:
                return found
            cursor = bounded_adapter_id(next_cursor, field="Codex thread cursor")
            if cursor in seen_cursors:
                raise RuntimeError("Codex thread listing repeated a cursor")
            seen_cursors.add(cursor)
        raise RuntimeError("Codex thread listing exceeded the pagination safety bound")

    async def start_isolated_thread(
        self,
        cwd: str,
        *,
        name: str = "pexbench",
        sandbox: str = "workspace-write",
    ) -> HarnessSession:
        """Create an ephemeral thread. Never resume a listed thread.

        ``danger-full-access`` is explicit and intended only for a disposable,
        caller-controlled proof workspace. The production/default boundary is
        workspace-write.
        """
        if sandbox not in {"workspace-write", "danger-full-access"}:
            raise ValueError(f"unsupported Codex sandbox {sandbox!r}")
        raw_cwd = bounded_adapter_text(
            cwd,
            field="Codex isolated workspace",
            max_chars=MAX_PATH_CHARS,
        )
        candidate = Path(raw_cwd)
        if not candidate.is_absolute():
            raise ValueError("Codex isolated workspace must be an absolute path")
        try:
            requested = candidate.resolve()
        except (OSError, RuntimeError):
            raise ValueError("Codex isolated workspace could not be resolved") from None
        if requested == Path(requested.anchor):
            raise ValueError("Codex isolated workspace cannot be a filesystem root")
        safe_name = bounded_observed_text(
            name,
            field="Codex isolated thread name",
            max_chars=512,
        )
        if not safe_name:
            raise ValueError("Codex isolated thread name must be bounded text")
        async with self._delivery_lock:
            return await self._start_isolated_thread_locked(requested, safe_name, sandbox)

    async def _start_isolated_thread_locked(
        self,
        requested: Path,
        safe_name: str,
        sandbox: str,
    ) -> HarnessSession:
        if not await self._ready():
            raise IsolatedThreadError("codex app-server is not attached")
        transport = self.transport
        assert transport is not None
        connection_token = self._transport_connection_token(transport)
        existing = await self.existing_thread_ids()
        started = await transport.request(
            "thread/start",
            {
                "cwd": str(requested),
                "ephemeral": True,
                "sandbox": sandbox,
                "approvalPolicy": "never",
            },
        )
        if (
            self.transport is not transport
            or self._transport_connection_token(transport) != connection_token
        ):
            raise DeliveryUncertainError("Codex transport changed during thread creation")
        if not isinstance(started, dict):
            raise DeliveryUncertainError("thread/start returned no authoritative receipt object")
        if "thread" in started and not isinstance(started.get("thread"), dict):
            raise DeliveryUncertainError("thread/start returned a malformed thread receipt")
        thread = started.get("thread") if "thread" in started else started
        try:
            vendor_id = bounded_adapter_id((thread or {}).get("id") or "", field="Codex thread id")
        except ValueError:
            raise DeliveryUncertainError("thread/start returned no verified thread id") from None
        if vendor_id in existing:
            raise IsolatedThreadError(
                f"refusing to use {vendor_id}: it already existed before thread/start"
            )
        server_cwd = (thread or {}).get("cwd")
        if isinstance(server_cwd, str) and server_cwd:
            try:
                server_path = Path(server_cwd)
                if not server_path.is_absolute() or server_path.resolve() != requested:
                    raise IsolatedThreadError(
                        "thread/start cwd does not match the requested isolated workspace"
                    )
            except IsolatedThreadError:
                raise
            except (OSError, ValueError):
                raise IsolatedThreadError("thread/start cwd was not comparable") from None
        session_id = f"codex:{vendor_id}"
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.CODEX,
            vendor_session_id=vendor_id,
            cwd=str(requested),
            project_id=str(requested),
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
            metadata={
                "isolated": True,
                "name": safe_name,
                "source": "pexbench",
                "sandbox": sandbox,
            },
        )
        self.sessions[session_id] = session
        self._loaded_thread_bindings[vendor_id] = (
            connection_token,
            self._thread_load_binding(session),
        )
        return session

    async def start_turn(
        self,
        session: HarnessSession,
        text: str,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        bound = self.sessions.get(session.id)
        if (
            not session_binding_matches(bound, session, harness_type=HarnessType.CODEX)
            or session.id != f"codex:{session.vendor_session_id}"
            or not bound.cwd
            or not bound.project_id
        ):
            raise ValueError("Codex turn requires an exact session and non-empty text")
        cleaned = bounded_adapter_text(text, field="Codex turn text").strip()
        if is_chatgpt_observe_session(bound):
            raise ValueError("ChatGPT.exe observe sessions cannot start App Server turns")
        async with self._delivery_lock:
            return await self._start_turn_locked(bound, cleaned, extra_params)

    async def _start_turn_locked(
        self,
        session: HarnessSession,
        cleaned: str,
        extra_params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        session, transport = await self._ensure_thread_loaded(session)
        connection_token = self._transport_connection_token(transport)
        sandbox = str((session.metadata or {}).get("sandbox") or "workspace-write")
        sandbox_policy: dict[str, Any]
        if sandbox == "danger-full-access":
            sandbox_policy = {"type": "dangerFullAccess"}
        else:
            sandbox_policy = {
                "type": "workspaceWrite",
                "writableRoots": [session.cwd] if session.cwd else [],
                "networkAccess": False,
            }
        params: dict[str, Any] = {
            "threadId": session.vendor_session_id,
            "input": [{"type": "text", "text": cleaned}],
            "cwd": session.cwd,
            "approvalPolicy": "never",
            "sandboxPolicy": sandbox_policy,
        }
        if extra_params is not None:
            if not isinstance(extra_params, dict) or not all(
                isinstance(key, str) for key in extra_params
            ):
                raise ValueError("extra Codex turn params must be an object with text keys")
            reserved = set(params).intersection(extra_params)
            if reserved:
                raise ValueError(
                    "extra Codex turn params cannot override " + ", ".join(sorted(reserved))
                )
            unsupported = set(extra_params) - {"model", "outputSchema"}
            if unsupported:
                raise ValueError(
                    "unsupported extra Codex turn params: " + ", ".join(sorted(unsupported))
                )
            validated_extra = dict(extra_params)
            if "model" in validated_extra:
                validated_extra["model"] = bounded_adapter_id(
                    validated_extra["model"], field="Codex turn model"
                )
            if "outputSchema" in validated_extra and not isinstance(
                validated_extra["outputSchema"], dict
            ):
                raise ValueError("Codex outputSchema must be an object")
            try:
                encoded_extra = strict_json_dumps(
                    validated_extra,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError("extra Codex turn params must be bounded JSON") from exc
            if len(encoded_extra.encode("utf-8")) > 65_536:
                raise ValueError("extra Codex turn params exceed the safety bound")
            params.update(validated_extra)
        inbox = self.inbox.setdefault(session.id, [])
        if len(inbox) >= MAX_INBOX_MESSAGES:
            raise RuntimeError("Codex session inbox safety bound reached")
        result = await transport.request("turn/start", params)
        if (
            self.transport is not transport
            or self._transport_connection_token(transport) != connection_token
        ):
            raise DeliveryUncertainError("Codex transport changed during turn delivery")
        if not isinstance(result, dict):
            raise DeliveryUncertainError("Codex turn/start returned a malformed receipt")
        turn = result.get("turn") if isinstance(result.get("turn"), dict) else {}
        try:
            turn_id = bounded_adapter_id(turn.get("id") or "", field="Codex turn id")
        except ValueError as exc:
            raise DeliveryUncertainError(
                "Codex turn/start did not return a verified turn id"
            ) from exc
        inbox.append(cleaned)
        recorded = getattr(transport, "turns", None)
        self.last_turn_params = recorded[-1] if recorded else params
        self.last_turn_id = turn_id
        return result

    async def start_session(
        self,
        project: str,
        prompt: str,
        config: dict | None = None,
    ) -> HarnessSession | None:
        """Start a new isolated Codex thread and its first turn.

        This path is deliberately workspace-write only. The policy layer still
        requires an authenticated human decision before calling it because a
        real turn can incur provider cost.
        """
        try:
            cleaned_project = bounded_adapter_text(
                project,
                field="Codex project",
                max_chars=MAX_PATH_CHARS,
            )
            cleaned_prompt = bounded_adapter_text(prompt, field="Codex start prompt").strip()
        except ValueError:
            return None
        candidate = Path(cleaned_project)
        if not candidate.is_absolute():
            return None
        try:
            requested = candidate.resolve()
        except (OSError, RuntimeError):
            return None
        if requested == Path(requested.anchor) or not requested.is_dir():
            return None
        if config is not None and not isinstance(config, dict):
            return None
        config = config or {}
        name = bounded_observed_text(
            config.get("name") or "pex-worker",
            field="Codex worker name",
            max_chars=120,
        )
        if not name:
            return None
        session = await self.start_isolated_thread(
            str(requested),
            name=name,
            sandbox="workspace-write",
        )
        session.metadata.update({"source": "pex_lifecycle", "started_by_pex": True})
        result = await self.start_turn(session, cleaned_prompt)
        turn_id = str((result.get("turn") or {}).get("id") or "")
        if not turn_id:
            session.status = SessionStatus.ERROR
            session.metadata["start_error"] = "turn/start returned no turn id"
            raise IsolatedThreadError("turn/start returned no turn id after thread creation")
        session.metadata["started_turn_id"] = turn_id
        return session

    async def wait_for_turn_completion(
        self,
        session: HarnessSession,
        turn_id: str,
        *,
        timeout: float = 600,
    ) -> dict[str, Any]:
        """Wait for the official `turn/completed` notification for this isolated turn."""
        if self.transport is None:
            raise RuntimeError("codex app-server is not attached")
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.CODEX
        ):
            raise ValueError("Codex wait session binding mismatch")
        turn_id = bounded_adapter_id(turn_id, field="Codex turn id")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or not 0 < float(timeout) <= 3_600
        ):
            raise ValueError("Codex wait timeout is outside the safety bound")
        deadline = asyncio.get_running_loop().time() + timeout
        completion_key = (session.vendor_session_id, turn_id)
        cached = self._completed_turns.get(completion_key)
        if cached is not None:
            return dict(cached)
        completion_event = self._turn_completion_waiters.setdefault(
            completion_key,
            asyncio.Event(),
        )
        seen = 0
        try:
            while asyncio.get_running_loop().time() < deadline:
                cached = self._completed_turns.get(completion_key)
                if cached is not None:
                    return dict(cached)
                pending = getattr(self.transport, "pending_approvals", {})
                for request_id, request in list(pending.items()):
                    params = request.get("params") or {}
                    thread_id = str(params.get("threadId") or "")
                    if thread_id and thread_id != session.vendor_session_id:
                        continue
                    decision = self._isolated_approval_decision(session, request)
                    if len(self.isolated_approval_decisions) >= MAX_CODEX_RECORDS:
                        raise RuntimeError("Codex approval audit safety bound reached")
                    self.isolated_approval_decisions.append(
                        {
                            "request_id": request_id,
                            "method": request.get("method"),
                            "decision": decision,
                        }
                    )
                    await self.respond_permission(session, request_id, decision)

                pump_active = self._pump_task is not None and not self._pump_task.done()
                notifications = getattr(self.transport, "notifications", [])
                if not pump_active:
                    if seen > len(notifications):
                        seen = 0
                    for message in notifications[seen:]:
                        if not isinstance(message, dict):
                            continue
                        params = message.get("params") or {}
                        if not isinstance(params, dict):
                            continue
                        self._collect_isolated_item(session, message)
                        turn = params.get("turn") or {}
                        if (
                            message.get("method") == "turn/completed"
                            and params.get("threadId") == session.vendor_session_id
                            and isinstance(turn, dict)
                        ):
                            self._remember_turn_completion(session, turn)
                    seen = len(notifications)
                    cached = self._completed_turns.get(completion_key)
                    if cached is not None:
                        return dict(cached)

                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    await asyncio.wait_for(
                        completion_event.wait(),
                        timeout=min(0.05, remaining),
                    )
                except TimeoutError:
                    pass
            raise TimeoutError(f"timed out waiting for Codex turn {turn_id}")
        finally:
            if self._turn_completion_waiters.get(completion_key) is completion_event:
                self._turn_completion_waiters.pop(completion_key, None)

    def _collect_isolated_item(self, session: HarnessSession, message: dict[str, Any]) -> None:
        params = message.get("params") or {}
        thread_id = str(params.get("threadId") or "")
        if thread_id and thread_id != session.vendor_session_id:
            return
        item = params.get("item") if isinstance(params.get("item"), dict) else params
        kind = str((item or {}).get("type") or "")
        if kind:
            if len(self.isolated_item_types) >= MAX_CODEX_RECORDS:
                raise RuntimeError("Codex isolated item safety bound reached")
            self.isolated_item_types.append(kind)
        text = (item or {}).get("text")
        if kind == "agentMessage" and isinstance(text, str) and text.strip():
            if len(self.isolated_agent_messages) >= MAX_CODEX_RECORDS:
                raise RuntimeError("Codex isolated message safety bound reached")
            self.isolated_agent_messages.append(
                bounded_adapter_text(text, field="Codex agent message")
            )

    @staticmethod
    def _isolated_approval_decision(
        session: HarnessSession,
        request: dict[str, Any],
    ) -> str:
        """Fail closed under approvalPolicy=never; never silently broaden a turn."""
        _ = (session, request)
        return "deny"

    async def _ready(self) -> bool:
        if self.transport is None:
            return False
        try:
            await self.transport.ensure_ready()
        except Exception:
            return False
        return True

    async def probe(self) -> AdapterCapabilities:
        connected = False
        if await self._ready():
            assert self.transport is not None
            try:
                listed = await self.transport.request("thread/list", {"limit": 1})
                connected = isinstance(listed, dict) and (
                    isinstance(listed.get("data"), list) or isinstance(listed.get("threads"), list)
                )
            except Exception:
                connected = False
        desktop = chatgpt_desktop_running()
        pumping = (
            connected
            and self._pump_task is not None
            and not self._pump_task.done()
            and self.last_pump_error is None
            and (
                getattr(self.transport, "_reader_task", None) is None
                or not self.transport._reader_task.done()  # type: ignore[attr-defined]
            )
        )
        if pumping:
            label = AdapterSupportLabel.DEEP
            note = "Transport handshake, thread listing, and event pump are healthy."
        elif connected:
            label = AdapterSupportLabel.BASIC
            note = "Transport handshake passed; observation awaits a healthy event pump."
        elif desktop:
            label = AdapterSupportLabel.OBSERVE_ONLY
            note = (
                "ChatGPT.exe is running. Observe/focus only. Isolated `codex app-server` "
                "is a separate attach; private desktop JSON-RPC is unproven."
            )
        else:
            label = AdapterSupportLabel.UNAVAILABLE
            note = "No live App Server process; ChatGPT.exe is not running."
        return AdapterCapabilities(
            observe_messages=pumping,
            observe_thought_events=pumping,
            observe_tool_calls=pumping,
            observe_file_edits=pumping,
            observe_shell=pumping,
            observe_permissions=pumping,
            observe_session_status=connected or desktop,
            send_message=connected,
            inject_context=connected,
            # Every PEX turn is started with approvalPolicy=never. If a server
            # nevertheless emits an approval request, only an explicit denial
            # is a faithful response; this adapter never broadens that policy.
            approve=False,
            deny=pumping,
            permission_response_mode=(
                PermissionResponseMode.ASYNC if pumping else PermissionResponseMode.NONE
            ),
            start=connected,
            resume=connected,
            fork=False,
            focus_ui=desktop,
            control_granularity=ControlGranularity.EVENT if pumping else ControlGranularity.SESSION,
            trust_level=0.9 if pumping else 0.65 if connected else 0.35 if desktop else 0.0,
            support_label=label,
            notes=(
                "Official surface: isolated `codex app-server` JSON-RPC "
                "(initialize, thread/start|resume, turn/start, server-initiated approvals). " + note
            ),
        )

    async def focus_ui(self, session: HarnessSession) -> bool:
        from pex_bridge.adapters.winfocus import focus_harness

        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.CODEX
        ):
            return False
        return focus_harness("codex")

    def _observe_desktop_session(self) -> None:
        from pex_bridge.adapters.desktop import upsert_desktop_observe_session

        upsert_desktop_observe_session(
            self.sessions,
            harness=HarnessType.CODEX,
            process="ChatGPT.exe",
        )

    def _drop_unconfirmed_app_server_sessions(self) -> None:
        live = {
            SessionStatus.WORKING,
            SessionStatus.VERIFYING,
            SessionStatus.DRIFTING,
            SessionStatus.NEEDS_DECISION,
            SessionStatus.BLOCKED,
        }
        for session_id, session in list(self.sessions.items()):
            if session_id == "codex:desktop":
                continue
            if session.status in live or (session.metadata or {}).get("isolated") is True:
                continue
            self.sessions.pop(session_id, None)
            self._loaded_thread_bindings.pop(session.vendor_session_id, None)

    async def discover_sessions(self) -> list[HarnessSession]:
        if not await self._ready():
            self._drop_unconfirmed_app_server_sessions()
            self._observe_desktop_session()
            return list(self.sessions.values())
        assert self.transport is not None
        listed = await self.transport.request("thread/list", {"limit": 50})
        rows = _thread_rows(listed)
        if len(rows) > MAX_CODEX_SESSIONS:
            raise RuntimeError("Codex thread listing exceeded the safety bound")
        for thread in rows:
            try:
                vendor_id = bounded_adapter_id(thread.get("id") or "", field="Codex thread id")
            except ValueError:
                continue
            session_id = f"codex:{vendor_id}"
            existing = self.sessions.get(session_id)
            status = SessionStatus.WORKING if existing else SessionStatus.DISCOVERED
            raw_status = thread.get("status")
            if isinstance(raw_status, dict) and raw_status.get("type") == "idle":
                status = SessionStatus.IDLE
            listed_cwd = thread.get("cwd")
            if not isinstance(listed_cwd, str) or not listed_cwd:
                listed_cwd = existing.cwd if existing else None
            if listed_cwd:
                listed_cwd = bounded_adapter_text(
                    listed_cwd, field="Codex cwd", max_chars=MAX_PATH_CHARS
                )
            raw_project_id = thread.get("projectId")
            project_id = raw_project_id if isinstance(raw_project_id, str) else listed_cwd
            if project_id:
                project_id = bounded_adapter_text(
                    project_id, field="Codex project id", max_chars=MAX_PATH_CHARS
                )
            goal_id, paused = preserve_bridge_state(
                existing,
                cwd=listed_cwd,
                project_id=project_id,
            )
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.CODEX,
                vendor_session_id=vendor_id,
                cwd=listed_cwd,
                project_id=project_id,
                status=status,
                last_activity=datetime.now(UTC),
                goal_id=goal_id,
                supervision_paused=paused,
                metadata={
                    "name": bounded_observed_text(
                        thread.get("name"), field="Codex thread name", max_chars=256
                    ),
                    "source": bounded_observed_text(
                        thread.get("source"), field="Codex thread source", max_chars=256
                    ),
                },
            )
        self._observe_desktop_session()
        return list(self.sessions.values())

    async def send_message(
        self,
        session: HarnessSession,
        text: str,
        attachments=None,
    ) -> bool | AdapterMessageResult:
        if is_chatgpt_observe_session(session):
            return False
        try:
            result = await self.start_turn(session, text)
        except (DeliveryUncertainError, TimeoutError):
            raise
        except Exception:
            return False
        turn = result.get("turn") if isinstance(result.get("turn"), dict) else {}
        turn_id = bounded_adapter_id(turn.get("id") or "", field="Codex turn id")
        return AdapterMessageResult(
            accepted=True,
            vendor_session_id=session.vendor_session_id,
            vendor_turn_id=turn_id,
        )

    async def respond_permission(
        self, session: HarnessSession, request_id: str, decision: str
    ) -> bool:
        try:
            request_id = bounded_adapter_id(request_id, field="Codex approval request id")
        except ValueError:
            return False
        pending = getattr(self.transport, "pending_approvals", {}) if self.transport else {}
        request = pending.get(request_id) if isinstance(pending, dict) else None
        params = request.get("params") if isinstance(request, dict) else None
        bound_thread = str((params or {}).get("threadId") or "")
        bound_session = self.sessions.get(session.id)
        if (
            self.transport is None
            or not request_id
            or not isinstance(request, dict)
            or not session_binding_matches(bound_session, session, harness_type=HarnessType.CODEX)
            or session.id != f"codex:{session.vendor_session_id}"
            or is_chatgpt_observe_session(session)
            or bound_thread != session.vendor_session_id
            or decision != "deny"
        ):
            return False
        try:
            await self.transport.respond_approval(request_id, decision)
        except DeliveryUncertainError:
            raise
        except Exception:
            return False
        return True

    @staticmethod
    def _bounded_user_message_text(raw: object) -> tuple[str | None, bool, bool]:
        """Return an exact bounded prefix plus truncation/redaction facts."""

        if not isinstance(raw, str) or not raw or "\x00" in raw:
            return None, False, False
        truncated = len(raw) > MAX_ADAPTER_MESSAGE_CHARS
        prefix = raw[:MAX_ADAPTER_MESSAGE_CHARS]
        observed = bounded_observed_text(
            prefix,
            field="Codex user message",
            max_chars=MAX_ADAPTER_MESSAGE_CHARS,
        )
        return observed, truncated, observed is not None and (
            observed != prefix or "[REDACTED:" in prefix
        )

    @classmethod
    def _normalize_user_message_content(
        cls,
        item: dict[str, Any],
    ) -> tuple[str | None, dict[str, Any]]:
        """Normalize documented userMessage content without inventing text."""

        max_parts = 128
        metadata: dict[str, Any] = {
            "role": "user",
            "message_provenance": "codex_app_server.userMessage.content",
            "content_status": "missing",
            "content_part_count": 0,
            "content_parts_observed": 0,
            "text_parts_observed": 0,
            "unsupported_content_parts": 0,
            "malformed_content_parts": 0,
            "content_truncated": False,
            "content_redacted": False,
        }
        if "content" not in item:
            raw_text = item.get("text")
            raw_message = item.get("message")
            raw = raw_text or raw_message
            if raw in (None, ""):
                return None, metadata
            field = "text" if raw_text else "message"
            message, truncated, redacted = cls._bounded_user_message_text(raw)
            metadata.update(
                {
                    "message_provenance": f"codex_app_server.userMessage.{field}",
                    "content_status": (
                        "truncated"
                        if message is not None and truncated
                        else "legacy_top_level"
                        if message is not None
                        else "malformed"
                    ),
                    "content_truncated": truncated,
                    "content_redacted": redacted,
                }
            )
            return message, metadata

        content = item.get("content")
        if not isinstance(content, list):
            metadata["content_status"] = "malformed"
            return None, metadata
        metadata["content_part_count"] = len(content)
        if len(content) > max_parts:
            metadata["content_truncated"] = True

        chunks: list[str] = []
        remaining = MAX_ADAPTER_MESSAGE_CHARS
        unsupported_types: list[str] = []
        for part in content[:max_parts]:
            metadata["content_parts_observed"] += 1
            if not isinstance(part, dict):
                metadata["malformed_content_parts"] += 1
                continue
            part_type = part.get("type")
            if part_type != "text":
                if not isinstance(part_type, str) or not part_type:
                    metadata["malformed_content_parts"] += 1
                    continue
                metadata["unsupported_content_parts"] += 1
                try:
                    bounded_type = bounded_adapter_id(
                        part_type,
                        field="Codex user content type",
                    )
                except ValueError:
                    metadata["malformed_content_parts"] += 1
                    metadata["unsupported_content_parts"] -= 1
                    continue
                if bounded_type not in unsupported_types and len(unsupported_types) < 16:
                    unsupported_types.append(bounded_type)
                continue
            raw_text = part.get("text")
            if not isinstance(raw_text, str) or "\x00" in raw_text:
                metadata["malformed_content_parts"] += 1
                continue
            metadata["text_parts_observed"] += 1
            if not raw_text:
                continue
            if remaining <= 0:
                metadata["content_truncated"] = True
                continue
            prefix = raw_text[:remaining]
            chunks.append(prefix)
            remaining -= len(prefix)
            if len(prefix) != len(raw_text):
                metadata["content_truncated"] = True

        if unsupported_types:
            metadata["unsupported_content_types"] = unsupported_types
        raw_message = "".join(chunks)
        message = bounded_observed_text(
            raw_message,
            field="Codex user message content",
            max_chars=MAX_ADAPTER_MESSAGE_CHARS,
        )
        metadata["content_redacted"] = message is not None and (
            message != raw_message or "[REDACTED:" in raw_message
        )
        has_unsupported = bool(
            metadata["unsupported_content_parts"]
            or metadata["malformed_content_parts"]
        )
        if metadata["content_truncated"]:
            metadata["content_status"] = "truncated"
        elif message is not None and has_unsupported:
            metadata["content_status"] = "partial_unsupported"
        elif message is not None:
            metadata["content_status"] = "complete"
        elif metadata["malformed_content_parts"]:
            metadata["content_status"] = "malformed"
        elif metadata["unsupported_content_parts"]:
            metadata["content_status"] = "unsupported"
        else:
            metadata["content_status"] = "empty"
        return message, metadata

    def normalize_item(
        self,
        session: HarnessSession,
        item: dict[str, Any],
        *,
        event_suffix: str | None = None,
        vendor_turn_id: str | None = None,
    ) -> HarnessEvent:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.CODEX
        ):
            raise ValueError("Codex item session binding mismatch")
        raw_kind = item.get("type")
        try:
            kind = bounded_adapter_id(
                raw_kind if isinstance(raw_kind, str) else "status",
                field="Codex item type",
            )
        except ValueError:
            kind = "status"
        mapping = {
            "agentMessage": EventType.AGENT_RESPONSE,
            "userMessage": EventType.USER_PROMPT,
            "commandExecution": EventType.SHELL,
            "fileChange": EventType.FILE_EDIT,
            "todo": EventType.STATUS,
            "reasoning": EventType.AGENT_THOUGHT,
            "contextCompaction": EventType.COMPACTION,
        }
        command = item.get("command")
        if isinstance(command, dict):
            command = command.get("command") or command.get("cmd")
        files: list[str] = []
        if isinstance(item.get("path"), str) and item.get("path"):
            files.append(_bounded_path(item["path"]))
        changes = item.get("changes") or item.get("files") or []
        if not isinstance(changes, list):
            changes = []
        for change in changes[:256]:
            if isinstance(change, str):
                files.append(_bounded_path(change))
            elif isinstance(change, dict):
                path = change.get("path") or change.get("file")
                if isinstance(path, str) and path:
                    files.append(_bounded_path(path))
        message = None
        message_metadata: dict[str, Any] = {}
        if kind == "userMessage":
            message, message_metadata = self._normalize_user_message_content(item)
        elif kind in {"agentMessage", "reasoning"}:
            raw = item.get("text") or item.get("message")
            if isinstance(raw, str) and raw:
                message = bounded_observed_text(
                    raw,
                    field="Codex item message",
                    max_chars=MAX_ADAPTER_MESSAGE_CHARS,
                )
        process_state = None
        error = None
        if kind == "commandExecution":
            payload = {
                "output": (
                    item.get("aggregatedOutput")
                    or item.get("aggregated")
                    or item.get("output")
                    or item.get("stdout")
                ),
                "stderr": item.get("stderr"),
                "exit_code": (
                    item.get("exitCode")
                    if item.get("exitCode") is not None
                    else item.get("exit_code")
                ),
                "status": item.get("status"),
            }
            process_state = parse_pytest_process_state(str(command or ""), payload)
            status = item.get("status")
            if isinstance(status, str) and status.lower() in {"failed", "error"}:
                error = bounded_observed_text(
                    payload.get("output") or payload.get("stderr") or "command failed",
                    field="Codex item error",
                )
        event_id_suffix = event_suffix or _safe_event_suffix(item.get("id"))
        return HarnessEvent(
            event_id=f"{session.id}:item:{event_id_suffix}",
            ts=datetime.now(UTC),
            harness_type=HarnessType.CODEX,
            session_id=session.id,
            project_id=session.project_id,
            event_type=mapping.get(kind, EventType.STATUS),
            phase=EventPhase.DURING,
            raw_event_ref=self._raw_event_ref(
                session,
                turn_id=vendor_turn_id,
                item_id=event_id_suffix,
            ),
            message_delta=message,
            command=(
                bounded_observed_text(
                    command,
                    field="Codex command",
                    max_chars=MAX_ADAPTER_MESSAGE_CHARS,
                )
                if isinstance(command, str) and command
                else None
            ),
            file_paths=files,
            error=error,
            process_state=process_state,
            metadata={
                "raw_type": kind,
                "vendor_turn_id": vendor_turn_id,
                **message_metadata,
            },
        )

    async def pump_into_pipeline(self, ingest) -> None:
        seen_approvals: dict[str, tuple[str, str]] = {}
        seen_items: set[str] = set()
        seen_item_order: deque[str] = deque()
        seen_transport: CodexTransport | None = None
        last_discover: float | None = None

        def remember_item(item_key: str) -> None:
            if not item_key or item_key in seen_items:
                return
            seen_items.add(item_key)
            seen_item_order.append(item_key)
            while len(seen_item_order) > MAX_CODEX_RECORDS:
                seen_items.discard(seen_item_order.popleft())

        while True:
            try:
                transport = self.transport
                if transport is not seen_transport:
                    if seen_transport is not None:
                        self._completed_turns.clear()
                        self._completed_turn_order.clear()
                    seen_transport = transport
                    seen_approvals.clear()
                    seen_items.clear()
                    seen_item_order.clear()
                    last_discover = None
                now = asyncio.get_running_loop().time()
                if last_discover is None or now - last_discover >= 1.0:
                    await self.discover_sessions()
                    last_discover = now
                pending = getattr(transport, "pending_approvals", {}) if transport else {}
                if not isinstance(pending, dict) or len(pending) > MAX_CODEX_PENDING:
                    raise RuntimeError("Codex pending approvals exceeded the safety bound")
                active_approval_ids = {str(request_id) for request_id in pending}
                for stale_key in set(seen_approvals) - active_approval_ids:
                    seen_approvals.pop(stale_key, None)
                for request_id, request in list(pending.items()):
                    if not isinstance(request, dict):
                        continue
                    try:
                        key = bounded_adapter_id(str(request_id), field="Codex approval id")
                    except ValueError:
                        continue
                    request_identity = self._approval_identity(request)
                    request_fingerprint = self._request_fingerprint(request)
                    receipt_key = (request_identity, request_fingerprint)
                    if seen_approvals.get(key) == receipt_key:
                        continue
                    params = request.get("params") or {}
                    if not isinstance(params, dict):
                        params = {}
                    session = self._session_for(params)
                    if session is None:
                        continue
                    event = HarnessEvent(
                        event_id=(
                            f"{session.id}:approval:{key}:"
                            f"{request_identity.rsplit(':', 1)[-1]}:{request_fingerprint}"
                        ),
                        ts=datetime.now(UTC),
                        harness_type=HarnessType.CODEX,
                        session_id=session.id,
                        project_id=session.project_id,
                        event_type=EventType.PERMISSION_REQUEST,
                        phase=EventPhase.BEFORE,
                        command=params.get("command")
                        if isinstance(params.get("command"), str)
                        else None,
                        approval_request={
                            "request_id": key,
                            "id": key,
                            "method": request.get("method"),
                            "params": params,
                        },
                        metadata={"raw_method": request.get("method")},
                    )
                    await ingest(event, session)
                    # Do not acknowledge an approval until its audit event has been
                    # ingested. A transient store failure must retry this exact request.
                    seen_approvals[key] = receipt_key
                notifications = getattr(transport, "notifications", []) if transport else []
                if not isinstance(notifications, list) or len(notifications) > MAX_CODEX_RECORDS:
                    raise RuntimeError("Codex notifications exceeded the safety bound")
                # Consume only the stable prefix visible at the start of this pass.
                # A STOP may append same-thread outcome notifications while ingest
                # awaits; they remain at the head for the next fair pump pass.
                watermark = min(len(notifications), MAX_CODEX_NOTIFICATIONS_PER_PASS)
                for _ in range(watermark):
                    message = notifications[0]
                    if not isinstance(message, dict):
                        del notifications[0]
                        continue
                    notification_identity = self._notification_identity(message)
                    params = message.get("params") or {}
                    if not isinstance(params, dict):
                        params = {}
                    session = self._session_for(params)
                    if session is None:
                        del notifications[0]
                        continue
                    method = message.get("method")
                    if method == "turn/completed":
                        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
                        self._remember_turn_completion(session, turn)
                        items = turn.get("items") or []
                        if not isinstance(items, list) or len(items) > MAX_CODEX_RECORDS:
                            raise RuntimeError("Codex turn items exceeded the safety bound")
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            item_key, event_suffix = self._item_identity(
                                session,
                                params,
                                item,
                                notification_identity,
                            )
                            if item_key in seen_items:
                                continue
                            await ingest(
                                self.normalize_item(
                                    session,
                                    item,
                                    event_suffix=event_suffix,
                                    vendor_turn_id=self._vendor_turn_id(params, item),
                                ),
                                session,
                            )
                            remember_item(item_key)
                        turn_status = (
                            bounded_observed_text(
                                turn.get("status"),
                                field="Codex turn status",
                                max_chars=512,
                            )
                            or "completed"
                        )
                        turn_error = turn.get("error")
                        raw_turn_id = turn.get("id")
                        try:
                            vendor_turn_id = (
                                bounded_adapter_id(raw_turn_id, field="Codex turn id")
                                if isinstance(raw_turn_id, str) and raw_turn_id
                                else None
                            )
                        except ValueError:
                            vendor_turn_id = None
                        turn_suffix = vendor_turn_id or (
                            "anonymous:" + notification_identity.replace(":", "-")
                        )
                        stop_metadata = {
                            "raw_method": "turn/completed",
                            "turn_status": turn_status,
                        }
                        if vendor_turn_id is not None:
                            stop_metadata["vendor_turn_id"] = vendor_turn_id
                        event = HarnessEvent(
                            event_id=f"{session.id}:turn:{turn_suffix}",
                            ts=datetime.now(UTC),
                            harness_type=HarnessType.CODEX,
                            session_id=session.id,
                            project_id=session.project_id,
                            event_type=EventType.STOP,
                            phase=EventPhase.TERMINAL,
                            raw_event_ref=self._raw_event_ref(
                                session,
                                turn_id=vendor_turn_id,
                            ),
                            error=bounded_observed_text(turn_error, field="Codex turn error"),
                            metadata=stop_metadata,
                        )
                        await ingest(event, session)
                    elif method == "item/completed":
                        item = (
                            params.get("item") if isinstance(params.get("item"), dict) else params
                        )
                        item_key, event_suffix = self._item_identity(
                            session,
                            params,
                            item if isinstance(item, dict) else {},
                            notification_identity,
                        )
                        if item_key not in seen_items:
                            event = self.normalize_item(
                                session,
                                item if isinstance(item, dict) else {},
                                event_suffix=event_suffix,
                                vendor_turn_id=self._vendor_turn_id(
                                    params,
                                    item if isinstance(item, dict) else {},
                                ),
                            )
                            await ingest(event, session)
                            remember_item(item_key)
                    # Acknowledge this exact record only after every derived event was
                    # ingested. On failure the poison record stays, but successful prefix
                    # records are already reclaimed and cannot exhaust retention.
                    del notifications[0]
                self.last_pump_error = None
                await asyncio.sleep(0.05)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_pump_error = type(exc).__name__
                await asyncio.sleep(0.5)

    def start_pipeline_pump(self, ingest) -> asyncio.Task:
        existing = self._pump_task
        if existing is not None and not existing.done():
            return existing
        self._pump_task = asyncio.create_task(
            self.pump_into_pipeline(ingest),
            name="codex-pipeline-pump",
        )
        return self._pump_task


def _bounded_path(value: object) -> str:
    return bounded_adapter_text(value, field="path", max_chars=MAX_PATH_CHARS)


def _validated_jsonrpc_id(value: object) -> int | str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return bounded_adapter_id(value, field="Codex JSON-RPC id")
        except ValueError:
            return None
    return None


def _safe_event_suffix(value: object) -> str:
    raw = str(value or uuid4().hex)
    try:
        return bounded_adapter_id(raw, field="Codex event id")
    except ValueError:
        return uuid4().hex


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
