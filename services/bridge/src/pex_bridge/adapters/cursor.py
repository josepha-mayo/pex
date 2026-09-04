from __future__ import annotations

import hashlib
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from pex_protocol.actions import InterventionType
from pex_protocol.capabilities import (
    AdapterCapabilities,
    AdapterSupportLabel,
    ControlGranularity,
    PermissionResponseMode,
)
from pex_protocol.enums import (
    EventPhase,
    EventType,
    HarnessType,
    PolicyVerdict,
    SessionStatus,
)
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.acp_client import AcpClient, AcpTransport
from pex_bridge.adapters.base import (
    MAX_ADAPTER_MESSAGE_CHARS,
    AdapterMessageResult,
    CursorHookPreparation,
    DeliveryUncertainError,
    HarnessAdapter,
    bounded_adapter_id,
    bounded_adapter_text,
    bounded_observed_mapping,
    bounded_observed_text,
    preserve_bridge_state,
    session_binding_matches,
    validate_cursor_hook_preparation_receipt,
)
from pex_bridge.adapters.desktop import (
    desktop_process_running,
    is_desktop_observe_session,
    upsert_desktop_observe_session,
)
from pex_bridge.adapters.strict_json import strict_json_dumps
from pex_bridge.shell_state import parse_pytest_process_state

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

HOOK_HEARTBEAT_TTL_SECONDS = 30.0
MAX_TRACKED_SESSIONS = 1_024
MAX_INBOX_MESSAGES = 1_000
MAX_AUDIT_RECORDS = 10_000
MAX_FILE_PATHS = 256
MAX_PATH_CHARS = 4_096
MIN_BRIDGE_TOKEN_CHARS = 32
MAX_BRIDGE_TOKEN_CHARS = 512


@dataclass(frozen=True)
class _PendingCursorFollowup:
    text: str
    preparation: CursorHookPreparation


def _cursor_vendor_id(payload: dict) -> str:
    value = bounded_adapter_id(payload.get("conversation_id") or "", field="conversation_id")
    if value and value.lower() not in {"unknown", "desktop", "none"}:
        return value
    # Every installed Cursor agent hook carries conversation_id. Workspace and
    # cwd are shared by concurrent chats and must never become session identity.
    raise ValueError("Cursor hook payload is missing conversation_id")


