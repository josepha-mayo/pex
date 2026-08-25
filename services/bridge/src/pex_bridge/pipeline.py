from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from pex_protocol.actions import InterventionType
from pex_protocol.enums import AutonomyLevel, EventType, PolicyVerdict, SessionStatus
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest
from pex_supervisor.loop import decide

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.context.mesh import item_from_event
from pex_bridge.executor import ActionExecutor
from pex_bridge.intent import classify_prompt
from pex_bridge.policy.engine import PolicyEngine
from pex_bridge.scoring import score_trajectory
from pex_bridge.secrets import redact_mapping, redact_text
from pex_bridge.store import Store, new_id, utcnow


def _redact_event(event: HarnessEvent) -> None:
    for field in (
        "command",
        "diff_ref",
        "error",
        "message_delta",
        "raw_event_ref",
        "tool_output_ref",
    ):
        cleaned, _ = redact_text(getattr(event, field))
        setattr(event, field, cleaned)
    for field in (
        "approval_request",
        "metadata",
        "process_state",
        "token_usage",
        "tool_input",
    ):
        cleaned, _ = redact_mapping(getattr(event, field))
        setattr(event, field, cleaned)
    event.file_paths = [redact_text(path)[0] or "" for path in event.file_paths]


class Cooldowns:
    def __init__(self) -> None:
        self._last: dict[tuple[str, str], float] = {}

    def allow(self, session_id: str, action_type: str, seconds: int) -> bool:
        key = (session_id, action_type)
        now = time.monotonic()
        last = self._last.get(key, 0.0)
        if now - last < seconds:
            return False
        self._last[key] = now
        return True


class Pipeline:
    def __init__(
        self,
        store: Store,
        adapters: AdapterRegistry,
        bus: EventBus,
        settings: Settings,
        model=None,
    ) -> None:
        self.store = store
        self.adapters = adapters
        self.bus = bus
        self.settings = settings
        self.model = model
        self.policy = PolicyEngine(AutonomyLevel(settings.autonomy))
        self.executor = ActionExecutor(adapters, store)
        self.cooldowns = Cooldowns()
        self.supervision_paused = False

    async def ingest_event(
        self, event: HarnessEvent, session: HarnessSession
    ) -> Intervention | None:
        _redact_event(event)
        await self.store.add_event(event)
        session.last_activity = event.ts
        if event.event_type == EventType.STOP:
            session.status = SessionStatus.STOPPED
        elif event.event_type == EventType.ERROR:
            session.status = SessionStatus.ERROR
        else:
            session.status = SessionStatus.WORKING
        await self.store.upsert_session(session)

        if session.project_id:
            item = item_from_event(session.project_id, session.goal_id, event)
            if item:
                await self.store.add_context(item)

        await self.bus.publish("event", event.model_dump(mode="json"))

        if session.supervision_paused or self.supervision_paused:
            return None

        goal = await self.store.get_goal(session.goal_id) if session.goal_id else None
        recent = await self.store.recent_events(session.id, self.settings.max_recent_events)
        scores = score_trajectory(recent, goal)
        notes = ""
        if event.event_type == EventType.USER_PROMPT:
            classification = classify_prompt(goal, event.message_delta or "")
            notes = classification.value
        request = SupervisorRequest(
            session=session,
            goal=goal,
            event=event,
            recent_events=recent,
            scores=scores,
            autonomy=self.settings.autonomy,
            notes=notes,
        )
        result = await asyncio.to_thread(decide, request, self.model)
        action = result.action
        cleaned_payload, _ = redact_mapping(action.payload)
        action.payload = cleaned_payload or {}
        action.evidence = [redact_text(item)[0] or "" for item in action.evidence]
        result.traces = [redact_text(item)[0] or "" for item in result.traces]
        if action.requires_capability:
            caps = session.capabilities or {}
            if caps and not caps.get(action.requires_capability, False):
                action.type = InterventionType.NOTIFY
                action.payload["limitation"] = action.requires_capability

        if action.type != InterventionType.NOOP and not self.cooldowns.allow(
            session.id, action.type.value, action.cooldown_seconds
        ):
            intervention = self._intervention(
                event=event,
                session=session,
                result=result,
                verdict=PolicyVerdict.DENY,
                outcome="suppressed_by_cooldown",
                action_taken="SUPPRESSED_COOLDOWN",
            )
            await self.store.add_intervention(intervention)
            await self.bus.publish("intervention", intervention.model_dump(mode="json"))
            return intervention

        command = event.command or str(action.payload.get("command") or "")
        verdict = self.policy.decide(action, command=command)
        outcome = await self.executor.execute(action, verdict)
        intervention = self._intervention(
            event=event,
            session=session,
            result=result,
            verdict=verdict,
            outcome=outcome,
            action_taken=action.type.value,
        )
        await self.store.add_intervention(intervention)
        await self.bus.publish("intervention", intervention.model_dump(mode="json"))
        await self.bus.publish("pet", await self.pet_snapshot())
        return intervention

    def _intervention(
        self,
        *,
        event: HarnessEvent,
        session: HarnessSession,
        result,
        verdict: PolicyVerdict,
        outcome: str,
        action_taken: str,
    ) -> Intervention:
        action = result.action
        return Intervention(
            id=new_id("int_"),
            session_id=session.id,
            goal_id=session.goal_id,
            trigger=event.event_type.value,
            evidence=action.evidence,
            diagnosis=result.diagnosis,
            proposed_action=action,
            confidence=action.confidence,
            risk=action.risk.value,
            reversible=action.reversible,
            authority_required=action.authority_required.value,
            action_taken=action_taken,
            policy_verdict=verdict,
            result=outcome,
            created_at=utcnow(),
            metadata={
                "used_llm": result.used_llm,
                "traces": result.traces,
                "inference_request_id": result.inference_request_id,
                "model_name": result.model_name,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "backend": result.backend,
                "latency_ms": result.latency_ms,
            },
        )

    async def pet_snapshot(self) -> dict:
        sessions = await self.store.list_sessions()
        interventions = await self.store.list_interventions()
        working = sum(1 for s in sessions if s.status.value in {"working", "verifying"})
        drifting = sum(1 for s in sessions if s.status.value == "drifting")
        paused = sum(1 for s in sessions if s.supervision_paused)
        needs = [s for s in sessions if s.status == SessionStatus.NEEDS_DECISION]
        last = interventions[0] if interventions else None
        headline = f"{working} working"
        if drifting:
            headline += f" · {drifting} drifting"
        if needs:
            headline = f"{needs[0].harness_type} needs a decision"
        elif working == 0 and sessions:
            headline = "idle"
        return {
            "headline": headline,
            "working": working,
            "drifting": drifting,
            "needs_you": len(needs),
            "paused": paused,
            "last_action": None
            if last is None
            else {
                "id": last.id,
                "session_id": last.session_id,
                "action": last.action_taken,
                "diagnosis": last.diagnosis,
                "evidence": last.evidence[:6],
                "result": last.result,
                "used_llm": (last.metadata or {}).get("used_llm"),
            },
            "sessions": [s.model_dump(mode="json") for s in sessions],
            "ts": datetime.now(UTC).isoformat(),
        }
