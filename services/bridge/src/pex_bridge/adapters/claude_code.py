"""Claude Code via official Agent SDK / settings.json hooks.

Strong: stdin JSON hooks (PreToolUse, Stop, UserPromptSubmit, PermissionRequest,
PreCompact). Responses use Claude's hookSpecificOutput contract. PEX does not
spawn Claude sessions.
"""

from __future__ import annotations

import hashlib
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from pex_protocol.actions import InterventionType
from pex_protocol.capabilities import (
    AdapterCapabilities,
    AdapterSupportLabel,
    ControlGranularity,
    PermissionResponseMode,
)
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import (
    MAX_ADAPTER_MESSAGE_CHARS,
    AdapterMessageResult,
    HarnessAdapter,
    bounded_adapter_id,
    bounded_adapter_text,
    bounded_observed_mapping,
    bounded_observed_text,
    preserve_bridge_state,
    session_binding_matches,
    verified_inline_permission_outcome,
)
from pex_bridge.adapters.desktop import (
    is_desktop_observe_session,
    matching_desktop_image,
    upsert_desktop_observe_session,
)
from pex_bridge.adapters.strict_json import strict_json_dumps

HOOK_EVENT_MAP = {
    "PreToolUse": EventType.TOOL_CALL,
    "PostToolUse": EventType.TOOL_RESULT,
    "PostToolUseFailure": EventType.TOOL_FAILURE,
    "PermissionRequest": EventType.PERMISSION_REQUEST,
    "UserPromptSubmit": EventType.USER_PROMPT,
    "Stop": EventType.STOP,
    "PreCompact": EventType.COMPACTION,
    "SessionStart": EventType.SESSION_START,
    "SessionEnd": EventType.SESSION_END,
    "SubagentStart": EventType.SESSION_START,
    "SubagentStop": EventType.STOP,
}

HOOK_HEARTBEAT_TTL_SECONDS = 30.0
MAX_TRACKED_SESSIONS = 1_024
MAX_INBOX_MESSAGES = 1_000
MAX_HOOK_RECEIPTS = 10_000
MAX_PATH_CHARS = 4_096