class CursorAdapter(HarnessAdapter):
    """Cursor via official hooks plus optional ACP control."""

    name = "cursor"

    def __init__(self, acp: AcpClient | None = None, bridge_url: str | None = None) -> None:
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.pending_followups: dict[tuple[str, str], _PendingCursorFollowup] = {}
        self.acp = acp
        self.acp_prompts: list[tuple[str, str]] = []
        self.permission_responses: list[tuple[str, str, str]] = []
        self.bridge_url = _loopback_bridge_url(bridge_url)
        self.isolated_agent_messages: list[str] = []
        self.last_turn_id: str | None = None
        self._last_hook_at: float | None = None
        self._active_hook: ContextVar[tuple[str, str, str] | None] = ContextVar(
            f"pex_cursor_active_hook_{id(self)}", default=None
        )
        self._active_permission_request: ContextVar[tuple[str, str] | None] = ContextVar(
            f"pex_cursor_permission_{id(self)}", default=None
        )
        self._delivery_channel: ContextVar[str] = ContextVar(
            f"pex_cursor_delivery_{id(self)}", default="hook"
        )

    def attach_acp(self, transport: AcpTransport) -> None:
        self.acp = AcpClient(transport)

    def _hook_live(self) -> bool:
        return (
            self._last_hook_at is not None
            and time.monotonic() - self._last_hook_at <= HOOK_HEARTBEAT_TTL_SECONDS
        )

    async def probe(self) -> AdapterCapabilities:
        acp_ready = False
        if self.acp is not None:
            try:
                if not self.acp.ready:
                    await self.acp.handshake()
                await self.acp.list_sessions()
                acp_ready = True
            except Exception:
                acp_ready = False
        hook_live = self._hook_live()
        desktop = desktop_process_running("Cursor.exe")
        active_hook = self._active_hook.get()
        synchronous_hook_control = self._delivery_channel.get() != "observe"
        active_stop = bool(
            synchronous_hook_control and hook_live and active_hook and active_hook[1] == "stop"
        )
        active_permission = bool(
            synchronous_hook_control and hook_live and self._active_permission_request.get()
        )
        available = acp_ready or hook_live or desktop
        label = (
            AdapterSupportLabel.STRONG
            if active_stop or active_permission
            else AdapterSupportLabel.BASIC
            if acp_ready
            else AdapterSupportLabel.OBSERVE_ONLY
            if hook_live or desktop
            else AdapterSupportLabel.UNAVAILABLE
        )
        return AdapterCapabilities(
            observe_messages=hook_live,
            observe_thought_events=hook_live,
            observe_tool_calls=hook_live,
            observe_file_edits=hook_live,
            observe_shell=hook_live,
            observe_context_compaction=hook_live,
            observe_tokens=False,
            observe_permissions=hook_live,
            observe_session_status=available,
            send_message=acp_ready or active_stop,
            inject_context=acp_ready or active_stop,
            approve=active_permission,
            deny=active_permission,
            permission_response_mode=(
                PermissionResponseMode.INLINE
                if active_permission
                else PermissionResponseMode.NONE
            ),
            start=False,
            stop=False,
            resume=acp_ready or active_stop,
            fork=False,
            summarize=False,
            modify_config=False,
            modify_system_instructions=False,
            modify_tools=False,
            modify_mcp=False,
            modify_model=False,
            modify_reasoning_effort=False,
            focus_ui=available,
            control_granularity=(
                ControlGranularity.EVENT
                if active_stop or active_permission
                else ControlGranularity.SESSION
            ),
            trust_level=(
                0.8 if hook_live else 0.6 if acp_ready else 0.4 if desktop else 0.0
            ),
            support_label=label,
            notes=(
                "Cursor desktop via an already-running Cursor.exe. "
                "Official ~/.cursor/hooks.json is optional control, not required to list "
                "an open session, and is never auto-installed on discover. "
                "A recent hook heartbeat proves observation of tools/stops; hook control is "
                "advertised only while the matching stop or permission hook is active. "
                "stop may return followup_message and beforeShellExecution returns "
                "permission allow/deny/ask. Optional ACP is capability-gated and never "
                "auto-installed or auto-authenticated."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        if self.acp is not None:
            try:
                listed = await self.acp.list_sessions()
            except Exception:
                listed = []
            for item in listed:
                if len(self.sessions) >= MAX_TRACKED_SESSIONS:
                    break
                try:
                    vendor_id = bounded_adapter_id(item.get("sessionId") or "", field="sessionId")
                except ValueError:
                    continue
                session_id = f"cursor:{vendor_id}"
                existing = self.sessions.get(session_id)
                cwd = _optional_bounded_path(item.get("cwd"))
                goal_id, paused = preserve_bridge_state(
                    existing,
                    cwd=cwd,
                    project_id=cwd,
                )
                self.sessions[session_id] = HarnessSession(
                    id=session_id,
                    harness_type=HarnessType.CURSOR,
                    vendor_session_id=vendor_id,
                    cwd=cwd,
                    project_id=cwd,
                    status=SessionStatus.IDLE,
                    last_activity=datetime.now(UTC),
                    goal_id=goal_id,
                    supervision_paused=paused,
                    metadata={
                        "source": "acp",
                        "title": bounded_observed_text(
                            item.get("title"), field="Cursor session title"
                        ),
                    },
                )
        upsert_desktop_observe_session(
            self.sessions,
            harness=HarnessType.CURSOR,
            process="Cursor.exe",
            skip_if_other_sessions=True,
        )
        return list(self.sessions.values())

    def upsert_from_hook(self, payload: dict) -> HarnessSession:
        self._last_hook_at = time.monotonic()
        vendor_id = _cursor_vendor_id(payload)
        session_id = f"cursor:{vendor_id}"
        existing = self.sessions.get(session_id)
        roots_value = payload.get("workspace_roots")
        roots = roots_value if isinstance(roots_value, list) else []
        root = _optional_bounded_path(roots[0]) if roots else None
        cwd = root or _optional_bounded_path(payload.get("cwd"))
        project_id = root or cwd
        if existing is None and len(self.sessions) >= MAX_TRACKED_SESSIONS:
            raise ValueError("Cursor session safety bound reached")
        goal_id, paused = preserve_bridge_state(
            existing,
            cwd=cwd,
            project_id=project_id,
        )
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.CURSOR,
            vendor_session_id=vendor_id,
            project_id=project_id,
            cwd=cwd,
            model=bounded_observed_text(
                payload.get("model_id") or payload.get("model"),
                field="Cursor model",
                max_chars=512,
            ),
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
            metadata={
                "cursor_version": bounded_observed_text(
                    payload.get("cursor_version"),
                    field="Cursor version",
                    max_chars=512,
                ),
                "source": "hook",
                "title": ((existing.metadata or {}).get("title") if existing else None),
            },
            goal_id=goal_id,
            supervision_paused=paused,
        )
        self.sessions[session_id] = session
        self.inbox.setdefault(session_id, [])
        return session

    def normalize_hook(self, payload: dict, session: HarnessSession) -> HarnessEvent:
        bound = self.sessions.get(session.id)
        if not session_binding_matches(bound, session, harness_type=HarnessType.CURSOR):
            raise ValueError("Cursor hook session binding mismatch")
        if payload.get("conversation_id") and _cursor_vendor_id(payload) != bound.vendor_session_id:
            raise ValueError("Cursor hook conversation binding mismatch")
        session = bound
        self._active_hook.set(None)
        hook_name = bounded_adapter_id(
            payload.get("hook_event_name") or payload.get("hook") or "unknown",
            field="hook event name",
        )
        event_type = HOOK_EVENT_MAP.get(hook_name, EventType.STATUS)
        phase = (
            EventPhase.BEFORE if str(hook_name).startswith(("before", "pre")) else EventPhase.AFTER
        )
        if hook_name in {"stop", "sessionEnd"}:
            phase = EventPhase.TERMINAL
        command = None
        tool_input = bounded_observed_mapping(payload.get("tool_input"))
        if tool_input is not None:
            command = tool_input.get("command")
        command = command or payload.get("command") or payload.get("shell_command")
        files: list[str] = []
        if payload.get("file_path"):
            files.append(_bounded_path(payload["file_path"]))
        extras = payload.get("file_paths") or payload.get("paths") or []
        if not isinstance(extras, list):
            extras = []
        for extra in extras[:MAX_FILE_PATHS]:
            if extra:
                files.append(_bounded_path(extra))
        agent_hooks = {
            "afterAgentResponse",
            "afterAgentThought",
            "beforeSubmitPrompt",
            "stop",
            "sessionEnd",
        }
        message = None
        if hook_name in agent_hooks:
            message = (
                payload.get("prompt")
                or payload.get("text")
                or payload.get("agent_message")
                or payload.get("completion")
                or payload.get("content")
                or payload.get("last_assistant_message")
            )
        tool_name = payload.get("tool_name") or payload.get("tool") or payload.get("toolName")
        if not command and tool_input is not None:
            command = tool_input.get("command") or tool_input.get("cmd")
        process_state = None
        error = None
        if hook_name in {"afterShellExecution", "postToolUse", "postToolUseFailure"}:
            process_state = parse_pytest_process_state(str(command or ""), payload)
            error = _optional_bounded_text(
                payload.get("error") or payload.get("stderr"), field="hook error"
            )
            if hook_name == "postToolUseFailure" and not error:
                error = _optional_bounded_text(
                    payload.get("output") or payload.get("message"),
                    field="hook failure",
                ) or "tool failed"
        event_id = _cursor_event_id(session.id, payload)
        raw_generation_id = payload.get("generation_id")
        generation_id = (
            bounded_adapter_id(raw_generation_id, field="Cursor generation id")
            if raw_generation_id is not None and raw_generation_id != ""
            else None
        )
        if hook_name in {
            "beforeShellExecution",
            "preToolUse",
            "beforeMCPExecution",
            "beforeReadFile",
        }:
            self._active_permission_request.set((session.id, event_id))
        else:
            self._active_permission_request.set(None)
        event = HarnessEvent(
            event_id=event_id,
            ts=datetime.now(UTC),
            harness_type=HarnessType.CURSOR,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=phase,
            message_delta=_optional_bounded_text(message, field="hook message"),
            tool_name=_optional_bounded_text(tool_name, field="hook tool name"),
            tool_input=tool_input,
            command=_optional_bounded_text(command, field="hook command"),
            file_paths=files,
            error=error,
            process_state=process_state,
            approval_request={"hook": hook_name}
            if hook_name in {"beforeShellExecution", "preToolUse"}
            else None,
            metadata={
                "hook_event_name": hook_name,
                "cursor_version": bounded_observed_text(
                    payload.get("cursor_version"),
                    field="Cursor version",
                    max_chars=512,
                ),
                "conversation_id": session.vendor_session_id,
                "generation_id": generation_id,
                "tool_status": bounded_observed_text(
                    payload.get("status"), field="Cursor tool status", max_chars=512
                ),
            },
        )
        self._active_hook.set((session.id, str(hook_name), event.event_id))
        return event

    async def send_message(
        self, session: HarnessSession, text: str, attachments=None
    ) -> bool | AdapterMessageResult | CursorHookPreparation:
        bound = self.sessions.get(session.id)
        if not session_binding_matches(bound, session, harness_type=HarnessType.CURSOR):
            return False
        if is_desktop_observe_session(session) or is_desktop_observe_session(bound):
            return False
        try:
            cleaned = bounded_adapter_text(text).strip()
        except ValueError:
            return False
        if session.id != f"cursor:{session.vendor_session_id}":
            return False
        session = bound
        if self.acp is not None:
            inbox = self.inbox.setdefault(session.id, [])
            if len(inbox) >= MAX_INBOX_MESSAGES:
                return False
            try:
                await self.acp.activate(
                    session.vendor_session_id,
                    str(session.cwd or session.project_id or ""),
                )
                await self.acp.prompt(session.vendor_session_id, cleaned)
            except DeliveryUncertainError:
                raise
            except Exception:
                return False
            _append_bounded(
                self.acp_prompts,
                (session.vendor_session_id, cleaned),
                MAX_AUDIT_RECORDS,
            )
        elif self._delivery_channel.get() == "observe":
            # JSONL observe ingest is not a waiting stop hook. Claiming
            # followup_message here would record SEND_NUDGE as sent while the
            # helper already fail-opened with {}.
            return False
        elif self.bridge_url:
            inbox = self.inbox.setdefault(session.id, [])
            if len(inbox) >= MAX_INBOX_MESSAGES:
                return False
            upstream_effect_id = (
                str(attachments.get("operator_effect_id") or "").strip()
                if isinstance(attachments, dict)
                else ""
            )
            if not _post_bridge_followup(
                self.bridge_url,
                session.id,
                cleaned,
                upstream_effect_id=upstream_effect_id or None,
            ):
                return False
        else:
            # This only prepares text for the exact active stop event. A later
            # stdout flush proves local hook delivery, not Cursor acceptance or
            # display.
            active_hook = self._active_hook.get()
            if (
                not self._hook_live()
                or active_hook is None
                or active_hook[:2] != (session.id, "stop")
            ):
                return False
            trigger_event_id = active_hook[2]
            pending_key = (session.id, trigger_event_id)
            if pending_key in self.pending_followups:
                return False
            if len(self.pending_followups) >= MAX_TRACKED_SESSIONS:
                return False
            preparation = CursorHookPreparation(
                preparation_id=f"cursor-prep-{uuid4().hex}",
                trigger_event_id=trigger_event_id,
                vendor_session_id=session.vendor_session_id,
                message_sha256=hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
            )
            self.pending_followups[pending_key] = _PendingCursorFollowup(
                text=cleaned,
                preparation=preparation,
            )
            return preparation
        inbox.append(cleaned)
        return True

    async def wait_for_turn_completion(
        self, session: HarnessSession, turn_id: str, timeout: float = 600
    ):
        """Followups land on the next stop hook. Do not spawn a worker turn."""
        _ = (session, timeout)
        return {
            "status": "delivery_accepted_completion_unobserved",
            "id": turn_id,
            "completion_observed": False,
        }

    async def continue_or_resume(
        self, session: HarnessSession, message: str | None = None
    ) -> bool | AdapterMessageResult | CursorHookPreparation:
        if not message or not str(message).strip():
            return False
        return await self.send_message(session, message)

    async def respond_permission(
        self,
        session: HarnessSession,
        request_id: str,
        decision: str,
    ) -> bool:
        """Record the decision returned synchronously by the active Cursor hook."""
        if (
            decision not in {"allow", "deny"}
            or not self._hook_live()
            or self._active_permission_request.get() != (session.id, request_id)
            or not session_binding_matches(
                self.sessions.get(session.id), session, harness_type=HarnessType.CURSOR
            )
            or session.id != f"cursor:{session.vendor_session_id}"
        ):
            return False
        try:
            request_id = bounded_adapter_id(request_id, field="permission request id")
        except ValueError:
            return False
        _append_bounded(
            self.permission_responses,
            (session.id, request_id, decision),
            MAX_AUDIT_RECORDS,
        )
        return True

    async def focus_ui(self, session: HarnessSession) -> bool:
        from pex_bridge.adapters.winfocus import focus_harness

        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.CURSOR
        ):
            return False
        if focus_harness("cursor"):
            return True
        return _focus_cursor_window(session.vendor_session_id or "Cursor")

    def consume_followup(
        self,
        session_id: str,
        *,
        trigger_event_id: str | None = None,
    ) -> str | None:
        """Discard the active pending packet without exposing unverified text."""

        active_hook = self._active_hook.get()
        self._active_hook.set(None)
        event_id = trigger_event_id
        if event_id is None and active_hook is not None and active_hook[0] == session_id:
            event_id = active_hook[2]
        if event_id is not None:
            try:
                event_id = bounded_adapter_id(
                    event_id,
                    field="Cursor follow-up trigger event id",
                )
            except ValueError:
                return None
            self.pending_followups.pop((session_id, event_id), None)
        return None

    def consume_verified_stop_followup(
        self,
        session: HarnessSession,
        intervention: Intervention | None,
    ) -> str | None:
        """Consume, but expose only an exact prepared hook response.

        Pending text is single-use even when validation fails. This prevents a
        stale or policy-denied proposal from leaking into a later Cursor stop
        response merely because a model proposed the same action type.
        """

        active_hook = self._active_hook.get()
        self._active_hook.set(None)
        if (
            active_hook is None
            or active_hook[:2] != (session.id, "stop")
            or not session_binding_matches(
                self.sessions.get(session.id), session, harness_type=HarnessType.CURSOR
            )
        ):
            return None
        pending = self.pending_followups.pop((session.id, active_hook[2]), None)
        if pending is None:
            return None
        if (
            pending.preparation.trigger_event_id != active_hook[2]
            or pending.preparation.vendor_session_id != session.vendor_session_id
        ):
            return None
        text = pending.text.strip()
        if not text or text.startswith("PEX:"):
            return None
        if intervention is None:
            return None
        action = intervention.proposed_action
        prepared_actions = {
            InterventionType.SEND_NUDGE,
            InterventionType.CONTINUE_SESSION,
            InterventionType.INJECT_CONTEXT,
            InterventionType.REQUEST_VERIFICATION,
        }
        payload = action.payload if isinstance(action.payload, dict) else {}
        raw_receipt = (intervention.metadata or {}).get("hook_preparation_receipt")
        try:
            receipt = validate_cursor_hook_preparation_receipt(
                raw_receipt,
                session=session,
                preparation_id=pending.preparation.preparation_id,
                trigger_event_id=active_hook[2],
                message_sha256=pending.preparation.message_sha256,
            )
        except (TypeError, ValueError):
            return None
        if (
            action.type not in prepared_actions
            or intervention.session_id != session.id
            or intervention.goal_id is None
            or intervention.goal_id != session.goal_id
            or intervention.trigger != EventType.STOP.value
            or action.session_id != session.id
            or action.goal_id != session.goal_id
            or intervention.action_taken != action.type.value
            or intervention.policy_verdict != PolicyVerdict.ALLOW
            or intervention.result != "hook_followup_prepared_delivery_uncertain"
            or not any(str(item).strip() for item in intervention.evidence)
            or str(payload.get("text") or "").strip() != text
            or hashlib.sha256(text.encode("utf-8")).hexdigest()
            != receipt["message_sha256"]
            or (intervention.metadata or {}).get("worker_delivery_receipt") is not None
        ):
            return None
        return text

    async def apply_overlay(self, session: HarnessSession, overlay) -> bool:
        # Official hooks cannot change Cursor tools, MCP, or model. Do not
        # smuggle the overlay in as extra worker prompt text.
        _ = (session, overlay)
        return False

    async def revert_overlay(self, overlay_id: str, rollback: dict | None = None) -> bool:
        # Cursor hooks cannot mutate configuration, so there is no truthful
        # adapter-level rollback operation to report as delivered.
        return False


