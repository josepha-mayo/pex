from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pex_protocol.actions import InterventionType
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    AutonomyLevel,
    ContextKind,
    EventPhase,
    EventType,
    PolicyVerdict,
    Sensitivity,
    SessionStatus,
    SourceKind,
)
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest, SupervisorResult
from pex_supervisor.loop import _action_from_proposal, decide

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.claims import extract_claims
from pex_bridge.config import Settings
from pex_bridge.context.mesh import build_bundle, item_from_event
from pex_bridge.executor import ActionExecutor
from pex_bridge.intent import classify_prompt
from pex_bridge.policy.engine import PolicyEngine
from pex_bridge.scoring import score_trajectory
from pex_bridge.secrets import redact_mapping, redact_text
from pex_bridge.store import Store, new_id, utcnow

_SKIP_MESSAGE_PREFIXES = ("pex:", "replay (not live")
_HOOK_LABELS = {
    "afterAgentResponse": "agent replied",
    "afterAgentThought": "thinking",
    "beforeShellExecution": "shell",
    "afterShellExecution": "shell finished",
    "preToolUse": "tool",
    "postToolUse": "tool finished",
    "postToolUseFailure": "tool failed",
    "stop": "stopped",
    "sessionStart": "session started",
    "sessionEnd": "session ended",
    "beforeSubmitPrompt": "prompt",
}


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
        existing = await self.store.get_session(session.id)
        if existing:
            if not session.goal_id:
                session.goal_id = existing.goal_id
            if not session.cwd:
                session.cwd = existing.cwd
            if not session.project_id:
                session.project_id = existing.project_id
            session.supervision_paused = existing.supervision_paused
        await self.store.add_event(event)
        session.last_activity = event.ts
        if event.event_type == EventType.STOP:
            session.status = SessionStatus.STOPPED
        elif event.event_type == EventType.ERROR:
            session.status = SessionStatus.ERROR
        else:
            session.status = SessionStatus.WORKING
        await self.store.upsert_session(session)

        project_key = session.project_id or session.cwd
        if project_key:
            item = item_from_event(project_key, session.goal_id, event)
            if item:
                await self.store.add_context(item)

        await self.bus.publish("event", event.model_dump(mode="json"))

        if event.event_type in {EventType.AGENT_RESPONSE, EventType.STOP}:
            await self._maybe_auto_handoff(session, event)

        if session.supervision_paused or self.supervision_paused:
            return None

        goal = await self.store.get_goal(session.goal_id) if session.goal_id else None
        recent = await self.store.recent_events(session.id, self.settings.max_recent_events)
        scores = score_trajectory(recent, goal)
        claims: list[dict] = []
        notes = ""
        if event.event_type == EventType.STOP:
            claims = extract_claims(recent)
            scores.features["claims"] = claims
            if project_key:
                for claim in claims:
                    await self.store.add_context(
                        ContextItem(
                            id=new_id("claim_"),
                            project_id=project_key,
                            goal_id=session.goal_id,
                            kind=ContextKind.CLAIM,
                            content=str(claim.get("statement") or ""),
                            source_refs=[str(claim.get("source_event_id") or event.event_id)],
                            provenance=SourceKind.HARNESS,
                            confidence=float(claim.get("confidence") or 0.5),
                            relevance_tags=[str(claim.get("kind") or "claim"), str(claim.get("polarity") or "")],
                            valid_from=event.ts,
                            sensitivity=Sensitivity.INTERNAL,
                            metadata=claim,
                        )
                    )
            notes = (
                "claims:" + ";".join(f"{c.get('kind')}={c.get('statement')}" for c in claims)
                if claims
                else "no_completion_claims_extracted"
            )
        elif event.event_type == EventType.USER_PROMPT:
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
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(decide, request, self.model),
                timeout=42,
            )
        except TimeoutError:
            result = SupervisorResult(
                action=_action_from_proposal(
                    request,
                    {
                        "type": "NOOP",
                        "rationale": "supervisor_timeout",
                        "evidence": ["supervisor_timeout"],
                    },
                ),
                used_llm=False,
                diagnosis="supervisor_timeout",
            )
        action = result.action
        cleaned_payload, _ = redact_mapping(action.payload)
        action.payload = cleaned_payload or {}
        action.evidence = [redact_text(item)[0] or "" for item in action.evidence]
        result.traces = [redact_text(item)[0] or "" for item in result.traces]
        if event.phase == EventPhase.BEFORE and action.type not in {
            InterventionType.NOOP,
            InterventionType.RESPOND_PERMISSION,
            InterventionType.ASK_HUMAN,
        }:
            action.type = InterventionType.NOOP
            action.payload = {}
            result.action = action
            result.diagnosis = f"{result.diagnosis}:deferred_pre_hook"
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
                claims=claims,
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
            claims=claims,
        )
        await self.store.add_intervention(intervention)
        await self.bus.publish("intervention", intervention.model_dump(mode="json"))
        await self.bus.publish("pet", await self.pet_snapshot())
        return intervention

    async def _maybe_auto_handoff(self, session: HarnessSession, event: HarnessEvent) -> None:
        """Move the smallest useful observed fact to a sibling worker. No copy-paste."""
        content = (event.message_delta or event.command or "").strip()
        project_key = session.project_id or session.cwd
        if len(content) < 40 or not session.goal_id or not project_key:
            return
        if session.supervision_paused or self.supervision_paused:
            return
        goal = await self.store.get_goal(session.goal_id)
        if goal is None:
            return
        siblings = [
            row
            for row in await self.store.list_sessions()
            if row.id != session.id
            and not row.supervision_paused
            and (
                (session.project_id and row.project_id == session.project_id)
                or (session.cwd and row.cwd and row.cwd == session.cwd)
            )
        ]
        if not siblings:
            return
        items = await self.store.list_context(project_key)
        recent = await self.store.recent_events(session.id, 12)
        for target in siblings:
            if not self.cooldowns.allow(f"{session.id}->{target.id}", "auto_handoff", 120):
                continue
            bundle = build_bundle(goal, target, items, recent, [session.id])
            if not bundle.items and not bundle.direct_evidence and not bundle.relevant_artifacts:
                continue
            adapter = self.adapters.for_session(target.id)
            if adapter is None:
                continue
            try:
                ok = await adapter.inject_context(target, bundle)
            except Exception:
                continue
            if not ok:
                continue
            if not target.goal_id:
                target.goal_id = session.goal_id
                await self.store.upsert_session(target)

    def _intervention(
        self,
        *,
        event: HarnessEvent,
        session: HarnessSession,
        result,
        verdict: PolicyVerdict,
        outcome: str,
        action_taken: str,
        claims: list[dict] | None = None,
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
                "claims": claims or [],
            },
        )

    async def refresh_desktop_sessions(self) -> None:
        live = {"working", "verifying", "drifting", "needs_decision", "blocked"}
        idle = {"idle", "discovered"}
        for name in ("cursor", "codex", "grok_bot", "opencode"):
            adapter = self.adapters.get(name)
            if adapter is None:
                continue
            try:
                discovered = await adapter.discover_sessions()
            except Exception:
                continue
            for session in discovered:
                existing = await self.store.get_session(session.id)
                if existing:
                    session.goal_id = existing.goal_id
                    session.supervision_paused = existing.supervision_paused
                    source = (session.metadata or {}).get("source") or (existing.metadata or {}).get("source")
                    if (
                        existing.status.value in live
                        and session.status.value in idle
                        and source != "desktop"
                    ):
                        session.status = existing.status
                        session.last_activity = existing.last_activity
                await self.store.upsert_session(session)

    async def pet_snapshot(self) -> dict:
        sessions = await self.store.list_sessions()
        interventions = await self.store.list_interventions()
        goals = {goal.id: goal for goal in await self.store.list_goals()}
        now = datetime.now(UTC)
        events = await self.store.latest_events(120)
        latest_event: dict[str, HarnessEvent] = {}
        lines_by_session: dict[str, str] = {}
        for event in events:
            latest_event.setdefault(event.session_id, event)
            if event.session_id in lines_by_session:
                continue
            line = visible_event_line(event)
            if line:
                lines_by_session[event.session_id] = line
        live = collapse_live_agents(sessions, now)
        promptable = collapse_promptable_agents(sessions, now)
        working = sum(1 for s in live if s.status.value in {"working", "verifying"})
        drifting = sum(1 for s in live if s.status.value == "drifting")
        blocked = sum(1 for s in live if s.status.value in {"blocked", "error"})
        paused = sum(1 for s in live if s.supervision_paused)
        needs = [s for s in live if s.status == SessionStatus.NEEDS_DECISION]
        last = interventions[0] if interventions else None
        last_message, last_source = await self._latest_visible_line(last)
        headline = f"{working} working · {len(needs)} need you" if working else "quiet"
        if drifting:
            headline += f" · {drifting} drifting"
        if blocked:
            headline += f" · {blocked} blocked"
        if needs:
            headline = f"{needs[0].harness_type} needs a decision"
        sessions_out = []
        live_ids = {item.id for item in live}
        for session in promptable:
            row = session.model_dump(mode="json")
            goal = goals.get(session.goal_id or "")
            row["last_message"] = lines_by_session.get(session.id)
            row["label"] = agent_label(session, goal)
            if session.id in live_ids:
                row["activity"] = activity_phrase(latest_event.get(session.id))
            else:
                row["activity"] = "Ready for a prompt"
            sessions_out.append(row)
        return {
            "headline": headline,
            "working": working,
            "drifting": drifting,
            "blocked": blocked,
            "needs_you": len(needs),
            "paused": paused,
            "last_message": last_message,
            "last_source": last_source,
            "last_action": None
            if last is None
            else {
                "id": last.id,
                "session_id": last.session_id,
                "action": last.action_taken,
                "diagnosis": last.diagnosis,
                "evidence": last.evidence[:6],
                "result": last.result,
                "reversible": last.reversible,
                "confidence": last.confidence,
                "used_llm": (last.metadata or {}).get("used_llm"),
            },
            "sessions": sessions_out,
            "ts": now.isoformat(),
        }

    async def _latest_visible_line(self, last: Intervention | None) -> tuple[str | None, str | None]:
        fallback: tuple[str | None, str | None] = (None, None)
        for event in await self.store.latest_events(80):
            source = event.harness_type.value
            line = visible_event_line(event)
            if not line:
                continue
            text = clip_status_line(event.message_delta)
            if text and not _is_pex_line(text):
                return line, source
            if fallback[0] is None:
                fallback = (line, source)
        if fallback[0]:
            return fallback
        if last is not None:
            text = clip_status_line(last.diagnosis or last.action_taken)
            if text and "deterministic_triage" not in text.lower() and text.lower() not in {"noop", "ok"}:
                return text, last.session_id.split(":", 1)[0]
        return None, None


