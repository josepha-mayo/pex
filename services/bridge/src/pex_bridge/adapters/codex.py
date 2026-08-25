"""OpenAI Codex App Server JSON-RPC.

Wire format is newline-delimited JSON with the `"jsonrpc":"2.0"` header omitted.
Deep only after a live or injected transport completes `initialize` + `initialized`.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import HarnessAdapter
from pex_bridge.adapters.codex_bin import app_server_command

CLIENT_INFO = {"name": "pex", "title": "PEX", "version": "0.1.0"}
INIT_PARAMS = {"clientInfo": CLIENT_INFO, "capabilities": {}}

COMMAND_APPROVALS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
}
LEGACY_APPROVALS = {"execCommandApproval", "applyPatchApproval"}
PERMISSION_APPROVAL = "item/permissions/requestApproval"
APPROVAL_METHODS = COMMAND_APPROVALS | LEGACY_APPROVALS | {PERMISSION_APPROVAL}


class CodexTransport(Protocol):
    initialized: bool

    async def ensure_ready(self) -> dict[str, Any]: ...

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]: ...

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None: ...

    async def respond_approval(self, request_id: str, decision: str) -> None: ...

    async def close(self) -> None: ...


def approval_result(method: str, decision: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Map PEX allow/deny onto Codex v2 (and legacy) approval payloads."""
    token = decision.lower().replace("-", "_").replace(" ", "_")
    session = token in {"allow_session", "accept_for_session", "acceptforsession", "approved_for_session"}
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
        return rows
    rows = listed.get("threads")
    if isinstance(rows, list):
        return rows
    return []


class CodexAppServerTransport:
    """In-process App Server stand-in. Not a live `codex` process."""

    def __init__(self) -> None:
        self.turns: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.approvals: list[dict[str, Any]] = []
        self.threads: list[dict[str, Any]] = [
            {"id": "thr_demo", "preview": "synthetic thread", "cwd": None}
        ]
        self.initialized = False
        self.pending_approvals: dict[str, dict[str, Any]] = {}

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
            return {"thread": {"id": params.get("threadId")}}
        if method == "turn/start":
            self.turns.append(params)
            turn = {"id": f"turn_{len(self.turns)}", "status": "completed", "items": []}
            self.notifications.append(
                {
                    "method": "turn/completed",
                    "params": {"threadId": params.get("threadId"), "turn": turn},
                }
            )
            return {"turn": turn}
        raise KeyError(method)

    async def respond_approval(self, request_id: str, decision: str) -> None:
        pending = self.pending_approvals.pop(str(request_id), {})
        method = str(pending.get("method") or "item/commandExecution/requestApproval")
        self.approvals.append(
            {
                "request_id": request_id,
                "decision": decision,
                "result": approval_result(method, decision, pending.get("params") or {}),
            }
        )

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        return None

    async def close(self) -> None:
        return None