_INTERNAL_BRIDGE_TOKEN = ""


def set_internal_bridge_token(value: object) -> None:
    """Retain the bridge-owned bearer in-process without worker-visible files/env."""

    global _INTERNAL_BRIDGE_TOKEN
    _INTERNAL_BRIDGE_TOKEN = _valid_bridge_token(value)


def _bridge_token() -> str:
    return _INTERNAL_BRIDGE_TOKEN


def _cursor_event_id(session_id: str, payload: dict) -> str:
    canonical = strict_json_dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"{session_id}:hook:{digest}"


def _post_bridge_followup(
    bridge_url: str,
    session_id: str,
    text: str,
    *,
    upstream_effect_id: str | None = None,
) -> bool:
    """Queue the isolated supervisor nudge on this desktop's running bridge."""
    safe_bridge_url = _loopback_bridge_url(bridge_url)
    if safe_bridge_url is None:
        return False
    token = _bridge_token()
    request_digest = hashlib.sha256(
        strict_json_dumps(
            [
                "pex.cursor.bridge-followup.v1",
                upstream_effect_id or "legacy-without-effect-id",
                session_id,
                text,
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    payload = strict_json_dumps(
        {
            "idempotency_key": f"cursor-followup:{request_digest}",
            "text": text,
        }
    ).encode("utf-8")
    request = Request(
        f"{safe_bridge_url}/v1/sessions/{quote(session_id, safe='')}/message",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            return 200 <= int(response.status) < 300
    except HTTPError:
        # A concrete HTTP status is an authoritative rejection, not an
        # ambiguous transport failure after a possibly accepted mutation.
        return False
    except (URLError, TimeoutError, OSError) as exc:
        raise DeliveryUncertainError(
            "Cursor bridge follow-up may have been accepted without a receipt"
        ) from exc


def _loopback_bridge_url(bridge_url: str | None) -> str | None:
    raw = str(bridge_url or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
        _ = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return None
    return raw.rstrip("/")


def _valid_bridge_token(value: object) -> str:
    token = str(value or "").strip()
    if (
        not MIN_BRIDGE_TOKEN_CHARS <= len(token) <= MAX_BRIDGE_TOKEN_CHARS
        or any(ord(char) < 0x21 or ord(char) > 0x7E for char in token)
    ):
        return ""
    return token


def _optional_bounded_text(value: object, *, field: str) -> str | None:
    return bounded_observed_text(value, field=field, max_chars=MAX_ADAPTER_MESSAGE_CHARS)


def _bounded_path(value: object) -> str:
    return bounded_adapter_text(value, field="path", max_chars=MAX_PATH_CHARS)


def _optional_bounded_path(value: object) -> str | None:
    if value is None or value == "":
        return None
    return _bounded_path(value)


def _append_bounded(items: list, item, limit: int) -> None:
    if len(items) >= limit:
        del items[: len(items) - limit + 1]
    items.append(item)


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