_LIVE_STATUSES = {"working", "verifying", "drifting", "needs_decision", "blocked"}
_STALE = timedelta(minutes=10)


def agent_group_key(session: HarnessSession) -> str | None:
    vendor = (session.vendor_session_id or "").strip().lower()
    if session.goal_id:
        return f"goal:{session.goal_id}"
    title = str((session.metadata or {}).get("title") or "").strip()
    if title and vendor and vendor not in {"unknown", "desktop"}:
        return f"{session.harness_type.value}:{vendor}"
    cwd = str(session.cwd or session.project_id or "").replace("\\", "/").rstrip("/").lower()
    if cwd.startswith("/c:/"):
        cwd = cwd[1:]
    if cwd:
        return f"{session.harness_type.value}:{cwd}"
    if vendor and vendor not in {"unknown", "desktop"}:
        return f"{session.harness_type.value}:{vendor}"
    if vendor == "desktop":
        return f"{session.harness_type.value}:desktop"
    return None


def is_live_session(session: HarnessSession, now: datetime | None = None) -> bool:
    if session.status.value not in _LIVE_STATUSES:
        return False
    ts = session.last_activity
    if ts is None:
        return False
    now = now or datetime.now(UTC)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return now - ts <= _STALE


def collapse_live_agents(
    sessions: list[HarnessSession], now: datetime | None = None
) -> list[HarnessSession]:
    now = now or datetime.now(UTC)
    chosen: dict[str, HarnessSession] = {}
    for session in sessions:
        if not is_live_session(session, now):
            continue
        key = agent_group_key(session)
        if key is None:
            continue
        prev = chosen.get(key)
        prev_ts = prev.last_activity if prev is not None else None
        cur_ts = session.last_activity
        if prev is None or (cur_ts and (prev_ts is None or cur_ts > prev_ts)):
            chosen[key] = session
    return sorted(
        chosen.values(),
        key=lambda item: item.last_activity or now,
        reverse=True,
    )