class ClaudeCodeAdapter(HarnessAdapter):
    name = "claude_code"
    accepts_hooks = True

    def __init__(self) -> None:
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []
        self.pending_followups: dict[str, str] = {}
        self._last_hook_at: float | None = None
        self._active_hook: ContextVar[tuple[str, str] | None] = ContextVar(
            f"pex_claude_active_hook_{id(self)}", default=None
        )

    def _hook_live(self) -> bool:
        return (
            self._last_hook_at is not None
            and time.monotonic() - self._last_hook_at <= HOOK_HEARTBEAT_TTL_SECONDS
        )

    async def probe(self) -> AdapterCapabilities:
        hook_live = self._hook_live()
        active = self._active_hook.get()
        active_stop = bool(hook_live and active and active[1] == "Stop")
        active_permission = bool(
            hook_live and active and active[1] in {"PreToolUse", "PermissionRequest"}
        )
        desktop = matching_desktop_image(("claude.exe",)) is not None
        available = hook_live or desktop
        return AdapterCapabilities(
            observe_messages=hook_live,
            observe_tool_calls=hook_live,
            observe_session_status=available,
            observe_permissions=hook_live,
            observe_context_compaction=hook_live,
            send_message=active_stop,
            inject_context=active_stop,
            approve=active_permission,
            deny=active_permission,
            permission_response_mode=(
                PermissionResponseMode.INLINE
                if active_permission
                else PermissionResponseMode.NONE
            ),
            resume=active_stop,
            modify_system_instructions=False,
            focus_ui=available,
            control_granularity=(
                ControlGranularity.EVENT
                if active_stop or active_permission
                else ControlGranularity.SESSION
            ),
            trust_level=0.82 if hook_live else 0.4 if desktop else 0.0,
            support_label=(
                AdapterSupportLabel.STRONG
                if hook_live
                else AdapterSupportLabel.OBSERVE_ONLY
                if desktop
                else AdapterSupportLabel.UNAVAILABLE
            ),
            notes=(
                "Official Claude Code hooks from settings.json / Agent SDK. "
                "User-started sessions attach through those hooks without restarting "
                "Claude Code. Hooks are never auto-installed on discover. "
                "A recent hook heartbeat proves observation; control is advertised only "
                "during the matching active Stop or permission hook. "
                "PEX returns negotiated permission decisions and may block Stop with a "
                "reason to continue the same session; it does not own the session."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        upsert_desktop_observe_session(
            self.sessions,
            harness=HarnessType.CLAUDE_CODE,
            process="claude.exe",
            skip_if_other_sessions=True,
        )
        return list(self.sessions.values())

    async def focus_ui(self, session: HarnessSession) -> bool:
        from pex_bridge.adapters.winfocus import focus_harness

        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.CLAUDE_CODE
        ):
            return False
        return focus_harness("claude_code")

    def ingest_hook(self, payload: dict) -> HarnessSession:
        self._last_hook_at = time.monotonic()
        vendor_id = bounded_adapter_id(
            payload.get("session_id")
            or payload.get("conversation_id")
            or payload.get("sessionId")
            or "",
            field="Claude Code session_id",
        )
        session_id = f"claude_code:{vendor_id}"
        existing = self.sessions.get(session_id)
        roots = payload.get("cwd") or payload.get("workspace_roots") or []
        cwd = (
            roots[0]
            if isinstance(roots, list) and roots
            else (roots if isinstance(roots, str) else None)
        )
        cwd = _optional_bounded_path(cwd)
        project_id = cwd
        if existing is None and len(self.sessions) >= MAX_TRACKED_SESSIONS:
            raise ValueError("Claude Code session safety bound reached")
        goal_id, paused = preserve_bridge_state(
            existing,
            cwd=cwd,
            project_id=project_id,
        )
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.CLAUDE_CODE,
            vendor_session_id=vendor_id,
            cwd=cwd,
            project_id=project_id,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(UTC),
            goal_id=goal_id,
            supervision_paused=paused,
            metadata={
                "hook": bounded_observed_text(
                    payload.get("hook_event_name"),
                    field="Claude hook name",
                    max_chars=512,
                ),
                "source": "claude_hook",
            },
        )
        self.sessions[session_id] = session
        if len(self.hooks) >= MAX_HOOK_RECEIPTS:
            del self.hooks[: len(self.hooks) - MAX_HOOK_RECEIPTS + 1]
        self.hooks.append(
            {
                "session_id": session_id,
                "hook_event_name": bounded_observed_text(
                    payload.get("hook_event_name"),
                    field="Claude hook name",
                    max_chars=512,
                ),
                "received_at": datetime.now(UTC).isoformat(),
            }
        )
        self.inbox.setdefault(session_id, [])
        return session

    def normalize_hook(self, payload: dict, session: HarnessSession) -> HarnessEvent:
        bound = self.sessions.get(session.id)
        if not session_binding_matches(bound, session, harness_type=HarnessType.CLAUDE_CODE):
            raise ValueError("Claude Code hook session binding mismatch")
        payload_session_id = (
            payload.get("session_id") or payload.get("conversation_id") or payload.get("sessionId")
        )
        if payload_session_id and bounded_adapter_id(
            payload_session_id, field="Claude Code session_id"
        ) != bound.vendor_session_id:
            raise ValueError("Claude Code hook payload session mismatch")
        session = bound
        hook_name = bounded_adapter_id(
            payload.get("hook_event_name") or payload.get("hook") or "unknown",
            field="hook event name",
        )
        self._active_hook.set((session.id, hook_name))
        event_type = HOOK_EVENT_MAP.get(hook_name, EventType.STATUS)
        tool_input = bounded_observed_mapping(payload.get("tool_input"))
        return HarnessEvent(
            event_id=_hook_event_id(session.id, payload),
            ts=datetime.now(UTC),
            harness_type=HarnessType.CLAUDE_CODE,
            session_id=session.id,
            event_type=event_type,
            phase=EventPhase.TERMINAL if hook_name in {"Stop", "SessionEnd"} else EventPhase.BEFORE,
            message_delta=_optional_bounded_text(
                payload.get("prompt")
                or payload.get("text")
                or payload.get("reason")
                or payload.get("last_assistant_message"),
                field="hook message",
            ),
            tool_name=_optional_bounded_text(payload.get("tool_name"), field="hook tool name"),
            tool_input=tool_input,
            command=_optional_bounded_text(
                (tool_input or {}).get("command") if tool_input else payload.get("command"),
                field="hook command",
            ),
            metadata={"hook_event_name": hook_name},
        )

    def emit_status(self, session: HarnessSession, message: str) -> HarnessEvent:
        return self.normalize_hook({"hook_event_name": "unknown", "text": message}, session)

    async def send_message(
        self, session: HarnessSession, text: str, attachments=None
    ) -> bool | AdapterMessageResult:
        bound = self.sessions.get(session.id)
        if (
            not session_binding_matches(bound, session, harness_type=HarnessType.CLAUDE_CODE)
            or is_desktop_observe_session(session)
            or is_desktop_observe_session(bound)
            or not self._hook_live()
            or self._active_hook.get() != (session.id, "Stop")
        ):
            return False
        try:
            cleaned = bounded_adapter_text(text).strip()
        except ValueError:
            return False
        inbox = self.inbox.setdefault(session.id, [])
        if len(inbox) >= MAX_INBOX_MESSAGES:
            return False
        if (
            session.id not in self.pending_followups
            and len(self.pending_followups) >= MAX_TRACKED_SESSIONS
        ):
            return False
        inbox.append(cleaned)
        self.pending_followups[session.id] = cleaned
        return AdapterMessageResult(
            accepted=True,
            vendor_session_id=session.vendor_session_id,
            vendor_turn_id=f"claude-stop-{len(inbox):04d}",
        )

    def consume_followup(self, session_id: str) -> str | None:
        self._active_hook.set(None)
        return self.pending_followups.pop(session_id, None)

    def hook_response(
        self, session: HarnessSession, payload: dict, intervention: Intervention | None
    ) -> dict[str, Any]:
        if not session_binding_matches(
            self.sessions.get(session.id), session, harness_type=HarnessType.CLAUDE_CODE
        ):
            return {}
        raw_hook_name = payload.get("hook_event_name")
        if not isinstance(raw_hook_name, str):
            return {}
        try:
            hook_name = bounded_adapter_id(raw_hook_name, field="Claude hook name")
        except ValueError:
            return {}
        if hook_name == "PreToolUse":
            if not self._hook_live() or self._active_hook.get() != (session.id, hook_name):
                return {}
            self._active_hook.set(None)
            decision = verified_inline_permission_outcome(
                session,
                intervention,
                expected_trigger=EventType.TOOL_CALL,
                expected_request_id=_hook_event_id(session.id, payload),
            )
            if decision not in {"allow", "deny"}:
                # No completed inline response means Claude Code keeps its
                # configured permission behavior. In particular, a PEX policy
                # rejection is not an active denial of the worker's request.
                return {}
            reason = _bounded_response_text(
                intervention.diagnosis or f"PEX policy {decision}"
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        if hook_name == "PermissionRequest":
            if not self._hook_live() or self._active_hook.get() != (session.id, hook_name):
                return {}
            self._active_hook.set(None)
            behavior = verified_inline_permission_outcome(
                session,
                intervention,
                expected_trigger=EventType.PERMISSION_REQUEST,
                expected_request_id=_hook_event_id(session.id, payload),
            )
            if behavior not in {"allow", "deny"}:
                # Omitting a decision preserves Claude Code's native prompt.
                return {}
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": behavior},
                }
            }
        if hook_name == "Stop":
            active_hook = self._active_hook.get()
            followup = self.consume_followup(session.id)
            if _evidenced_stop_delivery(session, active_hook, followup, intervention):
                cleaned = str(followup).strip()
                # Claude's Stop hook continues a turn only via the top-level
                # block decision. additionalContext is not a Stop output.
                return {"decision": "block", "reason": cleaned}
            return {}
        if hook_name in {"UserPromptSubmit", "PreCompact"}:
            if not self._hook_live() or self._active_hook.get() != (session.id, hook_name):
                return {}
            self._active_hook.set(None)
            text = _claude_additional_context(hook_name, intervention, session.id)
            if not text:
                return {}
            return {
                "hookSpecificOutput": {
                    "hookEventName": hook_name,
                    "additionalContext": text,
                }
            }
        # ASK_HUMAN records a PEX escalation; it is not authorization to reject
        # a prompt already submitted by the human to Claude Code.
        return {}


