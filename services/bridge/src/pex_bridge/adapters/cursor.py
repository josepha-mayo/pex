from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventPhase, EventType, HarnessType, SessionStatus
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.acp_client import AcpClient, AcpTransport
from pex_bridge.adapters.base import HarnessAdapter

HOOK_EVENT_MAP = {
    "sessionStart": EventType.SESSION_START,
    "sessionEnd": EventType.SESSION_END,
    "preToolUse": EventType.TOOL_CALL,
    "postToolUse": EventType.TOOL_RESULT,
    "postToolUseFailure": EventType.TOOL_FAILURE,
    "beforeShellExecution": EventType.SHELL,
    "afterShellExecution": EventType.SHELL,
    "beforeMCPExecution": EventType.TOOL_CALL,
    "afterMCPExecution": EventType.TOOL_RESULT,
    "beforeReadFile": EventType.FILE_READ,
    "afterFileEdit": EventType.FILE_EDIT,
    "beforeSubmitPrompt": EventType.USER_PROMPT,
    "preCompact": EventType.COMPACTION,
    "stop": EventType.STOP,
    "afterAgentResponse": EventType.AGENT_RESPONSE,
    "afterAgentThought": EventType.AGENT_THOUGHT,
    "subagentStart": EventType.SESSION_START,
    "subagentStop": EventType.STOP,
}


def _cursor_vendor_id(payload: dict) -> str:
    for key in ("conversation_id", "session_id", "composer_id", "chat_id"):
        value = str(payload.get(key) or "").strip()
        if value and value.lower() not in {"unknown", "desktop", "none"}:
            return value
    roots = payload.get("workspace_roots") or []
    cwd = str(roots[0] if roots else payload.get("cwd") or "").strip()
    if cwd:
        return f"cwd:{cwd}"
    return "desktop"


