"""Claude Code via official Agent SDK / settings.json hooks.

Strong: stdin JSON hooks (PreToolUse, Stop, UserPromptSubmit, PermissionRequest,
PreCompact). Responses use Claude's hookSpecificOutput contract. PEX does not
spawn Claude sessions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pex_protocol.capabilities import AdapterCapabilities, AdapterSupportLabel, ControlGranularity
from pex_protocol.enums import EventPhase, EventType, HarnessType, PolicyVerdict, SessionStatus
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession

from pex_bridge.adapters.base import HarnessAdapter

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


class ClaudeCodeAdapter(HarnessAdapter):
    name = "claude_code"

    def __init__(self) -> None:
        self.sessions: dict[str, HarnessSession] = {}
        self.inbox: dict[str, list[str]] = {}
        self.hooks: list[dict] = []
        self.pending_followups: dict[str, str] = {}

    async def probe(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            observe_messages=True,
            observe_tool_calls=True,
            observe_session_status=True,
            observe_permissions=True,
            observe_context_compaction=True,
            send_message=True,
            inject_context=True,
            approve=True,
            deny=True,
            resume=True,
            modify_system_instructions=True,
            control_granularity=ControlGranularity.EVENT,
            trust_level=0.82,
            support_label=AdapterSupportLabel.STRONG,
            notes=(
                "Official Claude Code hooks from settings.json / Agent SDK. "
                "PEX returns permissionDecision and Stop additionalContext; it does not own the session."
            ),
        )

    async def discover_sessions(self) -> list[HarnessSession]:
        return list(self.sessions.values())

    def ingest_hook(self, payload: dict) -> HarnessSession:
        vendor_id = str(
            payload.get("session_id")
            or payload.get("conversation_id")
            or payload.get("sessionId")
            or uuid4().hex[:12]
        )
        session_id = f"claude_code:{vendor_id}"
        existing = self.sessions.get(session_id)
        roots = payload.get("cwd") or payload.get("workspace_roots") or []
        cwd = roots[0] if isinstance(roots, list) and roots else (roots if isinstance(roots, str) else None)
        session = HarnessSession(
            id=session_id,
            harness_type=HarnessType.CLAUDE_CODE,
            vendor_session_id=vendor_id,
            cwd=cwd,
            status=SessionStatus.WORKING,
            last_activity=datetime.now(timezone.utc),
            goal_id=existing.goal_id if existing else None,
            metadata={"hook": payload.get("hook_event_name")},
        )
        self.sessions[session_id] = session
        self.hooks.append(payload)
        self.inbox.setdefault(session_id, [])
        return session

    def normalize_hook(self, payload: dict, session: HarnessSession) -> HarnessEvent:
        hook_name = str(payload.get("hook_event_name") or payload.get("hook") or "unknown")
        event_type = HOOK_EVENT_MAP.get(hook_name, EventType.STATUS)
        tool_input = payload.get("tool_input") if isinstance(payload.get("tool_input"), dict) else None
        return HarnessEvent(
            event_id=uuid4().hex,
            ts=datetime.now(timezone.utc),
            harness_type=HarnessType.CLAUDE_CODE,
            session_id=session.id,
            event_type=event_type,
            phase=EventPhase.TERMINAL if hook_name in {"Stop", "SessionEnd"} else EventPhase.BEFORE,
            message_delta=payload.get("prompt") or payload.get("text") or payload.get("reason"),
            tool_name=payload.get("tool_name"),
            tool_input=tool_input,
            command=(tool_input or {}).get("command") if tool_input else payload.get("command"),
            metadata={"hook_event_name": hook_name},
        )

    def emit_status(self, session: HarnessSession, message: str) -> HarnessEvent:
        return self.normalize_hook({"hook_event_name": "unknown", "text": message}, session)

    async def send_message(self, session: HarnessSession, text: str, attachments=None) -> bool:
        self.inbox.setdefault(session.id, []).append(text)
        self.pending_followups[session.id] = text
        return True

    def consume_followup(self, session_id: str) -> str | None:
        return self.pending_followups.pop(session_id, None)

    def hook_response(self, session: HarnessSession, payload: dict, intervention: Intervention | None) -> dict[str, Any]:
        hook_name = str(payload.get("hook_event_name") or "")
        if hook_name == "PreToolUse":
            decision = "allow"
            reason = "policy allow"
            if intervention and intervention.policy_verdict == PolicyVerdict.DENY:
                decision = "deny"
                reason = intervention.diagnosis or "policy deny"
            elif intervention and intervention.policy_verdict == PolicyVerdict.ASK_HUMAN:
                decision = "ask"
                reason = intervention.diagnosis or "needs a human decision"
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": decision,
                    "permissionDecisionReason": reason,
                }
            }
        if hook_name == "PermissionRequest":
            behavior = "allow"
            if intervention and intervention.policy_verdict in {PolicyVerdict.DENY, PolicyVerdict.ASK_HUMAN}:
                behavior = "deny"
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": behavior},
                }
            }
        if hook_name == "Stop":
            followup = self.consume_followup(session.id)
            if not followup and intervention and intervention.action_taken in {"CONTINUE_SESSION", "SEND_NUDGE"}:
                followup = str(intervention.proposed_action.payload.get("text") or intervention.diagnosis)
            if followup:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "Stop",
                        "additionalContext": followup,
                    }
                }
            return {}
        if hook_name == "UserPromptSubmit" and intervention and intervention.action_taken == "ASK_HUMAN":
            return {"decision": "block", "reason": intervention.diagnosis or "Conflicts with persistent goal."}
        return {}