def _hook_event_id(session_id: str, payload: dict) -> str:
    canonical = strict_json_dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return f"{session_id}:hook:{digest}"


def _optional_bounded_text(value: object, *, field: str) -> str | None:
    return bounded_observed_text(value, field=field, max_chars=MAX_ADAPTER_MESSAGE_CHARS)


def _optional_bounded_path(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return None
    return bounded_adapter_text(value, field="path", max_chars=MAX_PATH_CHARS)


def _bounded_response_text(value: object) -> str:
    return bounded_observed_text(value, field="hook response", max_chars=4_096) or "PEX policy"


def _claude_additional_context(
    hook_name: str,
    intervention: Intervention | None,
    session_id: str,
) -> str:
    """Map a completed intervention onto Claude's additionalContext contract."""

    if intervention is None or intervention.session_id != session_id:
        return ""
    if intervention.policy_verdict != PolicyVerdict.ALLOW:
        return ""
    action = intervention.proposed_action
    if hook_name == "UserPromptSubmit":
        if action.type != InterventionType.ANNOTATE:
            return ""
    elif hook_name == "PreCompact":
        if action.type not in {
            InterventionType.ANNOTATE,
            InterventionType.SEND_NUDGE,
            InterventionType.INJECT_CONTEXT,
        }:
            return ""
    else:
        return ""
    text = str(action.payload.get("text") or action.payload.get("user_message") or "").strip()
    if not text or text.startswith("PEX:"):
        return ""
    return _bounded_response_text(text)


def _evidenced_stop_delivery(
    session: HarnessSession,
    active_hook: tuple[str, str] | None,
    followup: str | None,
    intervention: Intervention | None,
) -> bool:
    """Emit a Stop block only for this hook's completed, auditable delivery."""
    cleaned = str(followup or "").strip()
    if (
        active_hook != (session.id, "Stop")
        or not cleaned
        or cleaned.startswith("PEX:")
        or intervention is None
        or intervention.session_id != session.id
        or intervention.trigger != EventType.STOP.value
        or intervention.policy_verdict != PolicyVerdict.ALLOW
        or not any(str(item).strip() for item in intervention.evidence)
    ):
        return False
    action = intervention.proposed_action
    action_name = str(intervention.action_taken or "")
    expected_results = {
        "SEND_NUDGE": "sent",
        "INJECT_CONTEXT": "sent",
        "CONTINUE_SESSION": "continued",
        "REQUEST_VERIFICATION": "verification_requested",
    }
    return (
        action_name in expected_results
        and action.type.value == action_name
        and action.session_id == session.id
        and intervention.result == expected_results[action_name]
        and str(action.payload.get("text") or "").strip() == cleaned
    )