_PROMPTABLE_STATUSES = {"idle", "discovered", "stopped"}
_PROMPTABLE_STALE = timedelta(hours=24)


def collapse_promptable_agents(
    sessions: list[HarnessSession], now: datetime | None = None
) -> list[HarnessSession]:
    """Live workers first, then recently seen idle harnesses the user can still prompt."""
    now = now or datetime.now(UTC)
    live = collapse_live_agents(sessions, now)
    ordered = list(live)
    seen = {agent_group_key(session) for session in live}
    extras: list[HarnessSession] = []
    for session in sessions:
        key = agent_group_key(session)
        if key is None or key in seen:
            continue
        if session.status.value not in _PROMPTABLE_STATUSES:
            continue
        ts = session.last_activity
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if now - ts > _PROMPTABLE_STALE:
            continue
        extras.append(session)
        seen.add(key)
    extras.sort(key=lambda item: item.last_activity or now, reverse=True)
    ordered.extend(extras[:12])
    return ordered


def agent_label(session: HarnessSession, goal: object | None = None) -> str:
    title = getattr(goal, "title", None) or (session.metadata or {}).get("title")
    if title:
        return str(title)
    cwd = session.cwd or session.project_id
    if cwd:
        name = Path(str(cwd)).name.strip()
        if name:
            return name
    return str(session.harness_type.value).replace("_", " ")


