from __future__ import annotations

from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.context import ContextBundle
from pex_protocol.enums import PolicyVerdict, SessionStatus
from pex_protocol.overlay import Overlay

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.store import Store, utcnow


class ActionExecutor:
    def __init__(self, adapters: AdapterRegistry, store: Store) -> None:
        self.adapters = adapters
        self.store = store

    async def execute(self, action: ProposedAction, verdict: PolicyVerdict) -> str:
        if verdict == PolicyVerdict.DENY:
            return "denied_by_policy"
        if verdict == PolicyVerdict.ASK_HUMAN:
            session = await self.store.get_session(action.session_id)
            if session:
                session.status = SessionStatus.NEEDS_DECISION
                await self.store.upsert_session(session)
            return "awaiting_human"

        adapter = self.adapters.for_session(action.session_id)
        session = await self.store.get_session(action.session_id)
        if adapter is None or session is None:
            return "missing_session_or_adapter"

        text = str(action.payload.get("text") or "")
        if action.type == InterventionType.NOOP:
            return "noop"
        if action.type in {InterventionType.SEND_NUDGE, InterventionType.INJECT_CONTEXT}:
            if not text.strip():
                return "send_skipped_empty"
            ok = await adapter.send_message(session, text)
            return "sent" if ok else "send_failed"
        if action.type == InterventionType.REQUEST_VERIFICATION:
            if not text.strip():
                return "verification_skipped_no_specific_probe"
            ok = await adapter.send_message(session, text)
            return "verification_requested" if ok else "verification_failed"
        if action.type == InterventionType.FRESH_HANDOFF:
            raw = action.payload.get("bundle")
            if isinstance(raw, dict):
                ok = await adapter.inject_context(session, ContextBundle.model_validate(raw))
            else:
                if not text.strip():
                    return "handoff_skipped_no_specific_context"
                ok = await adapter.send_message(session, text)
            return "handoff_injected" if ok else "handoff_failed"
        if action.type == InterventionType.CONTINUE_SESSION:
            ok = await adapter.continue_or_resume(session, text or None)
            return "continued" if ok else "continue_failed"
        if action.type == InterventionType.RESPOND_PERMISSION:
            request_id = str(action.payload.get("request_id") or "")
            decision = str(action.payload.get("decision") or "").lower()
            if not request_id or decision not in {"allow", "deny"}:
                return "permission_invalid"
            ok = await adapter.respond_permission(session, request_id, decision)
            return f"permission_{decision}" if ok else "permission_failed"
        if action.type == InterventionType.APPLY_OVERLAY:
            raw_overlay = action.payload.get("overlay")
            if not isinstance(raw_overlay, dict):
                return "overlay_invalid"
            overlay = Overlay.model_validate(raw_overlay)
            overlay.applied_at = utcnow()
            await self.store.upsert_overlay(overlay)
            ok = await adapter.apply_overlay(session, overlay)
            return "overlay_applied" if ok else "overlay_failed"
        if action.type == InterventionType.REVERT_OVERLAY:
            overlay_id = str(action.payload.get("overlay_id") or "")
            if not overlay_id:
                return "overlay_revert_invalid"
            overlay = await self.store.get_overlay(overlay_id)
            if overlay:
                overlay.reverted_at = utcnow()
                await self.store.upsert_overlay(overlay)
            ok = await adapter.revert_overlay(overlay_id)
            return "overlay_reverted" if ok else "overlay_revert_failed"
        if action.type == InterventionType.FOCUS_UI:
            ok = await adapter.focus_ui(session)
            return "focused" if ok else "focus_failed"
        if action.type == InterventionType.ASK_HUMAN:
            session.status = SessionStatus.NEEDS_DECISION
            await self.store.upsert_session(session)
            return "escalated"
        if action.type == InterventionType.ANNOTATE:
            return "annotated"
        if action.type == InterventionType.NOTIFY:
            return "notified"
        return f"unhandled_{action.type}"