class CodexStdioTransport:
    """Live `codex app-server --listen stdio://` child process."""

    def __init__(self, command: str | list[str]) -> None:
        if isinstance(command, str):
            self.command = app_server_command(command)
        else:
            self.command = list(command)
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[Any, asyncio.Future] = {}
        self._next_id = 1
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self.initialized = False
        self.pending_approvals: dict[str, dict[str, Any]] = {}
        self.notifications: list[dict[str, Any]] = []
        self.stderr_tail: list[str] = []
        self.init_result: dict[str, Any] | None = None
        self.approvals: list[dict[str, Any]] = []
        self.turns: list[dict[str, Any]] = []

    async def start(self) -> None:
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
            **kwargs,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._stderr_loop())

    async def _stderr_loop(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            if text:
                self.stderr_tail.append(text[-500:])
                self.stderr_tail = self.stderr_tail[-30:]

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue
            msg_id = msg.get("id")
            if msg_id is not None and ("result" in msg or "error" in msg):
                fut = self._pending.pop(msg_id, None)
                if fut is None:
                    fut = self._pending.pop(str(msg_id), None)
                if fut and not fut.done():
                    if "error" in msg:
                        fut.set_exception(RuntimeError(str(msg["error"])))
                    else:
                        fut.set_result(msg.get("result") or {})
                continue
            method = msg.get("method")
            if method in APPROVAL_METHODS and msg_id is not None:
                self.pending_approvals[str(msg_id)] = msg
                continue
            if method:
                # Official turn/item events are notifications. Some builds still attach an
                # `id`; do not treat those as approval requests or the turn never completes.
                self.notifications.append(msg)

    async def _write(self, payload: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def ensure_ready(self) -> dict[str, Any]:
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
        if self._proc is None:
            await self.start()
        req_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut
        await self._write({"id": req_id, "method": method, "params": params or {}})
        try:
            result = await asyncio.wait_for(fut, timeout=45)
        except TimeoutError as exc:
            tail = "\n".join(self.stderr_tail[-8:])
            raise RuntimeError(f"codex app-server timeout on {method}: {tail}") from exc
        if method == "turn/start":
            self.turns.append(params or {})
        return result

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        if self._proc is None:
            await self.start()
        await self._write({"method": method, "params": params or {}})

    async def respond_approval(self, request_id: str, decision: str) -> None:
        pending = self.pending_approvals.pop(str(request_id), {})
        method = str(pending.get("method") or "item/commandExecution/requestApproval")
        result = approval_result(method, decision, pending.get("params") or {})
        self.approvals.append({"request_id": request_id, "decision": decision, "result": result})
        payload_id: Any = pending.get("id", request_id)
        try:
            payload_id = int(payload_id)
        except (TypeError, ValueError):
            payload_id = request_id
        if result.get("denied"):
            await self._write(
                {"id": payload_id, "error": {"code": -32001, "message": "denied by PEX"}}
            )
            return
        await self._write({"id": payload_id, "result": result})

    async def close(self) -> None:
        for task in (self._reader_task, self._stderr_task):
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
        self.initialized = False


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

    def attach_transport(self, transport: CodexTransport) -> None:
        self.transport = transport

    async def existing_thread_ids(self) -> set[str]:
        if not await self._ready():
            return set()
        assert self.transport is not None
        listed = await self.transport.request("thread/list", {"limit": 100})
        return {str(row.get("id")) for row in _thread_rows(listed) if row.get("id")}

    async def start_isolated_thread(self, cwd: str, *, name: str = "pexbench") -> HarnessSession:
        """Create an ephemeral, workspace-sandboxed thread. Never resume a listed thread."""
        if not await self._ready():
            raise IsolatedThreadError("codex app-server is not attached")
        assert self.transport is not None
        existing = await self.existing_thread_ids()
        requested = Path(cwd).resolve()
        started = await self.transport.request(
            "thread/start",
            {
                "cwd": str(requested),
                "ephemeral": True,
                "sandbox": "workspace-write",
                "approvalPolicy": "never",
            },
        )
        thread = started.get("thread") if isinstance(started.get("thread"), dict) else started
        vendor_id = str((thread or {}).get("id") or "")
        if not vendor_id:
            raise IsolatedThreadError("thread/start returned no id")
        if vendor_id in existing:
            raise IsolatedThreadError(
                f"refusing to use {vendor_id}: it already existed before thread/start"
            )
        server_cwd = (thread or {}).get("cwd")
        if isinstance(server_cwd, str) and server_cwd:
            try:
                if Path(server_cwd).resolve() != requested:
                    raise IsolatedThreadError(
                        f"thread/start cwd {server_cwd!r} does not match requested {requested}"
                    )
            except IsolatedThreadError:
                raise
            except (OSError, ValueError) as exc:
                raise IsolatedThreadError(f"thread/start cwd was not comparable: {exc}") from exc
        session_id = f"codex:{vendor_id}"
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.CODEX,
            vendor_session_id=vendor_id,
            cwd=str(requested),
            project_id=str(requested),
            status=SessionStatus.WORKING,
            last_activity=datetime.now(timezone.utc),
            metadata={"isolated": True, "name": name, "source": "pexbench"},
        )
        self.sessions[session_id] = session
        return session

    async def start_turn(
        self,
        session: HarnessSession,
        text: str,
        extra_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not await self._ready():
            raise RuntimeError("codex app-server is not attached")
        assert self.transport is not None
        self.inbox.setdefault(session.id, []).append(text)
        params: dict[str, Any] = {
            "threadId": session.vendor_session_id,
            "input": [{"type": "text", "text": text}],
            "cwd": session.cwd,
            "approvalPolicy": "never",
            "sandboxPolicy": {
                "type": "workspaceWrite",
                "writableRoots": [session.cwd] if session.cwd else [],
                "networkAccess": False,
            },
        }
        if extra_params:
            params.update(extra_params)
        result = await self.transport.request("turn/start", params)
        recorded = getattr(self.transport, "turns", None)
        self.last_turn_params = recorded[-1] if recorded else params
        self.last_turn_id = str((result.get("turn") or {}).get("id") or "")
        return result

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
        deadline = asyncio.get_running_loop().time() + timeout
        seen = 0
        while asyncio.get_running_loop().time() < deadline:
            pending = getattr(self.transport, "pending_approvals", {})
            for request_id, request in list(pending.items()):
                params = request.get("params") or {}
                thread_id = str(params.get("threadId") or "")
                if thread_id and thread_id != session.vendor_session_id:
                    continue
                decision = self._isolated_approval_decision(session, request)
                self.isolated_approval_decisions.append(
                    {
                        "request_id": request_id,
                        "method": request.get("method"),
                        "decision": decision,
                    }
                )
                await self.respond_permission(session, request_id, decision)
            notifications = getattr(self.transport, "notifications", [])
            for message in notifications[seen:]:
                params = message.get("params") or {}
                self._collect_isolated_item(session, message)
                turn = params.get("turn") or {}
                if (
                    message.get("method") == "turn/completed"
                    and params.get("threadId") == session.vendor_session_id
                    and str(turn.get("id") or "") == turn_id
                ):
                    return turn
            seen = len(notifications)
            await asyncio.sleep(0.05)
        raise TimeoutError(f"timed out waiting for Codex turn {turn_id}")

    def _collect_isolated_item(self, session: HarnessSession, message: dict[str, Any]) -> None:
        params = message.get("params") or {}
        thread_id = str(params.get("threadId") or "")
        if thread_id and thread_id != session.vendor_session_id:
            return
        item = params.get("item") if isinstance(params.get("item"), dict) else params
        kind = str((item or {}).get("type") or "")
        if kind:
            self.isolated_item_types.append(kind)
        text = (item or {}).get("text")
        if kind == "agentMessage" and isinstance(text, str) and text.strip():
            self.isolated_agent_messages.append(text)

    @staticmethod
    def _isolated_approval_decision(
        session: HarnessSession,
        request: dict[str, Any],
    ) -> str:
        """Fail closed: allow only when every declared path is inside the workspace."""
        params = request.get("params") or {}
        thread_id = str(params.get("threadId") or "")
        if thread_id and thread_id != session.vendor_session_id:
            return "deny"
        try:
            root = Path(session.cwd or "").resolve()
        except (OSError, ValueError):
            return "deny"
        if not session.cwd or not root.is_absolute():
            return "deny"

        declared: list[str] = []
        for key in ("cwd", "path"):
            value = params.get(key)
            if isinstance(value, str) and value:
                declared.append(value)
        for value in params.get("writableRoots") or []:
            if isinstance(value, str) and value:
                declared.append(value)
        for change in params.get("changes") or []:
            if isinstance(change, dict) and isinstance(change.get("path"), str):
                declared.append(change["path"])
        permissions = params.get("permissions") or {}
        if isinstance(permissions, dict):
            for value in permissions.values():
                if isinstance(value, str) and value:
                    declared.append(value)
                elif isinstance(value, list):
                    declared.extend(item for item in value if isinstance(item, str))

        if not declared:
            return "deny"
        try:
            resolved = []
            for value in declared:
                path = Path(value)
                if not path.is_absolute():
                    path = root / path
                resolved.append(path.resolve())
            if not all(path.is_relative_to(root) for path in resolved):
                return "deny"
        except (OSError, ValueError):
            return "deny"
        return "allow"

    async def _ready(self) -> bool:
        if self.transport is None:
            return False
        try:
            await self.transport.ensure_ready()
        except Exception:
            return False
        return True

    async def probe(self) -> AdapterCapabilities:
        connected = await self._ready()
        return AdapterCapabilities(
            observe_messages=connected,
            observe_thought_events=connected,
            observe_tool_calls=connected,
            observe_file_edits=connected,
            observe_shell=connected,
            observe_permissions=connected,
            observe_session_status=connected,
            send_message=connected,
            inject_context=connected,
            approve=connected,
            deny=connected,
            start=connected,
            resume=connected,
            fork=connected,
            control_granularity=ControlGranularity.EVENT if connected else ControlGranularity.SESSION,
            trust_level=0.9 if connected else 0.0,
            support_label=AdapterSupportLabel.DEEP if connected else AdapterSupportLabel.UNAVAILABLE,
            notes=(
                "Official surface: `codex app-server` JSON-RPC "
                "(initialize, thread/start|resume|fork, turn/start, server-initiated approvals). "
                + (
                    "Transport attached and handshake succeeded."
                    if connected
                    else "No live App Server process; label stays Unavailable."
                )
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if not await self._ready():
            return list(self.sessions.values())
        assert self.transport is not None
        try:
            listed = await self.transport.request("thread/list", {"limit": 50})
        except Exception:
            listed = {"data": getattr(self.transport, "threads", [])}
        for thread in _thread_rows(listed):
            vendor_id = str(thread.get("id"))
            session_id = f"codex:{vendor_id}"
            existing = self.sessions.get(session_id)
            status = SessionStatus.WORKING if existing else SessionStatus.DISCOVERED
            raw_status = thread.get("status")
            if isinstance(raw_status, dict) and raw_status.get("type") == "idle":
                status = SessionStatus.IDLE
            self.sessions[session_id] = HarnessSession(
                id=session_id,
                harness_type=HarnessType.CODEX,
                vendor_session_id=vendor_id,
                cwd=thread.get("cwd"),
                project_id=thread.get("projectId") or thread.get("cwd"),
                status=status,
                last_activity=datetime.now(timezone.utc),
                goal_id=existing.goal_id if existing else None,
                metadata={
                    "preview": thread.get("preview"),
                    "name": thread.get("name"),
                    "source": thread.get("source"),
                },
            )
        return list(self.sessions.values())

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        try:
            await self.start_turn(session, text)
        except RuntimeError:
            return False
        return True

    async def respond_permission(self, session: HarnessSession, request_id: str, decision: str) -> bool:
        if self.transport is None:
            return False
        await self.transport.respond_approval(request_id, decision)
        return True

    def normalize_item(self, session: HarnessSession, item: dict[str, Any]) -> HarnessEvent:
        kind = str(item.get("type") or "status")
        mapping = {
            "agentMessage": EventType.AGENT_RESPONSE,
            "userMessage": EventType.USER_PROMPT,
            "commandExecution": EventType.SHELL,
            "fileChange": EventType.FILE_EDIT,
            "todo": EventType.STATUS,
            "reasoning": EventType.AGENT_THOUGHT,
            "contextCompaction": EventType.COMPACTION,
        }
        return HarnessEvent(
            event_id=str(item.get("id") or uuid4().hex),
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.CODEX,
            session_id=session.id,
            event_type=mapping.get(kind, EventType.STATUS),
            phase=EventPhase.DURING,
            message_delta=str(item.get("text") or item.get("command") or ""),
            command=item.get("command"),
            metadata={"raw_type": kind},
        )