def activity_phrase(event: HarnessEvent | None) -> str:
    if event is None:
        return "Working"
    if event.event_type == EventType.FILE_EDIT:
        count = len(event.file_paths) or 1
        return f"Edited {count} file" + ("s" if count != 1 else "")
    if event.event_type == EventType.SHELL:
        return "Ran command"
    if event.event_type == EventType.STOP:
        return "Stopped"
    tool = str(event.tool_name or "").lower()
    if tool in {"write", "edit", "searchreplace", "strreplace"}:
        return "Edited 1 file"
    if tool in {"shell", "bash", "powershell"}:
        return "Ran command"
    if tool and tool not in {"unknown", "none"}:
        return f"Using {event.tool_name}"
    line = clip_status_line(event.message_delta, 72)
    if line:
        return line
    return "Working"


def visible_event_line(event: HarnessEvent) -> str | None:
    text = clip_status_line(event.message_delta)
    if text and not _is_pex_line(text):
        return text
    command = clip_status_line(event.command)
    if command:
        return command
    if event.tool_name and str(event.tool_name).lower() not in {"unknown", "none"}:
        return f"{event.harness_type.value} · {event.tool_name}"
    hook = (event.metadata or {}).get("hook_event_name")
    if hook and str(hook).lower() not in {"unknown", "none", "event"}:
        label = _HOOK_LABELS.get(str(hook), str(hook).replace("_", " "))
        return f"{event.harness_type.value} · {label}"
    return None


def clip_status_line(value: str | None, limit: int = 160) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.replace("\n", " ").split())
    if len(cleaned) < 4:
        return None
    if len(cleaned) <= limit:
        return cleaned
    trimmed = cleaned[: limit - 1].rsplit(" ", 1)[0]
    return f"{trimmed}…"


def _is_pex_line(text: str) -> bool:
    lowered = text.lower()
    return any(lowered.startswith(prefix) for prefix in _SKIP_MESSAGE_PREFIXES)