class CursorAdapter(HarnessAdapter):
    """Cursor via official hooks plus optional ACP control."""

    name = "cursor"

    def __init__(self, acp: AcpClient | None = None) -> None:
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.pending_followups: dict[str, str] = {}
        self.acp = acp
        self.acp_prompts: list[tuple[str, str]] = []

    def attach_acp(self, transport: AcpTransport) -> None:
        self.acp = AcpClient(transport)

    async def probe(self) -> AdapterCapabilities:
        acp_ready = False
        if self.acp is not None:
            try:
                if not self.acp.ready:
                    await self.acp.handshake()
                acp_ready = True
            except Exception:
                acp_ready = False
        label = AdapterSupportLabel.DEEP if acp_ready else AdapterSupportLabel.STRONG
        return AdapterCapabilities(
            observe_messages=True,
            observe_thought_events=True,
            observe_tool_calls=True,
            observe_file_edits=True,
            observe_shell=True,
            observe_context_compaction=True,
            observe_tokens=False,
            observe_permissions=True,
            observe_session_status=True,
            send_message=True,
            inject_context=True,
            approve=True,
            deny=True,
            start=acp_ready,
            stop=False,
            resume=True,
            fork=False,
            summarize=False,
            modify_config=False,
            modify_system_instructions=True,
            modify_tools=False,
            modify_mcp=False,
            modify_model=False,
            modify_reasoning_effort=False,
            focus_ui=True,
            control_granularity=ControlGranularity.EVENT,
            trust_level=0.85 if acp_ready else 0.8,
            support_label=label,
            notes=(
                "Cursor desktop via official ~/.cursor/hooks.json (primary path). "
                "stop may return followup_message; beforeShellExecution returns "
                "permission allow/deny/ask. ACP CLI is optional extra and is never auto-installed."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.acp is not None:
            try:
                listed = await self.acp.list_sessions()
            except Exception:
                listed = []
            for item in listed:
                vendor_id = str(item.get("sessionId") or "")
                if not vendor_id:
                    continue
                session_id = f"cursor:{vendor_id}"
                existing = self.sessions.get(session_id)
                self.sessions[session_id] = HarnessSession(
                    id=session_id,
                    harness_type=HarnessType.CURSOR,
                    vendor_session_id=vendor_id,
                    cwd=item.get("cwd"),
                    project_id=item.get("cwd"),
                    status=SessionStatus.IDLE,
                    last_activity=datetime.now(timezone.utc),
                    goal_id=existing.goal_id if existing else None,
                    supervision_paused=existing.supervision_paused if existing else False,
                    metadata={"source": "acp", "title": item.get("title")},
                )
        return list(self.sessions.values())

    def upsert_from_hook(self, payload: dict) -> HarnessSession:
        vendor_id = _cursor_vendor_id(payload)
        session_id = f"cursor:{vendor_id}"
        existing = self.sessions.get(session_id)
        roots = payload.get("workspace_roots") or []
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.CURSOR,
            vendor_session_id=vendor_id,
            project_id=str(roots[0]) if roots else None,
            cwd=str(roots[0]) if roots else payload.get("cwd"),
            model=payload.get("model_id") or payload.get("model"),
            status=SessionStatus.WORKING,
            last_activity=datetime.now(timezone.utc),
            metadata={
                "transcript_path": payload.get("transcript_path"),
                "cursor_version": payload.get("cursor_version"),
                "source": "hook",
                "title": ((existing.metadata or {}).get("title") if existing else None),
            },
            goal_id=existing.goal_id if existing else None,
            supervision_paused=existing.supervision_paused if existing else False,
        )
        self.sessions[session_id] = session
        self.inbox.setdefault(session_id, [])
        return session

    def normalize_hook(self, payload: dict, session: HarnessSession) -> HarnessEvent:
        hook_name = payload.get("hook_event_name") or payload.get("hook") or "unknown"
        event_type = HOOK_EVENT_MAP.get(hook_name, EventType.STATUS)
        phase = EventPhase.BEFORE if str(hook_name).startswith(("before", "pre")) else EventPhase.AFTER
        if hook_name in {"stop", "sessionEnd"}:
            phase = EventPhase.TERMINAL
        command = None
        tool_input = payload.get("tool_input")
        if isinstance(tool_input, dict):
            command = tool_input.get("command")
        command = command or payload.get("command") or payload.get("shell_command")
        files: list[str] = []
        if payload.get("file_path"):
            files.append(payload["file_path"])
        message = (
            payload.get("prompt")
            or payload.get("text")
            or payload.get("agent_message")
            or payload.get("completion")
            or payload.get("content")
            or payload.get("last_assistant_message")
            or payload.get("output")
        )
        tool_name = payload.get("tool_name") or payload.get("tool") or payload.get("toolName")
        if not command and isinstance(tool_input, dict):
            command = tool_input.get("command") or tool_input.get("cmd")
        return HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.CURSOR,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=phase,
            message_delta=message,
            tool_name=tool_name,
            tool_input=tool_input if isinstance(tool_input, dict) else None,
            command=command,
            file_paths=files,
            approval_request={"hook": hook_name} if hook_name in {"beforeShellExecution", "preToolUse"} else None,
            metadata={"hook_event_name": hook_name, "raw": {k: payload[k] for k in payload if k != "raw"}},
        )

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        self.inbox.setdefault(session.id, []).append(text)
        self.pending_followups[session.id] = text
        if self.acp is not None:
            try:
                await self.acp.prompt(session.vendor_session_id, text)
                self.acp_prompts.append((session.vendor_session_id, text))
            except Exception:
                # Hook follow-up remains the durable path if ACP is down.
                return True
        return True

    async def continue_or_resume(self, session: HarnessSession, message: str | None = None) -> bool:
        if not message or not str(message).strip():
            return False
        return await self.send_message(session, message)

    async def focus_ui(self, session: HarnessSession) -> bool:
        from pex_bridge.adapters.winfocus import focus_harness

        if focus_harness("cursor"):
            return True
        return _focus_cursor_window(session.vendor_session_id or "Cursor")

    def consume_followup(self, session_id: str) -> str | None:
        return self.pending_followups.pop(session_id, None)

    async def apply_overlay(self, session: HarnessSession, overlay) -> bool:
        text = overlay.diff.system_instructions or overlay.reason
        return await self.send_message(
            session,
            f"Session overlay ({overlay.id}): {text}\nFollow this for the rest of the session unless reverted.",
        )

    async def revert_overlay(self, overlay_id: str) -> bool:
        for session in self.sessions.values():
            await self.send_message(
                session,
                f"PEX overlay {overlay_id} reverted. Return to the persistent goal and default tools.",
            )
            return True
        return True


def _focus_cursor_window(hint: str) -> bool:
    try:
        import win32con
        import win32gui
    except ImportError:
        return False

    matches: list[int] = []
    needle = (hint or "Cursor").lower()

    def _enum(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if "cursor" in title.lower() and (needle in title.lower() or needle in {"cursor", ""}):
            matches.append(hwnd)

    win32gui.EnumWindows(_enum, None)
    if not matches:
        return False
    hwnd = matches[0]
    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)
    return True
