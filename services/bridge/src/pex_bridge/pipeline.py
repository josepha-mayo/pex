from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from contextlib import nullcontext
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.capabilities import AdapterCapabilities
from pex_protocol.context import (
    ClaimVerificationRequest,
    ContextBundle,
    ContextHandoffRequest,
    ContextItem,
    HumanDecisionRequest,
    ProgressReport,
)
from pex_protocol.enums import (
    Authority,
    AutonomyLevel,
    ContextKind,
    DecisionSource,
    DecisionStatus,
    EventPhase,
    EventType,
    HarnessType,
    PolicyVerdict,
    Sensitivity,
    SessionStatus,
    SourceKind,
)
from pex_protocol.goal import Decision, Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest, SupervisorResult
from pex_protocol.verification import (
    EvidenceGatheringReceipt,
    EvidenceGatheringState,
    VerificationBackendKind,
    VerificationExecutionReceipt,
    VerificationExecutionResult,
    VerificationProbe,
    VerificationProbeKind,
    classify_pytest_invocation,
)
from pex_supervisor.background import confirm_abandoned_background, find_abandoned_background
from pex_supervisor.drift import duplicate_sibling_work, goal_path_names
from pex_supervisor.evidence_tools import workspace_evidence_guard
from pex_supervisor.loop import (
    _action_from_proposal,
    _preserve_deterministic_truth,
    needs_semantic_inference,
)
from pex_supervisor.planner import plan_deterministic
from pex_supervisor.verify import (
    missing_required_files,
    required_files,
    required_verification_probe_kind,
    verification_probe_targets,
    verify_claims,
)
from pex_supervisor.workspace import snapshot

from pex_bridge.adapters import AdapterRegistry
from pex_bridge.adapters.base import (
    bounded_adapter_id,
    resolve_adapter_message_result,
    validate_cursor_hook_preparation_receipt,
    validate_worker_delivery_receipt_binding,
)
from pex_bridge.adapters.desktop import is_desktop_observe_session
from pex_bridge.adapters.opencode_outcomes import event_matches_opencode_delivery
from pex_bridge.agentcore import (
    AgentCoreDeliveryUncertainError,
    SupervisorRouter,
    compact_workspace_evidence,
)
from pex_bridge.bus import EventBus
from pex_bridge.channels import ChannelHub
from pex_bridge.claims import extract_claims
from pex_bridge.config import Settings
from pex_bridge.context.health import assess_context_health
from pex_bridge.context.mesh import build_bundle, item_from_event, items_from_verification
from pex_bridge.executor import (
    HANDOFF_ADAPTER_TIMEOUT_SECONDS,
    ActionExecutionResult,
    ActionExecutor,
    ClaimedMainEffect,
    _WorkspaceDispatchRefused,
)
from pex_bridge.fingerprints import fingerprint_score_features
from pex_bridge.handoff_views import handoff_bundle_receipt, public_intervention
from pex_bridge.intent import PromptClass, lint_prompt
from pex_bridge.mcp_auth import (
    MCP_REPORT_PROGRESS_SCOPE,
    MCP_REQUEST_DECISION_SCOPE,
    MCP_VERIFY_CLAIM_SCOPE,
    MCPPrincipal,
)
from pex_bridge.policy.engine import PolicyEngine
from pex_bridge.scoring import score_trajectory
from pex_bridge.secrets import redact_mapping, redact_text
from pex_bridge.speculative import (
    cheap_competing_approaches,
    compare_probe_results,
    probe_already_running,
    probe_instructions,
    probe_result_from_stop,
    speculative_pair,
)
from pex_bridge.store import (
    EVENT_EFFECT_TERMINAL_STATES,
    EVENT_PROCESSING_TERMINAL_STATES,
    MCP_REPORT_PROGRESS_TOOL,
    MCP_REQUEST_DECISION_TOOL,
    MCP_VERIFY_CLAIM_TOOL,
    ProjectIdentityBlockedError,
    Store,
    claim_verification_request_fingerprint,
    event_semantic_hash,
    event_semantic_payload,
    human_decision_logical_key,
    human_decision_request_fingerprint,
    new_id,
    reported_progress_request_fingerprint,
    stable_event_artifact_id,
    stable_operator_artifact_id,
    stable_operator_effect_id,
    utcnow,
)
from pex_bridge.supervisor_context import build_supervisor_context
from pex_bridge.workspace_access import workspace_read_check
from pex_bridge.workspace_binding import WorkspaceAuthorityError, require_workspace_sample


class _WorkspacePlannerNotStarted(WorkspaceAuthorityError):
    """Internal proof that the scheduled provider invocation never began."""


_HANDOFF_SIGNAL = re.compile(
    r"\b(?:artifact|blocked|checkpoint|constraint|decision|dependency|error|failed|"
    r"failure|handoff|missing|passed|unresolved|verified)\b",
    re.I,
)
_COMPLETION_SIGNAL = re.compile(
    r"\b(?:all tests passed|complete[ds]?|done|implemented|shipped|verified)\b",
    re.I,
)
DESKTOP_DISCOVERY_TIMEOUT_SECONDS = 3.0
DESKTOP_REFRESH_MIN_INTERVAL_SECONDS = 8.0
DESKTOP_REFRESH_ADAPTERS = (
    "cursor",
    "codex",
    "opencode",
    "hermes",
    "claude_code",
)
PET_TRANSIENT_SECONDS = 12.0
_CONTEXT_ROUTING_METADATA_KEYS = {"active_files", "current_task", "task_phase"}
_DURABLE_SESSION_METADATA_KEYS = {
    *_CONTEXT_ROUTING_METADATA_KEYS,
    "context_health_signals",
    "speculative",
    "speculative_result",
    "human_decision_attention",
}
_CONTEXT_TASK_CHARS = 2_000
_CONTEXT_ACTIVE_FILES = 32
_MAX_EVENT_PLANNING_SNAPSHOT_BYTES = 2 * 1024 * 1024
logger = logging.getLogger(__name__)
_HANDOFF_COOLDOWN_SECONDS = 120

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


def _auto_handoff_idempotency_key(
    *,
    event_id: str,
    source_session_id: str,
    target_session_id: str,
    goal_id: str,
    token_budget: int,
    item_ids: list[str],
) -> str:
    """Derive one stable automatic handoff request from immutable identities."""

    selected = sorted(set(item_ids))
    if not selected or len(selected) != len(item_ids):
        raise ValueError("automatic handoff item identities are invalid")
    payload = {
        "schema": "pex.auto-handoff-request.v1",
        "event_id": event_id,
        "source_session_id": source_session_id,
        "target_session_id": target_session_id,
        "goal_id": goal_id,
        "token_budget": token_budget,
        "item_ids": selected,
    }
    digest = hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return f"auto-handoff-{digest}"


def _bounded_utf8(value: object, limit: int) -> str:
    """Bound an observed payload by bytes without manufacturing replacement text."""

    raw = str(value or "").encode("utf-8")
    if len(raw) <= limit:
        return raw.decode("utf-8")
    return raw[:limit].decode("utf-8", "ignore")


def _exact_action_probe(
    action: ProposedAction,
    gathering: EvidenceGatheringReceipt,
) -> VerificationProbe | None:
    """Return the probe only when the full action payload is bridge-minted."""

    if gathering.probe is None:
        return None
    raw = action.payload.get("probe")
    if not isinstance(raw, dict):
        return None
    try:
        candidate = VerificationProbe.model_validate(raw)
    except (TypeError, ValueError):
        return None
    return candidate if candidate == gathering.probe else None


def _matching_pytest_execution(
    prior: Intervention,
    session: HarnessSession,
    event: HarnessEvent,
    gathering: EvidenceGatheringReceipt,
) -> VerificationExecutionReceipt | None:
    """Return a terminal receipt only for the requested, observed pytest process.

    A narration, an unrelated shell command, or a partial process snapshot is not
    execution evidence. The request is correlated by session, time, probe kind,
    action payload, and the first later exact pytest command with a terminal exit.
    """

    probe = gathering.probe
    if (
        gathering.state != EvidenceGatheringState.ATTEMPTED
        or probe is None
        or probe.kind != VerificationProbeKind.PYTEST
        or prior.proposed_action.type != InterventionType.REQUEST_VERIFICATION
        or prior.policy_verdict != PolicyVerdict.ALLOW
        or event.event_type != EventType.SHELL
        or event.session_id != probe.session_id
        or event.harness_type != probe.harness_type
        or session.harness_type != probe.harness_type
        or session.goal_id != probe.goal_id
        or prior.goal_id != probe.goal_id
        or str((prior.metadata or {}).get("trigger_event_id") or "") != probe.request_event_id
        or event.ts < prior.created_at
        or not session.cwd
        or not _same_project(session.cwd, probe.cwd)
        or not _same_project(session.project_id or session.cwd, probe.project_id)
        or (event.project_id is not None and not _same_project(event.project_id, probe.project_id))
    ):
        return None
    if _exact_action_probe(prior.proposed_action, gathering) is None:
        return None
    command = (event.command or "").strip()
    invocation = classify_pytest_invocation(command)
    if invocation is None or not probe.matches_pytest_invocation(invocation):
        return None
    state = event.process_state if isinstance(event.process_state, dict) else {}
    pytest_state = state.get("pytest")
    if not isinstance(pytest_state, dict):
        return None
    ok = pytest_state.get("ok")
    exit_code = pytest_state.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        return None
    if ok is True and exit_code == 0:
        result = VerificationExecutionResult.PASSED
    elif ok is False and exit_code != 0:
        result = VerificationExecutionResult.FAILED
    else:
        return None
    failure = pytest_state.get("failed")
    return VerificationExecutionReceipt(
        backend=VerificationBackendKind.HARNESS,
        policy_verdict=PolicyVerdict.ALLOW,
        source_event_id=event.event_id,
        observed_at=event.ts,
        observed_command=command,
        cwd=probe.cwd,
        process_started=True,
        exit_code=exit_code,
        result=result,
        output=_bounded_utf8(pytest_state.get("output"), probe.output_limit_bytes),
        failure_node=(str(failure)[:4_096] if failure else None),
    )


_TYPED_PROCESS_STATE_KEYS = {
    VerificationProbeKind.FILE_COUNT: "file_count",
    VerificationProbeKind.ARTIFACT_TAIL: "artifact_tail",
    VerificationProbeKind.COMMAND_EXIT: "command_exit",
    VerificationProbeKind.SERVICE_HEALTH: "service_health",
}


def _matching_typed_execution(
    prior: Intervention,
    session: HarnessSession,
    event: HarnessEvent,
    gathering: EvidenceGatheringReceipt,
) -> VerificationExecutionReceipt | None:
    """Return a terminal receipt only for the requested, observed typed process."""

    probe = gathering.probe
    process_key = _TYPED_PROCESS_STATE_KEYS.get(probe.kind) if probe is not None else None
    if (
        gathering.state != EvidenceGatheringState.ATTEMPTED
        or probe is None
        or process_key is None
        or prior.proposed_action.type != InterventionType.REQUEST_VERIFICATION
        or prior.policy_verdict != PolicyVerdict.ALLOW
        or event.event_type != EventType.SHELL
        or event.session_id != probe.session_id
        or event.harness_type != probe.harness_type
        or session.harness_type != probe.harness_type
        or session.goal_id != probe.goal_id
        or prior.goal_id != probe.goal_id
        or str((prior.metadata or {}).get("trigger_event_id") or "") != probe.request_event_id
        or event.ts < prior.created_at
        or not session.cwd
        or not _same_project(session.cwd, probe.cwd)
        or not _same_project(session.project_id or session.cwd, probe.project_id)
        or (event.project_id is not None and not _same_project(event.project_id, probe.project_id))
    ):
        return None
    if _exact_action_probe(prior.proposed_action, gathering) is None:
        return None
    command = (event.command or "").strip()
    if not command or ".." in command.replace("\\", "/"):
        return None
    if classify_pytest_invocation(command) is not None:
        return None
    lowered = command.replace("\\", "/")
    if probe.kind == VerificationProbeKind.COMMAND_EXIT and not probe.relative_targets:
        return None
    if any(target not in lowered for target in probe.relative_targets):
        return None
    state = event.process_state if isinstance(event.process_state, dict) else {}
    typed_state = state.get(process_key)
    if not isinstance(typed_state, dict):
        return None
    ok = typed_state.get("ok")
    exit_code = typed_state.get("exit_code")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        return None
    if ok is True and exit_code == 0:
        result = VerificationExecutionResult.PASSED
    elif ok is False and exit_code != 0:
        result = VerificationExecutionResult.FAILED
    else:
        return None
    return VerificationExecutionReceipt(
        backend=VerificationBackendKind.HARNESS,
        policy_verdict=PolicyVerdict.ALLOW,
        source_event_id=event.event_id,
        observed_at=event.ts,
        observed_command=command,
        cwd=probe.cwd,
        process_started=True,
        exit_code=exit_code,
        result=result,
        output=_bounded_utf8(typed_state.get("output"), probe.output_limit_bytes),
    )


def _merge_evidence_gathering(
    verification: dict,
    prior: EvidenceGatheringReceipt,
) -> bool:
    """Carry a monotonic request receipt into the current STOP verification."""

    current_raw = verification.get("evidence_gathering")
    if not isinstance(current_raw, dict):
        return False
    current = EvidenceGatheringReceipt.model_validate(current_raw)
    if prior.state not in {
        EvidenceGatheringState.ATTEMPTED,
        EvidenceGatheringState.EXECUTED,
    }:
        return False
    if prior.state == EvidenceGatheringState.EXECUTED:
        execution = prior.execution
        current_event_id = str(verification.get("pytest_event_id") or "")
        source_event_id = str(getattr(execution, "source_event_id", "") or "")
        if (
            execution is None
            or current.probe is not None
            or not current_event_id
            or source_event_id != current_event_id
        ):
            return False
    merged = EvidenceGatheringReceipt.model_validate(
        {
            **prior.model_dump(mode="json"),
            "sources": list(dict.fromkeys([*current.sources, *prior.sources]))[:32],
            "recent_events": current.recent_events,
            "workspace_snapshot": current.workspace_snapshot,
            "workspace_snapshot_reason": current.workspace_snapshot_reason,
            "claim_count": current.claim_count,
        }
    )
    verification["evidence_gathering"] = merged.model_dump(mode="json")
    return True


def _record_verification_dispatch(
    verification: dict,
    action: ProposedAction,
    verdict: PolicyVerdict,
    outcome: str,
) -> None:
    """Record delivery truth without confusing a message with test execution."""

    if action.type != InterventionType.REQUEST_VERIFICATION:
        return
    raw = verification.get("evidence_gathering")
    if not isinstance(raw, dict):
        return
    gathering = EvidenceGatheringReceipt.model_validate(raw)
    if gathering.probe is None:
        return
    probe_matches = _exact_action_probe(action, gathering) is not None
    if verdict == PolicyVerdict.ALLOW and outcome == "verification_requested" and probe_matches:
        gathering = EvidenceGatheringReceipt.model_validate(
            {
                **gathering.model_dump(mode="json"),
                "state": EvidenceGatheringState.ATTEMPTED,
                "sources": list(dict.fromkeys([*gathering.sources, "verification_request"])),
                "reason": "awaiting_matching_harness_result",
            }
        )
    elif probe_matches and outcome in {
        "verification_delivery_uncertain",
    }:
        gathering = EvidenceGatheringReceipt.model_validate(
            {
                **gathering.model_dump(mode="json"),
                "state": EvidenceGatheringState.ATTEMPTED,
                "sources": list(dict.fromkeys([*gathering.sources, "verification_dispatch"])),
                "reason": "verification_request_delivery_uncertain",
            }
        )
    elif outcome != "suppressed_by_cooldown":
        gathering = EvidenceGatheringReceipt.model_validate(
            {
                **gathering.model_dump(mode="json"),
                "state": EvidenceGatheringState.UNAVAILABLE,
                "reason": f"verification_unavailable:{outcome}"[:1_024],
            }
        )
    else:
        gathering = EvidenceGatheringReceipt.model_validate(
            {
                **gathering.model_dump(mode="json"),
                "reason": f"verification_request_not_delivered:{outcome}"[:1_024],
            }
        )
    verification["evidence_gathering"] = gathering.model_dump(mode="json")


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


def _project_key(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/").casefold()


def _same_project(left: str | None, right: str | None) -> bool:
    return bool(left and right and _project_key(left) == _project_key(right))


def _same_session_project(left: HarnessSession, right: HarnessSession) -> bool:
    """Compare the strongest project identity available for two sessions."""
    left_project = left.project_id or left.cwd
    right_project = right.project_id or right.cwd
    return _same_project(left_project, right_project)


def _update_context_routing_state(session: HarnessSession, event: HarnessEvent) -> None:
    """Persist bounded worker state used by target-specific context selection."""

    metadata = dict(session.metadata or {})
    if event.event_type == EventType.USER_PROMPT and event.message_delta:
        metadata["current_task"] = event.message_delta[:_CONTEXT_TASK_CHARS]
        metadata["task_phase"] = "planning"
    if event.file_paths:
        prior = metadata.get("active_files")
        prior_files = prior if isinstance(prior, list) else []
        metadata["active_files"] = list(
            dict.fromkeys([*event.file_paths[:_CONTEXT_ACTIVE_FILES], *prior_files])
        )[:_CONTEXT_ACTIVE_FILES]
    if event.event_type == EventType.FILE_EDIT:
        metadata["task_phase"] = "implementation"
    elif event.event_type == EventType.SHELL:
        pytest_state = (event.process_state or {}).get("pytest")
        metadata["task_phase"] = "verification" if isinstance(pytest_state, dict) else "execution"
    elif event.event_type == EventType.ERROR:
        metadata["task_phase"] = "debugging"
    session.metadata = metadata


def _required_capability(
    action: ProposedAction,
    verdict: PolicyVerdict,
) -> str | None:
    """Derive the real adapter control used by every externally acting action.

    Model output may include ``requires_capability``, but deterministic actions
    must be held to the same fail-closed contract. An explicit declaration wins
    so unknown proposed controls are rejected instead of silently remapped.
    """
    if action.requires_capability:
        return action.requires_capability
    if action.type == InterventionType.RESPOND_PERMISSION:
        requested = str(action.payload.get("decision") or "").strip().lower()
        if verdict == PolicyVerdict.ASK_HUMAN:
            return "observe_permissions"
        if verdict == PolicyVerdict.DENY or requested == "deny":
            return "deny"
        return "approve"
    if action.type == InterventionType.FRESH_HANDOFF:
        return (
            "inject_context" if isinstance(action.payload.get("bundle"), dict) else "send_message"
        )
    return {
        InterventionType.APPLY_OVERLAY: "modify_config",
        InterventionType.CONTINUE_SESSION: "resume",
        InterventionType.FOCUS_UI: "focus_ui",
        InterventionType.FORK_PROBE: "fork",
        InterventionType.INJECT_CONTEXT: "send_message",
        InterventionType.REQUEST_VERIFICATION: "send_message",
        InterventionType.REVERT_OVERLAY: "modify_config",
        InterventionType.SEND_NUDGE: "send_message",
        InterventionType.START_AGENT: "start",
        InterventionType.STOP_AGENT: "stop",
    }.get(action.type)


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

    def restart(self, session_id: str, action_type: str) -> None:
        """Start a new cooldown after a causally distinct successor action."""

        self._last[(session_id, action_type)] = time.monotonic()


def _requests_drifting(action: ProposedAction) -> bool:
    return str((action.payload or {}).get("session_status") or "").strip().lower() == "drifting"


def _clears_observed_drift(event: HarnessEvent, goal: Goal | None) -> bool:
    if event.event_type == EventType.USER_PROMPT:
        return True
    names = goal_path_names(goal)
    if not names:
        return False
    files = {
        Path(str(path).replace("\\", "/")).name.casefold()
        for path in (event.file_paths or [])
        if path
    }
    return bool(names & files)


def pet_transition(
    last: Intervention | None,
    now: datetime,
) -> tuple[str | None, str | None]:
    """Map a recent audited outcome to a short-lived, accessible pet state."""

    if last is None:
        return None, None
    try:
        age = (now - last.created_at).total_seconds()
    except (TypeError, ValueError):
        return None, None
    if age < 0 or age > PET_TRANSIENT_SECONDS:
        return None, None
    harness = last.session_id.split(":", 1)[0].replace("_", " ").title()
    if (
        last.action_taken == InterventionType.FRESH_HANDOFF.value
        and last.result == "handoff_injected"
    ):
        return "handoff", f"Context moved → {harness}"
    if last.action_taken == InterventionType.RESPOND_PERMISSION.value and last.result.startswith(
        "permission_allow"
    ):
        return "approved", f"{harness} permission handled"
    if last.action_taken == InterventionType.REQUEST_VERIFICATION.value and last.result in {
        "verification_requested",
        "verification_delivery_uncertain",
        "verification_failed",
    }:
        gathering = ((last.metadata or {}).get("verification") or {}).get(
            "evidence_gathering"
        ) or {}
        if gathering.get("state") == EvidenceGatheringState.ATTEMPTED.value:
            return "observing", "Verification requested → awaiting evidence"
        if gathering.get("state") == EvidenceGatheringState.UNAVAILABLE.value:
            return "observing", "Verification unavailable → no action taken"
    if last.action_taken == InterventionType.NOOP.value and last.trigger == EventType.STOP.value:
        verification = (last.metadata or {}).get("verification") or {}
        supported = (
            verification.get("status") == "supported"
            or verification.get("acceptance_status") == "supported"
        )
        gathering = verification.get("evidence_gathering") or {}
        gathering_state = str(gathering.get("state") or "")
        legacy_inspection = gathering.get("performed") is True
        if supported:
            return "observing", "Completion verified → no action needed"
        if gathering_state == "executed":
            return "observing", "Verification executed → no action needed"
        if gathering_state == "attempted":
            return "observing", "Verification requested → awaiting evidence"
        if gathering_state == "unavailable":
            return "observing", "Verification unavailable → no action taken"
        if gathering_state == "inspected" or legacy_inspection:
            return "observing", "Evidence inspected → no action needed"
    return None, None


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
        self.supervisor = SupervisorRouter(settings)
        self.policy = PolicyEngine(AutonomyLevel(settings.autonomy))
        self.channels = ChannelHub(settings)
        self.executor = ActionExecutor(adapters, store, channels=self.channels)
        self.cooldowns = Cooldowns()
        self.supervision_paused = False
        self._desktop_refresh_lock = asyncio.Lock()
        self._desktop_refresh_attempted_at: float | None = None
        self._handoff_mutation_lock = asyncio.Lock()
        self._session_locks_guard = asyncio.Lock()
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._event_worker_id = f"{self.store.process_boot_id}:pipeline:{uuid4().hex}"
        self._presentation_tasks: set[asyncio.Task] = set()
        # Durable parent/child reconciliation is authoritative work, not
        # presentation. Keep a strong reference while shielded so cancellation
        # cannot strand a delivered overlay child behind a dispatching parent.
        self._overlay_reconciliation_tasks: set[asyncio.Task] = set()
        self._main_effect_settlement_tasks: set[asyncio.Task] = set()

    async def ingest_observer_lifecycle(
        self, event: HarnessEvent, session: HarnessSession
    ) -> None:
        """Record a local observer disconnect without semantic worker processing.

        Only the registered shared adapter receives this callback. Generic event
        ingestion deliberately does not activate it from untrusted metadata.
        """
        from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter

        subscription_id = event.metadata.get("subscription_id")
        receipt = session.metadata.get("subscription_receipt")
        coverage = event.metadata.get("observation_coverage")
        if (
            event.harness_type != HarnessType.CODEX
            or session.harness_type != HarnessType.CODEX
            or event.session_id != session.id
            or session.id != f"codex:{session.vendor_session_id}"
            or event.event_type != EventType.STATUS
            or event.metadata.get("source") != "pex_observer_lifecycle"
            or event.metadata.get("worker_stopped") is not False
            or not isinstance(subscription_id, str)
            or not subscription_id
            or not isinstance(receipt, dict)
            or receipt.get("authorization_id") != subscription_id
            or not isinstance(coverage, dict)
            or coverage.get("state") != "disconnected"
            or session.metadata.get("observation_coverage") != coverage
            or session.status != SessionStatus.DETACHED
        ):
            raise ValueError("observer lifecycle receipt is invalid")

        async with self._session_locks_guard:
            lock = self._session_locks.setdefault(session.id, asyncio.Lock())
        async with lock:
            adapter = self.adapters.for_session(session.id)

            def validate_adapter() -> None:
                if (
                    not isinstance(adapter, CodexSharedAdapter)
                    or self.adapters.for_session(session.id) is not adapter
                    or adapter._subscription_id != subscription_id
                    or adapter.session.id != session.id
                    or adapter.session.metadata.get("subscription_receipt") != receipt
                    or adapter._connected()
                ):
                    raise ValueError("observer lifecycle does not own the current connection")

            validate_adapter()
            control = await self.store.get_session_control_state(session.id)
            if control is None:
                raise ValueError("observer lifecycle session is not published")
            current = control["session"]
            if (
                current.metadata.get("subscription_receipt") != receipt
                or current.vendor_session_id != session.vendor_session_id
                or current.harness_type != session.harness_type
                or not current.project_id
                or not session.project_id
                or not _same_project(current.project_id, session.project_id)
            ):
                raise ValueError("observer lifecycle durable connection changed")
            binding = await self.store.project_binding_for_authority(current.project_id)
            if control["project_binding"] != binding:
                raise ValueError("observer lifecycle project binding changed")
            validate_adapter()
            lifecycle = event.model_copy(deep=True)
            _redact_event(lifecycle)
            canonical = await self.store.publish_observer_session(
                session,
                expected_control_revision=control["control_revision"],
                expected_project_binding=binding,
                lifecycle_event=lifecycle,
                expected_subscription_id=subscription_id,
            )
            if self.adapters.for_session(session.id) is adapter:
                adapter.session = canonical
                adapter.sessions[session.id] = canonical
                adapter._normalizer.sessions[session.id] = canonical
            stored_event = await self.store.get_event(lifecycle.event_id)
            if stored_event is None:
                raise RuntimeError("committed observer lifecycle event is missing")
            self._schedule_committed_publication("event", stored_event.model_dump(mode="json"))

    @staticmethod
    def _freeze_shared_codex_observation(
        event: HarnessEvent, session: HarnessSession, *, input_baseline=None,
    ) -> HarnessEvent:
        """Use the same immutable receipt for live acceptance and loss recovery."""
        observed = event.model_copy(deep=True)
        observed.metadata["pex_observer_snapshot"] = {
            "schema": "pex.codex-live-observation.v1",
            "subscription_receipt": dict(session.metadata["subscription_receipt"]),
            "status": session.status.value,
            "last_activity": session.last_activity.isoformat() if session.last_activity else None,
            "observation_coverage": dict(session.metadata["observation_coverage"]),
        }
        if "workspace_binding" in session.metadata:
            # Freeze this observation's workspace, not a later attachment's.
            observed.metadata["pex_observer_snapshot"]["workspace_binding"] = (
                session.model_copy(deep=True).metadata["workspace_binding"]
            )
        if input_baseline is not None:
            observed.metadata["pex_observer_snapshot"]["input_baseline"] = asdict(input_baseline)
        return observed

    async def retain_shared_codex_observations(
        self,
        observations: tuple[tuple[HarnessEvent, HarnessSession], ...],
        session: HarnessSession,
    ) -> None:
        """Persist the actual stopped pump's pending ledger without planning.

        This callback is not a public ingest mode. Object witnesses attest the
        original observations; Store separately fences their durable identity.
        Frozen per-event state is retained as provenance, never projected over
        current human controls or a replacement connection.
        """
        from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter

        async with self._session_locks_guard:
            lock = self._session_locks.setdefault(session.id, asyncio.Lock())
        async with lock:
            adapter = self.adapters.for_session(session.id)
            receipt = session.metadata.get("subscription_receipt")

            def validate_owner() -> None:
                if (
                    not isinstance(adapter, CodexSharedAdapter)
                    or self.adapters.for_session(session.id) is not adapter
                    or adapter._retaining_observations is not observations
                    or adapter._retaining_session is not session
                    or adapter._connected()
                    or not adapter._invalid
                    or not isinstance(observations, tuple)
                    or not observations
                    or session.status != SessionStatus.DETACHED
                    or not isinstance(receipt, dict)
                    or receipt != adapter.session.metadata.get("subscription_receipt")
                    or receipt.get("authorization_id") != adapter._subscription_id
                ):
                    raise ValueError("retained observations do not own the stopped ingestion")

            validate_owner()
            events = []
            for event, snapshot in observations:
                held = adapter._undelivered.get(event.event_id)
                if (
                    event.session_id != session.id
                    or snapshot.id != session.id
                    or event.harness_type != HarnessType.CODEX
                    or snapshot.harness_type != HarnessType.CODEX
                    or snapshot.vendor_session_id != session.vendor_session_id
                    or snapshot.cwd != session.cwd
                    or snapshot.project_id != session.project_id
                    or snapshot.metadata.get("subscription_receipt") != receipt
                    or event.metadata.get("subscription_id") != adapter._subscription_id
                    or held is None
                    or held[0] is not event
                    or held[1] is not snapshot
                ):
                    raise ValueError("retained observation identity changed")
                baseline = adapter._input_baselines.get(event.event_id)
                if adapter._input_baseline is not None and baseline is None:
                    raise ValueError("retained observation lacks its frozen input baseline")
                observed = self._freeze_shared_codex_observation(
                    event, snapshot, input_baseline=baseline,
                )
                _redact_event(observed)
                events.append(observed)
            binding = await self.store.project_binding_for_authority(session.project_id)
            validate_owner()
            retained = await self.store.retain_observer_events(
                tuple(events), session, expected_project_binding=binding
            )
            for event in retained:
                self._schedule_committed_publication("event", event.model_dump(mode="json"))

    async def ingest_shared_codex_event(
        self, event: HarnessEvent, session: HarnessSession
    ) -> Intervention | None:
        """Freeze an actual queued observation, not client-supplied status claims.

        The in-flight object witness is local to the registered adapter. The
        frozen record survives durable event replay without re-reading a newer
        adapter runtime state. Store checks the receipt again at acceptance.
        """
        from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter

        async with self._session_locks_guard:
            lock = self._session_locks.setdefault(session.id, asyncio.Lock())
        async with lock:
            adapter = self.adapters.for_session(session.id)
            receipt = session.metadata.get("subscription_receipt")
            if (
                not isinstance(adapter, CodexSharedAdapter)
                or adapter._ingesting_observation is None
                or adapter._ingesting_observation[0] is not event
                or adapter._ingesting_observation[1] is not session
                or not adapter._connected()
                or event.session_id != session.id
                or event.harness_type != HarnessType.CODEX
                or session.harness_type != HarnessType.CODEX
                or not isinstance(receipt, dict)
                or receipt != adapter.session.metadata.get("subscription_receipt")
                or event.metadata.get("subscription_id") != adapter._subscription_id
            ):
                raise ValueError("shared observation does not own the current ingestion")
            baseline = adapter._input_baselines.get(event.event_id)
            if adapter._input_baseline is not None and baseline is None:
                raise ValueError("shared observation lacks its frozen input baseline")
            observed = self._freeze_shared_codex_observation(
                event, session, input_baseline=baseline,
            )
            if (
                observed.metadata.get("raw_method") == "item/started"
                and observed.metadata.get("human_input_pending") is True
            ):
                # An incomplete user item is evidence of pending input, not
                # an instruction to reason about. Record it without claiming
                # PEX authorship or calling the supervisor before completion.
                _redact_event(observed)
                binding = await self.store.project_binding_for_authority(session.project_id)
                retained = await self.store.retain_observer_events(
                    (observed,), session, expected_project_binding=binding,
                    require_current_workspace=True,
                )
                self._schedule_committed_publication(
                    "event", retained[0].model_dump(mode="json"),
                )
                return None
            if "pex_correction_observation" in observed.metadata:
                from pex_bridge.adapters.strict_json import strict_json_loads

                raw = adapter._correction_items.get(event.event_id)
                if raw is None:
                    raise ValueError("correction observation lacks its queued raw item")
                _redact_event(observed)
                retained = await self.store.record_codex_correction_observation(
                    observed, session, raw_item=strict_json_loads(raw),
                    turn_id=event.metadata["vendor_turn_id"],
                )
                self._schedule_committed_publication("event", retained.model_dump(mode="json"))
                return None
            result = await self._ingest_event_locked(observed, session)
            # A stale accepted event may already have been durably settled.
            # Still retire this stream through the adapter's owned finalizer;
            # later records cannot regain authority by retrying this receipt.
            await self.store.require_session_workspace_current(session)
            return result

    async def ingest_event(
        self, event: HarnessEvent, session: HarnessSession
    ) -> Intervention | None:
        if event.session_id != session.id or event.harness_type != session.harness_type:
            raise ValueError("event/session identity mismatch")
        if {"pex_observer_snapshot", "pex_correction_observation"} & event.metadata.keys():
            # Only the internal shared adapter callback may attest runtime
            # state. HTTP/plugin metadata cannot manufacture this authority.
            raise ValueError("observer snapshots require the internal ingestion path")
        # Multiple hook transports can report the same worker concurrently.
        # Serialize the complete read/decide/act ledger for one exact session so
        # no decision is based on a snapshot that another in-flight event has
        # already superseded. Independent workers retain full concurrency.
        async with self._session_locks_guard:
            lock = self._session_locks.setdefault(session.id, asyncio.Lock())
        async with lock:
            return await self._ingest_event_locked(event, session)

    async def _ingest_event_locked(
        self,
        event: HarnessEvent,
        session: HarnessSession,
    ) -> Intervention | None:
        canonical = await self.store.get_event(event.event_id)
        if canonical is not None:
            candidate = event.model_copy(deep=True)
            _redact_event(candidate)
            if candidate.goal_id is None:
                candidate.goal_id = canonical.goal_id
            if candidate.project_id is None:
                candidate.project_id = canonical.project_id
            if event_semantic_payload(candidate) != event_semantic_payload(canonical):
                raise ValueError("event id collision contains different content")
            processing = await self.store.get_event_processing(event.event_id)
            if processing is None:
                raise RuntimeError("event processing binding is missing")
            if processing["mode"] != "pipeline":
                return self._receipt_intervention(processing)
            return await self._drain_event_and_followups(event.event_id)
        return await self._accept_and_resume_event(event, session)

    async def _prepare_event_acceptance(
        self,
        event: HarnessEvent,
        session: HarnessSession,
    ) -> tuple[HarnessEvent, HarnessSession]:
        """Resolve durable identity before the atomic acceptance boundary."""

        event = event.model_copy(deep=True)
        session = session.model_copy(deep=True)
        _redact_event(event)
        existing = await self.store.get_session_for_authority(session.id)
        if existing is not None:
            incoming = session
            if existing.harness_type != session.harness_type:
                raise ValueError("session harness identity mismatch")
            if existing.vendor_session_id != session.vendor_session_id:
                raise ValueError("session vendor identity mismatch")
            if (
                existing.project_id
                and session.project_id
                and not _same_project(existing.project_id, session.project_id)
            ):
                raise ValueError("session project identity mismatch")
            # The accepted snapshot is the compare-and-merge baseline for the
            # later atomic plan. Starting from a stale adapter object makes
            # prior event-owned status/metadata look like a concurrent update,
            # which can discard the freshly probed capabilities and plan.
            # Preserve the durable row exactly, filling only locator/display
            # fields that were previously absent. Capability negotiation runs
            # after acceptance and is persisted as this event's projection.
            session = existing.model_copy(deep=True)
            if not session.cwd:
                session.cwd = incoming.cwd
            if not session.project_id:
                session.project_id = incoming.project_id
            if not session.repo:
                session.repo = incoming.repo
            if not session.external_url:
                session.external_url = incoming.external_url
            if not session.local_window_id:
                session.local_window_id = incoming.local_window_id
            if not session.model:
                session.model = incoming.model
            if not session.reasoning_effort:
                session.reasoning_effort = incoming.reasoning_effort
            for key, value in incoming.metadata.items():
                session.metadata.setdefault(key, value)
        goal = await self.store.get_goal_for_authority(session.goal_id) if session.goal_id else None
        if session.goal_id and goal is None:
            raise ValueError("session goal not found")
        if goal is not None:
            if session.project_id is None:
                session.project_id = goal.project_id
            else:
                await self.store.list_context_for_authority(
                    session.project_id,
                    goal_id=goal.id,
                    limit=1,
                )
        if event.goal_id is not None and event.goal_id != session.goal_id:
            raise ValueError("event/session goal identity mismatch")
        event.goal_id = session.goal_id
        if goal is not None and event.project_id:
            await self.store.list_context_for_authority(
                event.project_id,
                goal_id=goal.id,
                limit=1,
            )
        elif (
            event.project_id
            and session.project_id
            and not _same_project(event.project_id, session.project_id)
        ):
            raise ValueError("event/session project identity mismatch")
        if event.project_id is None:
            event.project_id = session.project_id
        elif session.project_id is None:
            session.project_id = event.project_id
        return event, session

    @staticmethod
    def _receipt_intervention(processing: dict) -> Intervention | None:
        receipt = processing.get("receipt")
        if not isinstance(receipt, dict):
            return None
        raw = receipt.get("intervention")
        return Intervention.model_validate(raw) if isinstance(raw, dict) else None

    async def _accept_and_resume_event(
        self,
        event: HarnessEvent,
        session: HarnessSession,
    ) -> Intervention | None:
        event, session = await self._prepare_event_acceptance(event, session)
        acceptance = await self.store.accept_pipeline_event(
            event,
            session_snapshot=session,
        )
        processing = acceptance["processing"]
        if processing["mode"] != "pipeline":
            return self._receipt_intervention(processing)
        intervention = await self._drain_event_and_followups(str(processing["event_id"]))
        if acceptance["created"]:
            self._schedule_committed_publication(
                "event",
                acceptance["event"].model_dump(mode="json"),
            )
        return intervention

    async def _drain_event_and_followups(
        self,
        event_id: str,
    ) -> Intervention | None:
        """Finish authoritative processing, then run recoverable handoff work.

        The event receipt never depends on presentation listeners.  Automatic
        handoff is different: it is worker-visible I/O, so it is awaited and
        protected by its own durable delivering receipt before returning.
        Replaying an accepted event re-enters this method; the handoff ledger
        suppresses any item whose delivery is complete or uncertain.
        """

        intervention = await self._drain_event_processing(event_id)
        processing = await self.store.get_event_processing(event_id)
        if processing is None or processing["state"] not in EVENT_PROCESSING_TERMINAL_STATES:
            return intervention
        if processing["state"] == "failed":
            return intervention
        event, accepted_session, _ = await self._processing_inputs(processing)
        try:
            await self.store.require_session_workspace_current(accepted_session)
        except WorkspaceAuthorityError:
            # Terminal history is replayable; it is not new handoff authority.
            return intervention
        plan = processing.get("plan")
        verification = dict(plan.get("verification") or {}) if isinstance(plan, dict) else {}
        followup_owner = f"{self._event_worker_id}:followup:{uuid4().hex}"
        auto_claim = await self.store.claim_event_followup(
            event_id=event_id,
            kind="auto_handoff",
            owner=followup_owner,
        )
        if auto_claim["outcome"] == "claimed":
            try:
                await self._maybe_auto_handoff(
                    accepted_session,
                    event,
                    verification,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # The authoritative event receipt is already committed.  A later
                # duplicate/recovery pass can re-enter this bounded follow-up.
                logger.warning(
                    "committed automatic handoff failed event_id=%s error=%s",
                    event_id,
                    type(exc).__name__,
                )
            else:
                await self.store.complete_event_followup(
                    event_id=event_id,
                    kind="auto_handoff",
                    owner=followup_owner,
                    result={"status": "complete"},
                )
        if intervention is None:
            return None
        stored_intervention = await self.store.get_intervention_for_authority(intervention.id)
        if stored_intervention is None:
            return intervention
        attention_owner = f"{self._event_worker_id}:followup:{uuid4().hex}"
        attention_claim = await self.store.claim_event_followup(
            event_id=event_id,
            kind="human_attention",
            owner=attention_owner,
        )
        if attention_claim["outcome"] == "claimed":
            try:
                stored_intervention = await self._run_human_attention_followup(
                    event_id=event_id,
                    owner=attention_owner,
                    intervention=stored_intervention,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # The event receipt remains authoritative. The claimed row is
                # retried only after lease expiry or by a later process boot.
                logger.warning(
                    "committed human attention failed event_id=%s error=%s",
                    event_id,
                    type(exc).__name__,
                )
        return stored_intervention

    async def _run_human_attention_followup(
        self,
        *,
        event_id: str,
        owner: str,
        intervention: Intervention,
    ) -> Intervention:
        live_session = await self.store.get_session_for_authority(
            intervention.session_id,
            require_goal_binding=intervention.goal_id is not None,
        )
        attention_result: dict[str, str]
        if (
            intervention.policy_verdict != PolicyVerdict.ASK_HUMAN
            or intervention.proposed_action.type
            in {InterventionType.NOTIFY, InterventionType.RESPOND_PERMISSION}
        ):
            attention_result = {
                "status": "skipped",
                "reason": "intervention_not_human_attention",
            }
        elif "remote_notify" in (intervention.metadata or {}):
            attention_result = {
                "status": "complete",
                "delivery": str(intervention.metadata["remote_notify"]),
            }
        elif not (
            live_session is not None
            and live_session.goal_id == intervention.goal_id
            and not live_session.supervision_paused
            and not self.supervision_paused
        ):
            attention_result = {
                "status": "skipped",
                "reason": "live_attention_binding_changed",
            }
        else:
            remote = self.channels.deliver_attention(
                live_session,
                intervention.proposed_action,
                idempotency_key=f"event-attention:{event_id}:{intervention.id}",
            )
            metadata = dict(intervention.metadata or {})
            metadata["remote_notify"] = remote
            intervention.metadata = metadata
            await self.store.update_intervention(
                intervention,
                record_type="remote_attention_delivered",
            )
            self._schedule_committed_publication(
                "intervention",
                intervention.model_dump(mode="json"),
            )
            attention_result = {"status": "complete", "delivery": remote}
        await self.store.complete_event_followup(
            event_id=event_id,
            kind="human_attention",
            owner=owner,
            result=attention_result,
        )
        return intervention

    async def _drain_event_processing(self, requested_event_id: str) -> Intervention | None:
        deadline = asyncio.get_running_loop().time() + 10.0
        while True:
            requested = await self.store.get_event_processing(requested_event_id)
            if requested is None:
                raise RuntimeError("accepted event processing row disappeared")
            if requested["state"] in EVENT_PROCESSING_TERMINAL_STATES:
                return self._receipt_intervention(requested)

            owner = f"{self._event_worker_id}:{uuid4().hex}"
            claim = await self.store.claim_event_processing(
                requested_event_id,
                owner=owner,
            )
            outcome = str(claim["outcome"])
            if outcome == "blocked_by_earlier_event":
                blocking_id = str(claim["blocking_event_id"])
                blocking_owner = f"{self._event_worker_id}:{uuid4().hex}"
                blocking_claim = await self.store.claim_event_processing(
                    blocking_id,
                    owner=blocking_owner,
                )
                blocking_outcome = str(blocking_claim["outcome"])
                if blocking_outcome == "claimed":
                    await self._drive_event_processing(
                        blocking_claim["processing"],
                        owner=blocking_owner,
                    )
                elif blocking_outcome == "requires_reconciliation":
                    await self._reconcile_uncertain_event(
                        blocking_claim["processing"],
                        owner=blocking_owner,
                    )
                elif blocking_outcome not in {
                    "terminal",
                    "busy",
                    "already_owned",
                    "dispatching",
                }:
                    raise RuntimeError(
                        f"unexpected blocking event claim outcome: {blocking_outcome}"
                    )
                if blocking_outcome in {"busy", "already_owned", "dispatching"}:
                    if asyncio.get_running_loop().time() >= deadline:
                        raise RuntimeError("earlier event processing remains active")
                    await asyncio.sleep(0.025)
                continue
            if outcome == "claimed":
                await self._drive_event_processing(claim["processing"], owner=owner)
                continue
            if outcome == "requires_reconciliation":
                await self._reconcile_uncertain_event(claim["processing"], owner=owner)
                continue
            if outcome == "terminal":
                return self._receipt_intervention(claim["processing"])
            if outcome not in {"busy", "already_owned", "dispatching"}:
                raise RuntimeError(f"unexpected event processing claim outcome: {outcome}")
            if asyncio.get_running_loop().time() >= deadline:
                raise RuntimeError("event processing remains active in another runner")
            await asyncio.sleep(0.025)

    async def _drive_event_processing(
        self,
        processing: dict,
        *,
        owner: str | None,
    ) -> None:
        state = str(processing["state"])
        if state in EVENT_PROCESSING_TERMINAL_STATES:
            return
        if state == "accepted":
            claim_owner = owner or f"{self._event_worker_id}:{uuid4().hex}"
            claim = await self.store.claim_event_processing(
                str(processing["event_id"]),
                owner=claim_owner,
            )
            if claim["outcome"] == "claimed":
                await self._drive_event_processing(
                    claim["processing"],
                    owner=claim_owner,
                )
            elif claim["outcome"] == "requires_reconciliation":
                await self._reconcile_uncertain_event(
                    claim["processing"],
                    owner=claim_owner,
                )
            return
        if state == "planned":
            if owner is None:
                owner = f"{self._event_worker_id}:{uuid4().hex}"
                claim = await self.store.claim_event_processing(
                    str(processing["event_id"]),
                    owner=owner,
                )
                if claim["outcome"] != "claimed":
                    return
                processing = claim["processing"]
            await self._resume_planned_event(processing, owner=owner)
            return
        if state == "planning":
            if owner is None:
                owner = f"{self._event_worker_id}:{uuid4().hex}"
                claim = await self.store.claim_event_processing(
                    str(processing["event_id"]),
                    owner=owner,
                )
                if claim["outcome"] != "claimed":
                    return
                processing = claim["processing"]
            await self._plan_claimed_event(processing, owner=owner)
            return
        if state == "plan_generation_uncertain":
            await self._reconcile_uncertain_event(
                processing,
                owner=owner or f"{self._event_worker_id}:{uuid4().hex}",
            )

    async def _processing_inputs(
        self,
        processing: dict,
    ) -> tuple[HarnessEvent, HarnessSession, Goal | None]:
        event = await self.store.get_event(str(processing["event_id"]))
        if event is None:
            raise RuntimeError("accepted event row disappeared")
        accepted_session = processing.get("accepted_session")
        if not isinstance(accepted_session, HarnessSession):
            raise RuntimeError("pipeline event is missing its accepted session snapshot")
        session = accepted_session.model_copy(deep=True)
        live = await self.store.get_session_for_authority(
            session.id,
            require_goal_binding=processing["goal_id"] is not None,
        )
        if live is not None:
            if live.harness_type != session.harness_type:
                raise ValueError("accepted session harness identity changed")
            if live.vendor_session_id != session.vendor_session_id:
                raise ValueError("accepted session vendor identity changed")
            if (
                live.project_id
                and session.project_id
                and not _same_project(live.project_id, session.project_id)
            ):
                raise ValueError("accepted session project identity changed")
            if not session.cwd:
                session.cwd = live.cwd
            if not session.repo:
                session.repo = live.repo
            if not session.project_id:
                session.project_id = live.project_id
            session.supervision_paused = live.supervision_paused
            for key in _DURABLE_SESSION_METADATA_KEYS:
                if key in live.metadata:
                    session.metadata[key] = live.metadata[key]
            if live.capabilities:
                session.capabilities = dict(live.capabilities)
                source = live.metadata.get("capabilities_adapter")
                if source is not None:
                    session.metadata["capabilities_adapter"] = source
        session.goal_id = processing["goal_id"]
        goal = (
            await self.store.get_goal_for_authority(str(processing["goal_id"]))
            if processing["goal_id"]
            else None
        )
        if processing["goal_id"] and goal is None:
            raise ValueError("accepted session goal not found")
        return event, session, goal

    @staticmethod
    def _deterministic_reconciliation_result(
        request: SupervisorRequest,
        *,
        reason: str,
    ) -> SupervisorResult:
        return SupervisorResult(
            action=plan_deterministic(request),
            used_llm=False,
            diagnosis=f"deterministic_reconciliation:{reason}",
            traces=[reason, "ambiguous_semantic_result_ignored"],
            inference_status="failed",
            execution_mode="deterministic_reconciliation",
            transport_status="failed",
        )

    @staticmethod
    def _reconcile_supervisor_effect(
        request: SupervisorRequest,
        effect: dict,
        *,
        reason: str,
    ) -> SupervisorResult:
        """Keep returned observations, never authorize an ambiguous proposal."""

        raw_result = (effect.get("result") or {}).get("supervisor_result")
        if raw_result is None:
            return Pipeline._deterministic_reconciliation_result(request, reason=reason)
        # The durable record retains the original response. This separate NOOP
        # projection preserves its telemetry without replaying inference or action.
        result = SupervisorResult.model_validate(raw_result).model_copy(deep=True)
        result.action = _action_from_proposal(
            request,
            {"type": "NOOP", "rationale": reason, "evidence": [reason]},
        )
        result.diagnosis = f"ambiguous_semantic_result:{reason}"
        result.traces = [*result.traces[-254:], reason, "ambiguous_semantic_action_ignored"]
        return result

    @staticmethod
    def _event_planning_snapshot(
        *,
        claims: list[dict],
        verification: dict,
        context_items: list[ContextItem],
        decisions: list[Decision],
        intervention_updates: list[Intervention],
    ) -> dict:
        """Freeze every mutable local projection used after semantic dispatch."""

        snapshot = {
            "schema": "pex.event-planning-snapshot.v1",
            "claims": claims,
            "verification": verification,
            "context_items": [item.model_dump(mode="json") for item in context_items],
            "decisions": [item.model_dump(mode="json") for item in decisions],
            "intervention_updates": [item.model_dump(mode="json") for item in intervention_updates],
        }
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > _MAX_EVENT_PLANNING_SNAPSHOT_BYTES:
            raise ValueError("event planning snapshot exceeds the durable size limit")
        return snapshot

    @staticmethod
    def _restore_event_planning_snapshot(
        raw: object,
    ) -> tuple[list[dict], dict, list[ContextItem], list[Decision], list[Intervention]]:
        """Validate a first-attempt snapshot before exact crash replay."""

        if not isinstance(raw, dict) or set(raw) != {
            "schema",
            "claims",
            "verification",
            "context_items",
            "decisions",
            "intervention_updates",
        }:
            raise RuntimeError("durable event planning snapshot envelope is invalid")
        if raw.get("schema") != "pex.event-planning-snapshot.v1":
            raise RuntimeError("durable event planning snapshot schema is invalid")
        try:
            encoded = json.dumps(
                raw,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise RuntimeError("durable event planning snapshot JSON is invalid") from exc
        if len(encoded) > _MAX_EVENT_PLANNING_SNAPSHOT_BYTES:
            raise RuntimeError("durable event planning snapshot exceeds the size limit")
        claims = raw.get("claims")
        verification = raw.get("verification")
        context_items = raw.get("context_items")
        decisions = raw.get("decisions")
        intervention_updates = raw.get("intervention_updates")
        if (
            not isinstance(claims, list)
            or len(claims) > 256
            or any(not isinstance(item, dict) for item in claims)
            or not isinstance(verification, dict)
            or not isinstance(context_items, list)
            or len(context_items) > 512
            or not isinstance(decisions, list)
            or len(decisions) > 256
            or not isinstance(intervention_updates, list)
            or len(intervention_updates) > 256
        ):
            raise RuntimeError("durable event planning snapshot content is invalid")
        try:
            restored_context = [ContextItem.model_validate(item) for item in context_items]
            restored_decisions = [Decision.model_validate(item) for item in decisions]
            restored_updates = [Intervention.model_validate(item) for item in intervention_updates]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("durable event planning snapshot model is invalid") from exc
        return (
            [dict(item) for item in claims],
            dict(verification),
            restored_context,
            restored_decisions,
            restored_updates,
        )

    async def _invoke_supervisor(self, request: SupervisorRequest, *, semantic: bool, witness):
        async def invoke():
            # wait_for schedules a new task. Recheck in that task, not merely
            # before it was queued, then enter the provider without another
            # bridge-owned scheduling boundary.
            try:
                current = await self.store.require_session_workspace_current(request.session)
                if current != witness:
                    raise WorkspaceAuthorityError("workspace changed before inference")
                if witness is not None:
                    require_workspace_sample(*witness, cwd=request.session.cwd)
            except WorkspaceAuthorityError as exc:
                raise _WorkspacePlannerNotStarted(str(exc)) from exc
            if (
                semantic
                and self.settings.supervisor_mode in {"agentcore", "hybrid"}
                and self.supervisor.agentcore is not None
            ):
                return await self.supervisor.agentcore.decide(request)
            return await self.supervisor.decide(request, local_model=self.model)

        scope = (
            workspace_evidence_guard(
                request.session,
                workspace_read_check(self.store, request.session, witness),
            )
            if witness is not None
            else nullcontext()
        )
        # Revoked on normal return, timeout and cancellation. A surviving model
        # thread cannot reopen local files after this invocation has ended.
        with scope:
            if (
                semantic
                and self.settings.supervisor_mode in {"agentcore", "hybrid"}
                and self.supervisor.agentcore is not None
            ):
                # No hybrid second call after an ambiguous remote boundary.
                result = await asyncio.wait_for(invoke(), timeout=30)
                return _preserve_deterministic_truth(
                    request, plan_deterministic(request), result
                )
            return await asyncio.wait_for(invoke(), timeout=30)

    async def _resolve_durable_supervisor(
        self,
        request: SupervisorRequest,
        event: HarnessEvent,
        *,
        owner: str,
        planning_snapshot: dict,
    ) -> tuple[SupervisorResult, dict, dict]:
        existing_effect = await self.store.get_event_effect(event.event_id, "planner")
        if existing_effect is not None:
            existing_payload = existing_effect.get("payload")
            if (
                not isinstance(existing_payload, dict)
                or existing_payload.get("schema") != "pex.supervisor-effect.v1"
                or existing_payload.get("event_id") != event.event_id
                or existing_payload.get("semantic_hash") != event_semantic_hash(event)
                or not isinstance(existing_payload.get("request"), dict)
                or not isinstance(existing_payload.get("planning_snapshot"), dict)
            ):
                raise RuntimeError("durable planner effect binding is invalid")
            request = SupervisorRequest.model_validate(existing_payload["request"])
            self._restore_event_planning_snapshot(existing_payload["planning_snapshot"])
            planning_snapshot = existing_payload["planning_snapshot"]
            planner_payload = existing_payload
        else:
            planner_payload = {
                "schema": "pex.supervisor-effect.v1",
                "event_id": event.event_id,
                "semantic_hash": event_semantic_hash(event),
                "request": request.model_dump(mode="json"),
                "planning_snapshot": planning_snapshot,
            }
        payload_json = json.dumps(
            planner_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        request_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        reservation = await self.store.reserve_event_effect(
            event_id=event.event_id,
            effect_key="planner",
            kind="supervisor_decision",
            target_session_id=event.session_id,
            payload=planner_payload,
            request_hash=request_hash,
            owner=owner,
        )
        effect = reservation["effect"]
        if effect["state"] == "delivered":
            raw_result = (effect.get("result") or {}).get("supervisor_result")
            if not isinstance(raw_result, dict):
                raise RuntimeError("delivered planner effect is missing its result")
            return SupervisorResult.model_validate(raw_result), effect, planning_snapshot
        if effect["state"] in {"failed", "skipped", "delivery_uncertain"}:
            return (
                self._reconcile_supervisor_effect(
                    request,
                    effect,
                    reason=f"planner_effect_{effect['state']}",
                ),
                effect,
                planning_snapshot,
            )
        if effect["state"] == "dispatching":
            raise RuntimeError("planner effect dispatch is still active")
        dispatch = await self.store.start_event_effect_dispatch(
            event_id=event.event_id,
            effect_key="planner",
            owner=owner,
        )
        if not dispatch["granted"]:
            if dispatch.get("reason") == WorkspaceAuthorityError.code:
                raise WorkspaceAuthorityError("workspace changed before planner dispatch")
            raise RuntimeError(str(dispatch.get("reason") or "planner dispatch refused"))

        try:
            witness = await self.store.require_session_workspace_current(request.session)
        except WorkspaceAuthorityError:
            # No provider call has started. Retire this reservation truthfully,
            # rather than leaving a dispatch marker that invites reconciliation.
            await self.store.finalize_event_effect(
                event_id=event.event_id,
                effect_key="planner",
                state="failed",
                result={
                    "status": "failed", "code": WorkspaceAuthorityError.code,
                    "provider_started": False,
                },
            )
            raise
        try:
            semantic = needs_semantic_inference(request)
            result = await self._invoke_supervisor(request, semantic=semantic, witness=witness)
            ambiguous = (
                result.inference_status in {"timeout"}
                or result.execution_mode == "hybrid_local_fallback"
                or (
                    semantic
                    and result.transport_status == "failed"
                    and self.settings.supervisor_mode in {"agentcore", "hybrid"}
                )
            )
            if ambiguous:
                uncertain_result = {
                    "status": "delivery_uncertain",
                    "code": "semantic_dispatch_result_ambiguous",
                    "supervisor_result": result.model_dump(mode="json"),
                }
                effect = await self.store.finalize_event_effect(
                    event_id=event.event_id,
                    effect_key="planner",
                    state="delivery_uncertain",
                    result=uncertain_result,
                )
                return (
                    self._reconcile_supervisor_effect(
                        request,
                        effect,
                        reason="semantic_dispatch_result_ambiguous",
                    ),
                    effect,
                    planning_snapshot,
                )
            result_payload = {
                "status": "delivered",
                "supervisor_result": result.model_dump(mode="json"),
            }
            downstream_id = (
                result.transport_request_id
                or result.inference_request_id
                or result.local_invocation_id
            )
            effect = await self.store.finalize_event_effect(
                event_id=event.event_id,
                effect_key="planner",
                state="delivered",
                result=result_payload,
                downstream_operation_id=downstream_id,
            )
            return result, effect, planning_snapshot
        except _WorkspacePlannerNotStarted:
            await self.store.finalize_event_effect(
                event_id=event.event_id,
                effect_key="planner",
                state="failed",
                result={
                    "status": "failed", "code": WorkspaceAuthorityError.code,
                    "provider_started": False,
                },
            )
            raise
        except AgentCoreDeliveryUncertainError as exc:
            effect = await asyncio.shield(
                self.store.finalize_event_effect(
                    event_id=event.event_id,
                    effect_key="planner",
                    state="delivery_uncertain",
                    result={
                        "status": "delivery_uncertain",
                        "code": f"agentcore_{exc.reason_code}",
                    },
                    downstream_operation_id=exc.transport_invocation_id,
                )
            )
            return (
                self._deterministic_reconciliation_result(
                    request,
                    reason=f"agentcore_{exc.reason_code}",
                ),
                effect,
                planning_snapshot,
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                self.store.finalize_event_effect(
                    event_id=event.event_id,
                    effect_key="planner",
                    state="delivery_uncertain",
                    result={
                        "status": "delivery_uncertain",
                        "code": "planner_cancelled_after_dispatch_marker",
                    },
                )
            )
            raise
        except Exception:
            effect = await asyncio.shield(
                self.store.finalize_event_effect(
                    event_id=event.event_id,
                    effect_key="planner",
                    state="delivery_uncertain",
                    result={
                        "status": "delivery_uncertain",
                        "code": "planner_failed_after_dispatch_marker",
                    },
                )
            )
            return (
                self._deterministic_reconciliation_result(
                    request,
                    reason="planner_failed_after_dispatch_marker",
                ),
                effect,
                planning_snapshot,
            )

    async def _plan_claimed_event(self, processing: dict, *, owner: str) -> None:
        try:
            committed = await self._build_and_commit_event_plan(
                processing,
                owner=owner,
                reconcile_uncertain=False,
            )
        except (ProjectIdentityBlockedError, WorkspaceAuthorityError) as exc:
            await self.store.fail_event_processing(
                event_id=str(processing["event_id"]),
                owner=owner,
                code=exc.code,
            )
            return
        if committed["state"] == "planned":
            await self._resume_planned_event(committed, owner=owner)

    async def _reconcile_uncertain_event(
        self,
        processing: dict,
        *,
        owner: str,
    ) -> None:
        current = await self.store.get_event_processing(str(processing["event_id"]))
        if current is None:
            raise RuntimeError("uncertain event processing row disappeared")
        if current["state"] != "plan_generation_uncertain":
            return
        try:
            committed = await self._build_and_commit_event_plan(
                current,
                owner=owner,
                reconcile_uncertain=True,
            )
        except (ProjectIdentityBlockedError, WorkspaceAuthorityError) as exc:
            await self.store.fail_event_processing(
                event_id=str(current["event_id"]),
                owner=owner,
                code=exc.code,
            )
            return
        if committed["state"] == "planned":
            await self._resume_planned_event(committed, owner=owner)

    @staticmethod
    def _event_plan_envelope(
        *,
        processing: dict,
        context_items: list[ContextItem],
        decisions: list[Decision],
        intervention_updates: list[Intervention],
        intervention: Intervention | None,
        effect_kind: str | None,
        required_capability: str | None,
        details: dict,
    ) -> dict:
        return {
            "schema": "pex.event-plan.v1",
            "event_id": processing["event_id"],
            "session_id": processing["session_id"],
            "goal_id": processing["goal_id"],
            "project_id": processing["project_id"],
            "effect_kind": effect_kind,
            "intervention_id": intervention.id if intervention is not None else None,
            "action": (
                intervention.proposed_action.model_dump(mode="json")
                if intervention is not None
                else None
            ),
            "required_capability": (required_capability if intervention is not None else None),
            "context_ids": [item.id for item in context_items],
            "decision_ids": [item.id for item in decisions],
            "intervention_update_ids": [item.id for item in intervention_updates],
            **details,
        }

    def _schedule_committed_publication(self, topic: str, payload: dict) -> None:
        """Wake presentation listeners after commit without gating the receipt."""

        async def publish() -> None:
            try:
                await self.bus.publish_committed(
                    topic,
                    payload,
                    timeout_seconds=0.1,
                )
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(
                    "committed event publication failed topic=%s error=%s",
                    topic,
                    type(exc).__name__,
                )
            finally:
                # Release the strong reference before the task becomes done.
                # A done callback alone can remain queued behind unrelated
                # ready work after the publication timeout has elapsed.
                current = asyncio.current_task()
                if current is not None:
                    self._presentation_tasks.discard(current)

        task = asyncio.create_task(publish())
        self._presentation_tasks.add(task)
        task.add_done_callback(self._presentation_tasks.discard)

    async def _publish_event_plan_commit(
        self,
        *,
        intervention_updates: list[Intervention],
        intervention: Intervention | None,
    ) -> None:
        for item in intervention_updates:
            self._schedule_committed_publication(
                "intervention",
                item.model_dump(mode="json"),
            )
        if intervention is not None:
            self._schedule_committed_publication(
                "intervention",
                intervention.model_dump(mode="json"),
            )

        async def publish_pet() -> None:
            try:
                pet = await self.pet_snapshot()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(
                    "committed event pet snapshot failed error=%s",
                    type(exc).__name__,
                )
            else:
                self._schedule_committed_publication("pet", pet)
            finally:
                # Keep presentation bookkeeping deterministic under a loaded
                # event loop; the callback below remains the cancellation-
                # before-first-step fallback.
                current = asyncio.current_task()
                if current is not None:
                    self._presentation_tasks.discard(current)

        task = asyncio.create_task(publish_pet())
        self._presentation_tasks.add(task)
        task.add_done_callback(self._presentation_tasks.discard)

    async def _snapshot_for_session(self, session: HarnessSession) -> dict:
        """Fence queued reads and discard results if workspace authority changes.

        In-thread samples cover queue delay; the final Store check covers
        locator/session changes while reading. Neither is a filesystem lock.
        """
        witness = await self.store.require_session_workspace_current(session)
        check = workspace_read_check(self.store, session, witness) if witness is not None else None

        def observe() -> dict:
            if check is not None:
                check()
            try:
                return snapshot(session.cwd, run_pytest=False)
            finally:
                if check is not None:
                    check()

        operation = asyncio.create_task(asyncio.to_thread(observe))
        try:
            result = await asyncio.shield(operation)
        except asyncio.CancelledError:
            # Cancelling the await does not stop the filesystem thread. Settle
            # this owned read before its pump reports observation shutdown.
            while not operation.done():
                try:
                    await asyncio.shield(operation)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not operation.cancelled():
                operation.exception()
            raise
        except Exception:
            await self.store.require_session_workspace_current(session)
            raise
        await self.store.require_session_workspace_current(session)
        return result

    async def _build_and_commit_event_plan(
        self,
        processing: dict,
        *,
        owner: str,
        reconcile_uncertain: bool,
    ) -> dict:
        """Build one acceptance-bound plan, then atomically persist its projections."""

        event, session, goal = await self._processing_inputs(processing)
        await self.store.require_session_workspace_current(session)
        _update_context_routing_state(session, event)
        await self._negotiate_capabilities(session)
        session.last_activity = event.ts
        live_session = await self.store.get_session_for_authority(
            session.id,
            require_goal_binding=goal is not None,
        )
        observation = event.metadata.get("pex_observer_snapshot")
        if isinstance(observation, dict):
            if (
                observation.get("schema") != "pex.codex-live-observation.v1"
                or session.harness_type != HarnessType.CODEX
                or observation.get("subscription_receipt")
                != session.metadata.get("subscription_receipt")
            ):
                raise ValueError("accepted shared observation binding is invalid")
            session.status = SessionStatus(observation["status"])
            activity = observation["last_activity"]
            session.last_activity = datetime.fromisoformat(activity) if activity else None
            session.metadata["observation_coverage"] = dict(observation["observation_coverage"])
        elif event.event_type == EventType.STOP:
            session.status = SessionStatus.STOPPED
        elif event.event_type == EventType.ERROR:
            session.status = SessionStatus.ERROR
        elif (
            live_session is not None
            and live_session.status == SessionStatus.DRIFTING
            and not _clears_observed_drift(event, goal)
        ):
            session.status = SessionStatus.DRIFTING
        else:
            session.status = SessionStatus.WORKING

        project_key = session.project_id or session.cwd
        plan_contexts: list[ContextItem] = []
        event_item: ContextItem | None = None
        if project_key and processing.get("project_id") and session.goal_id:
            event_item = item_from_event(project_key, session.goal_id, event)
            if event_item is not None:
                event_item = event_item.model_copy(
                    update={
                        "id": stable_event_artifact_id(
                            event.event_id,
                            "event_context",
                        )
                    }
                )
                plan_contexts.append(event_item)

        recent = (
            await self.store.recent_events_through_for_authority(
                session.id,
                event.event_id,
                goal_id=goal.id,
                project_id=project_key,
                harness_type=session.harness_type,
                limit=self.settings.max_recent_events,
            )
            if goal is not None and project_key
            else [event]
        )
        context_items: list[ContextItem] = []
        if project_key:
            context_items = await self.store.list_context_for_authority(
                project_key,
                goal_id=goal.id if goal is not None else None,
                limit=256,
            )
        health_items = [*context_items]
        if event_item is not None and all(item.id != event_item.id for item in health_items):
            health_items.append(event_item)
        health = assess_context_health(recent, health_items, now=event.ts)
        session.context_health = health.score
        session.metadata["context_health_signals"] = dict(health.signals)

        intervention_updates: list[Intervention] = []
        if event.event_type != EventType.STOP:
            intervention_updates = await self._observe_prior_intervention(
                session,
                event,
                persist=False,
            )

        scores = score_trajectory(recent, goal)
        scores.features.update(health.planner_features())
        for bucket in await self.store.agent_fingerprint_stats(
            session_id=session.id,
            accepted_event_id=event.event_id,
        ):
            if bucket.get("harness") == session.harness_type.value:
                scores.features.update(fingerprint_score_features(bucket))
                break
        claims: list[dict] = []
        verification: dict = {}
        notes = ""
        stored_decisions = (
            await self.store.list_decisions_for_authority(goal.id) if goal is not None else []
        )
        plan_decisions: list[Decision] = []

        if (
            event.event_type in {EventType.SHELL, EventType.TOOL_CALL}
            and event.phase == EventPhase.DURING
            and session.cwd
            and goal is not None
            and required_files(goal)
        ):
            workspace: dict = {}
            try:
                workspace = await self._snapshot_for_session(session)
            except WorkspaceAuthorityError:
                raise
            except Exception:
                workspace = {}
            missing = missing_required_files(goal, workspace)
            if missing:
                scores.features["missing_prerequisites"] = missing
        if (
            event.event_type in {EventType.FILE_EDIT, EventType.SHELL, EventType.TOOL_CALL}
            and session.goal_id
        ):
            duplicate = await self._duplicate_sibling_work(session, event)
            if duplicate:
                scores.features["duplicate_work"] = duplicate

        if event.event_type == EventType.STOP:
            claims = extract_claims(recent)
            scores.features["claims"] = claims
            workspace = {}
            workspace_snapshot_state = "unavailable"
            workspace_snapshot_reason: str | None = (
                "session_cwd_unavailable" if not session.cwd else None
            )
            if session.cwd:
                try:
                    workspace = await self._snapshot_for_session(session)
                    if workspace and not workspace.get("error"):
                        workspace_snapshot_state = "inspected"
                        workspace_snapshot_reason = None
                    else:
                        workspace_snapshot_reason = str(
                            workspace.get("error") or "workspace_snapshot_empty"
                        )[:256]
                except WorkspaceAuthorityError:
                    raise
                except Exception as exc:
                    workspace = {}
                    workspace_snapshot_reason = f"workspace_snapshot_failed:{type(exc).__name__}"
            verification = verify_claims(claims, recent, goal, workspace)
            probe_kind = required_verification_probe_kind(
                claims,
                recent,
                goal,
                verification,
            )
            probe: VerificationProbe | None = None
            probe_unavailable_reason: str | None = None
            if probe_kind is not None and goal is not None:
                if not session.cwd:
                    probe_unavailable_reason = "session_cwd_unavailable"
                elif not Path(session.cwd).is_absolute():
                    probe_unavailable_reason = "session_cwd_not_absolute"
                else:
                    try:
                        probe = VerificationProbe(
                            id=stable_event_artifact_id(event.event_id, "verification_probe"),
                            kind=probe_kind,
                            session_id=session.id,
                            harness_type=session.harness_type,
                            project_id=session.project_id or goal.project_id,
                            goal_id=goal.id,
                            request_event_id=event.event_id,
                            cwd=session.cwd,
                            relative_targets=verification_probe_targets(probe_kind, goal),
                        )
                    except (TypeError, ValueError):
                        probe_unavailable_reason = "probe_binding_invalid"
            verification["evidence_gathering"] = EvidenceGatheringReceipt(
                state=(
                    EvidenceGatheringState.UNAVAILABLE
                    if probe_kind is not None and probe is None
                    else EvidenceGatheringState.INSPECTED
                ),
                sources=[
                    "recent_events",
                    *(["workspace_snapshot"] if session.cwd else []),
                ],
                recent_events="inspected",
                workspace_snapshot=workspace_snapshot_state,
                workspace_snapshot_reason=workspace_snapshot_reason,
                claim_count=len(claims),
                probe=probe,
                reason=(
                    "typed_verification_probe_available"
                    if probe is not None
                    else (
                        f"verification_probe_unavailable:{probe_unavailable_reason}"
                        if probe_kind is not None
                        else "bounded_existing_evidence_only"
                    )
                ),
            ).model_dump(mode="json")
            intervention_updates = await self._observe_prior_intervention(
                session,
                event,
                verification,
                persist=False,
            )
            scores.features["verification"] = verification
            scores.features["prefetched_evidence"] = compact_workspace_evidence(workspace)
            scores.features["abandoned_background"] = confirm_abandoned_background(
                find_abandoned_background(recent)
            )
            await self._annotate_speculative_stop(
                session,
                goal,
                stored_decisions,
                scores,
                verification,
                recent,
                health_items,
                persist_session=False,
            )
            if verification.get("status") == "contradicted":
                scores.claim_contradiction = max(scores.claim_contradiction, 0.88)
            if project_key and processing.get("project_id") and session.goal_id:
                for index, claim in enumerate(claims):
                    source_ref = str(claim.get("source_event_id") or event.event_id)
                    plan_contexts.append(
                        ContextItem(
                            id=stable_event_artifact_id(
                                event.event_id,
                                "claim_context",
                                index=index,
                            ),
                            project_id=project_key,
                            goal_id=session.goal_id,
                            kind=ContextKind.CLAIM,
                            content=str(claim.get("statement") or ""),
                            source_refs=list(dict.fromkeys([source_ref, event.event_id])),
                            provenance=SourceKind.HARNESS,
                            confidence=float(claim.get("confidence") or 0.5),
                            relevance_tags=[
                                str(claim.get("kind") or "claim"),
                                str(claim.get("polarity") or ""),
                            ],
                            valid_from=event.ts,
                            sensitivity=Sensitivity.INTERNAL,
                            metadata={**claim, "source_session_id": session.id},
                        )
                    )
                if session.goal_id:
                    verified_items = items_from_verification(
                        project_key,
                        session.goal_id,
                        event,
                        verification,
                        recent,
                    )
                    for index, item in enumerate(verified_items):
                        plan_contexts.append(
                            item.model_copy(
                                update={
                                    "id": stable_event_artifact_id(
                                        event.event_id,
                                        "verification_context",
                                        index=index,
                                    ),
                                    "source_refs": list(
                                        dict.fromkeys([*item.source_refs, event.event_id])
                                    ),
                                }
                            )
                        )
            notes = (
                "claims:"
                + ";".join(f"{claim.get('kind')}={claim.get('statement')}" for claim in claims)
                if claims
                else "no_completion_claims_extracted"
            )
            notes += f";verify={verification.get('status')}"
        elif event.event_type == EventType.USER_PROMPT:
            lint = lint_prompt(goal, event.message_delta or "", decisions=stored_decisions)
            notes = lint.classification.value
            normalized_codex_user = (
                event.harness_type == HarnessType.CODEX
                and event.metadata.get("raw_type") == "userMessage"
            )
            content_status = event.metadata.get("content_status")
            complete_codex_user = (
                isinstance(content_status, str)
                and content_status in {"complete", "legacy_top_level"}
                and event.metadata.get("content_truncated") is False
                and event.metadata.get("content_redacted") is False
            )
            if normalized_codex_user and not complete_codex_user:
                # Retain the prompt for provenance and stale-action fencing,
                # but an observed prefix cannot authorize a ledger override.
                notes = "observed_incomplete_user_input:override_authority_not_established"
            elif lint.classification is PromptClass.CONTRADICTION and lint.matched_constraints:
                notes = f"{lint.classification.value}:{lint.matched_constraints[0][:200]}"
            elif lint.classification is PromptClass.OVERRIDE and goal is not None:
                projections = self._explicit_override_projections(
                    session,
                    goal,
                    event,
                    stable=True,
                )
                if projections is not None:
                    decision, context = projections
                    plan_decisions.append(decision)
                    plan_contexts.append(context)
                    notes = f"{lint.classification.value}:recorded"
                else:
                    notes = "observed_user_input:override_authority_not_established"
        elif event.event_type in {
            EventType.AGENT_RESPONSE,
            EventType.SHELL,
            EventType.TOOL_CALL,
            EventType.FILE_EDIT,
        }:
            lint = lint_prompt(
                goal,
                event.message_delta or event.command or "",
                decisions=stored_decisions,
            )
            if lint.classification is PromptClass.CONTRADICTION and lint.matched_constraints:
                notes = f"agent_contradiction:{lint.matched_constraints[0][:200]}"

        deferred = {
            "auto_handoff": "auto_handoff_deferred_until_multi_effect_recovery",
            "remote_attention": "remote_attention_deferred_until_multi_effect_recovery",
        }
        cursor_stop_terminated = (
            event.harness_type == HarnessType.CURSOR
            and event.event_type == EventType.STOP
            and event.metadata.get("tool_status") in {"aborted", "error"}
        )
        if (
            session.supervision_paused
            or self.supervision_paused
            or (goal is not None and goal.paused)
            or cursor_stop_terminated
        ):
            reason = (
                "cursor_stop_terminated_without_followup"
                if cursor_stop_terminated
                else "global_supervision_paused"
                if self.supervision_paused
                else ("goal_paused" if goal is not None and goal.paused else "session_paused")
            )
            plan = self._event_plan_envelope(
                processing=processing,
                context_items=plan_contexts,
                decisions=plan_decisions,
                intervention_updates=intervention_updates,
                intervention=None,
                effect_kind=None,
                required_capability=None,
                details={**deferred, "terminal_reason": reason},
            )
            receipt = {
                "schema": "pex.event-processing.receipt.v1",
                "event_id": event.event_id,
                "status": "complete",
                "intervention": None,
                "terminal_reason": reason,
            }
            committed = await self.store.commit_event_plan(
                event_id=event.event_id,
                owner=owner,
                plan=plan,
                session=session,
                context_items=plan_contexts,
                decisions=plan_decisions,
                intervention_updates=intervention_updates,
                receipt=receipt,
                reconcile_uncertain=reconcile_uncertain,
            )
            await self._publish_event_plan_commit(
                intervention_updates=intervention_updates,
                intervention=None,
            )
            return committed

        # Generic adapter methods remain observation-only. Tell the supervisor
        # about the distinct private action route without persisting invented
        # send/resume capability flags onto the shared session.
        if session.metadata.get("connection_kind") == "codex_shared":
            from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter

            shared_adapter = self.adapters.for_session(session.id)
            if isinstance(shared_adapter, CodexSharedAdapter) and shared_adapter._connected():
                correction_status = await self.store.get_autonomous_correction_grant_status(
                    session.id,
                )
                if correction_status.get("enabled") is True:
                    permission_note = (
                        "Standing operator permission enables the private claimed-correction route "
                        "for this attached goal: SEND_NUDGE, INJECT_CONTEXT, REQUEST_VERIFICATION, "
                        "CONTINUE_SESSION with exact evidence-grounded text. Generic adapter "
                        "send/resume flags remain false; this separate route still requires "
                        "current local policy and input/effect authority. "
                        "Prefer NOOP when justified."
                    )
                else:
                    permission_note = "Autonomous correction permission is disabled."
                # Existing trusted prefixes are consumed by deterministic safety
                # triage. Preserve them and the protocol's bounded notes field.
                notes = notes[:65_536 - len(permission_note) - 2] + "\n\n" + permission_note

        request = SupervisorRequest(
            session=session,
            goal=goal,
            event=event,
            recent_events=recent,
            scores=scores,
            autonomy=self.settings.autonomy,
            notes=notes,
            supervisor_context=build_supervisor_context(
                session,
                [*context_items, *plan_contexts],
                [*stored_decisions, *plan_decisions],
                now=event.ts,
            ),
        )
        planner_effect: dict | None = await self.store.get_event_effect(
            event.event_id,
            "planner",
        )
        planning_snapshot = self._event_planning_snapshot(
            claims=claims,
            verification=verification,
            context_items=plan_contexts,
            decisions=plan_decisions,
            intervention_updates=intervention_updates,
        )
        if reconcile_uncertain:
            if planner_effect is None or not isinstance(planner_effect.get("payload"), dict):
                raise RuntimeError("uncertain planner effect is missing its durable request")
            raw_request = planner_effect["payload"].get("request")
            if not isinstance(raw_request, dict):
                raise RuntimeError("uncertain planner effect request is missing")
            raw_snapshot = planner_effect["payload"].get("planning_snapshot")
            (
                claims,
                verification,
                plan_contexts,
                plan_decisions,
                intervention_updates,
            ) = self._restore_event_planning_snapshot(raw_snapshot)
            planning_snapshot = raw_snapshot
            request = SupervisorRequest.model_validate(raw_request)
            result = self._reconcile_supervisor_effect(
                request,
                planner_effect,
                reason="prior_planner_dispatch_uncertain",
            )
        else:
            result, planner_effect, planning_snapshot = await self._resolve_durable_supervisor(
                request,
                event,
                owner=owner,
                planning_snapshot=planning_snapshot,
            )
            # Record an actual inference outcome before rejecting stale use of
            # it. This never describes an already-called model as unexecuted.
            await self.store.require_session_workspace_current(request.session)
            raw_request = (planner_effect.get("payload") or {}).get("request")
            if isinstance(raw_request, dict):
                request = SupervisorRequest.model_validate(raw_request)
            (
                claims,
                verification,
                plan_contexts,
                plan_decisions,
                intervention_updates,
            ) = self._restore_event_planning_snapshot(planning_snapshot)
        reconcile_plan = bool(
            reconcile_uncertain
            or (planner_effect is not None and planner_effect.get("state") == "delivery_uncertain")
        )
        session = request.session.model_copy(deep=True)
        action = result.action
        if action.session_id != session.id or action.goal_id != session.goal_id:
            result.action = _action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": "supervisor_action_identity_mismatch",
                    "evidence": ["supervisor_action_identity_mismatch"],
                },
            )
            result.diagnosis = "supervisor_action_identity_mismatch"
            result.traces = [
                *result.traces[-255:],
                "supervisor_action_identity_mismatch",
            ]
            result.inference_status = "failed"
            action = result.action
        if not session.goal_id and action.type != InterventionType.NOOP:
            result.action = _action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": "unattached_session_cannot_bind_intervention",
                    "evidence": ["unattached_session_cannot_bind_intervention"],
                },
            )
            result.diagnosis = "unattached_session_cannot_bind_intervention"
            result.traces = [
                *result.traces[-255:],
                "unattached_session_cannot_bind_intervention",
            ]
            result.inference_status = "failed"
            action = result.action
        cleaned_payload, _ = redact_mapping(action.payload)
        action.payload = cleaned_payload or {}
        action.evidence = [redact_text(item)[0] or "" for item in action.evidence]
        result.traces = [redact_text(item)[0] or "" for item in result.traces]
        if action.type == InterventionType.REQUEST_VERIFICATION:
            raw_gathering = verification.get("evidence_gathering")
            try:
                minted_gathering = (
                    EvidenceGatheringReceipt.model_validate(raw_gathering)
                    if isinstance(raw_gathering, dict)
                    else None
                )
            except (TypeError, ValueError):
                minted_gathering = None
            if minted_gathering is None or _exact_action_probe(action, minted_gathering) is None:
                result.action = _action_from_proposal(
                    request,
                    {
                        "type": "NOOP",
                        "rationale": "verification_probe_not_bridge_minted",
                        "evidence": ["verification_probe_not_bridge_minted"],
                    },
                )
                result.diagnosis = "verification_probe_not_bridge_minted"
                result.traces = [
                    *result.traces[-255:],
                    "verification_probe_not_bridge_minted",
                ]
                result.inference_status = "failed"
                action = result.action
        if event.phase == EventPhase.BEFORE and action.type not in {
            InterventionType.NOOP,
            InterventionType.RESPOND_PERMISSION,
            InterventionType.ASK_HUMAN,
            InterventionType.ANNOTATE,
        }:
            result.action = _action_from_proposal(
                request,
                {
                    "type": "NOOP",
                    "rationale": "deferred_pre_hook",
                    "evidence": ["deferred_pre_hook"],
                },
            )
            action = result.action
            result.diagnosis = f"{result.diagnosis}:deferred_pre_hook"
        command = event.command or str(action.payload.get("command") or "")
        verdict = self.policy.decide(action, command=command)
        action_taken = action.type.value
        required_capability = _required_capability(action, verdict)
        private_correction_granted = False
        if required_capability in {"send_message", "resume"}:
            from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
            from pex_bridge.codex_correction import requires_correction

            if (
                verdict == PolicyVerdict.ALLOW
                and requires_correction(session, action.model_dump(mode="json"))
                and isinstance(self.adapters.for_session(session.id), CodexSharedAdapter)
            ):
                grant_status = await self.store.get_autonomous_correction_grant_status(session.id)
                private_correction_granted = grant_status.get("enabled") is True
        if required_capability and not (
            session.capabilities.get(required_capability, False) or private_correction_granted
        ):
            action.evidence.append(f"missing_capability:{required_capability}")
            action.rationale = f"Action skipped because the adapter lacks {required_capability}."
            result.diagnosis = f"{result.diagnosis}:missing_capability:{required_capability}"
            verdict = PolicyVerdict.DENY
            action_taken = InterventionType.NOOP.value

        intervention: Intervention | None = None
        main_effect: dict | None = None
        receipt: dict | None = None
        local_outcome: str | None = None
        if (
            action.type == InterventionType.NOOP
            and event.event_type != EventType.STOP
            and result.transport_status != "failed"
            and result.inference_status not in {"failed", "timeout"}
        ):
            local_outcome = None
        elif verdict == PolicyVerdict.DENY:
            local_outcome = "denied_by_policy"
        elif action.type == InterventionType.NOOP:
            local_outcome = "noop"
        elif action.type == InterventionType.FRESH_HANDOFF:
            local_outcome = "auto_handoff_deferred_until_multi_effect_recovery"
        elif action.type == InterventionType.NOTIFY:
            local_outcome = "remote_attention_deferred_until_multi_effect_recovery"
        elif verdict == PolicyVerdict.ASK_HUMAN:
            if action.type == InterventionType.RESPOND_PERMISSION:
                response_mode = str(session.capabilities.get("permission_response_mode") or "none")
                local_outcome = (
                    "permission_delegated_to_harness"
                    if response_mode in {"inline", "both"}
                    else "permission_awaiting_human"
                )
            else:
                local_outcome = (
                    "escalated" if action.type == InterventionType.ASK_HUMAN else "awaiting_human"
                )
            if session.status != SessionStatus.STOPPED or action.type in {
                InterventionType.START_AGENT,
                InterventionType.STOP_AGENT,
                InterventionType.FORK_PROBE,
            }:
                session.status = SessionStatus.NEEDS_DECISION
        elif action.type == InterventionType.ASK_HUMAN:
            local_outcome = "escalated"
            if session.status != SessionStatus.STOPPED:
                session.status = SessionStatus.NEEDS_DECISION
        elif action.type == InterventionType.ANNOTATE:
            local_outcome = "annotated"
        elif action.type in {
            InterventionType.START_AGENT,
            InterventionType.STOP_AGENT,
            InterventionType.FORK_PROBE,
        }:
            local_outcome = "lifecycle_human_authorization_required"
            session.status = SessionStatus.NEEDS_DECISION

        if local_outcome is None and action.type != InterventionType.NOOP:
            if goal is None or not project_key:
                result.action = _action_from_proposal(
                    request,
                    {
                        "type": "NOOP",
                        "rationale": "unattached_session_cannot_bind_intervention",
                        "evidence": ["unattached_session_cannot_bind_intervention"],
                    },
                )
                action = result.action
                result.diagnosis = "unattached_session_cannot_bind_intervention"
                result.traces = [
                    *result.traces[-255:],
                    "unattached_session_cannot_bind_intervention",
                ]
                result.inference_status = "failed"
                action_taken = InterventionType.NOOP.value
                local_outcome = "unattached_session_cannot_bind_intervention"
            prior_interventions = await self.store.list_interventions_for_authority(
                session.id,
                goal_id=goal.id,
                project_id=project_key,
                harness_type=session.harness_type,
            )
            accepted_at = datetime.fromisoformat(str(processing["accepted_at"]))
            prior_at: datetime | None = None
            for prior in prior_interventions:
                if prior.action_taken != action.type.value:
                    continue
                raw_at = prior.metadata.get("event_accepted_at")
                try:
                    candidate = datetime.fromisoformat(str(raw_at)) if raw_at else prior.created_at
                except ValueError:
                    candidate = prior.created_at
                if candidate <= accepted_at and (prior_at is None or candidate > prior_at):
                    prior_at = candidate
            cooldown_allowed = (
                prior_at is None
                or (accepted_at - prior_at).total_seconds() >= action.cooldown_seconds
                or (
                    action.type == InterventionType.REQUEST_VERIFICATION
                    and bool(verification.get("supersedes_probe_id"))
                )
            )
            if not cooldown_allowed:
                verdict = PolicyVerdict.DENY
                action_taken = "SUPPRESSED_COOLDOWN"
                local_outcome = "suppressed_by_cooldown"

        intervention_id = stable_event_artifact_id(event.event_id, "intervention")
        if local_outcome is not None:
            _record_verification_dispatch(
                verification,
                action,
                verdict,
                local_outcome,
            )
            intervention = self._intervention(
                event=event,
                session=session,
                result=result,
                verdict=verdict,
                outcome=local_outcome,
                action_taken=action_taken,
                claims=claims,
                verification=verification,
                intervention_id=intervention_id,
                created_at=event.ts,
            )
        elif action.type != InterventionType.NOOP:
            intervention = self._intervention(
                event=event,
                session=session,
                result=result,
                verdict=verdict,
                outcome="delivery_reserved",
                action_taken=action_taken,
                claims=claims,
                verification=verification,
                intervention_id=intervention_id,
                created_at=event.ts,
            )
        if not session.goal_id or goal is None:
            intervention = None
            main_effect = None
        if intervention is not None:
            intervention.metadata["event_accept_seq"] = int(processing["accept_seq"])
            intervention.metadata["event_accepted_at"] = processing["accepted_at"]
            if request.supervisor_context is not None:
                context_packet = request.supervisor_context.model_dump(mode="json", by_alias=True)
                # These IDs were offered to inference, not proven to have been
                # selected, understood or used by the model. The exact packet
                # is retained in the immutable planner request for replay.
                intervention.metadata["supervisor_context_reference"] = {
                    "offered_context_ids": list(request.supervisor_context.offered_context_ids),
                    "offered_decision_ids": list(request.supervisor_context.offered_decision_ids),
                    "observed_at": request.supervisor_context.observed_at.isoformat(),
                    "packet_sha256": hashlib.sha256(
                        json.dumps(
                            context_packet, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False,
                        ).encode("utf-8")
                    ).hexdigest(),
                }

        if intervention is not None and local_outcome is None:
            # The Store derives shared-worker correction provenance from the
            # accepted event and its published workspace, never model metadata.
            # It revalidates this exact envelope inside commit_event_plan.
            effect_payload = await self.store.prepare_main_effect_payload(
                event_id=event.event_id,
                intervention_id=intervention.id,
                action=intervention.proposed_action.model_dump(mode="json"),
                required_capability=required_capability,
            )
            effect_payload_json = json.dumps(
                effect_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            main_effect = {
                "effect_key": "main",
                "kind": "worker_action",
                "target_session_id": session.id,
                "payload": effect_payload,
                "request_hash": hashlib.sha256(effect_payload_json.encode("utf-8")).hexdigest(),
            }
        else:
            receipt = {
                "schema": "pex.event-processing.receipt.v1",
                "event_id": event.event_id,
                "status": "complete",
                "intervention": (
                    intervention.model_dump(mode="json") if intervention is not None else None
                ),
                "terminal_reason": local_outcome or "no_action",
            }

        plan = self._event_plan_envelope(
            processing=processing,
            context_items=plan_contexts,
            decisions=plan_decisions,
            intervention_updates=intervention_updates,
            intervention=intervention,
            effect_kind="worker_action" if main_effect is not None else None,
            required_capability=required_capability,
            details={
                **deferred,
                "supervisor_result": result.model_dump(mode="json"),
                "planner_effect_id": (
                    planner_effect.get("effect_id") if planner_effect is not None else None
                ),
                "planner_effect_state": (
                    planner_effect.get("state") if planner_effect is not None else None
                ),
                "reconciliation": (
                    {
                        "status": "deterministic_reconciled",
                        "reason": "planner_dispatch_uncertain",
                        "late_semantic_result": "ignored",
                    }
                    if reconcile_plan
                    else None
                ),
                "claims": claims,
                "verification": verification,
            },
        )
        followup_kinds: list[str] = []
        if session.goal_id and event.event_type in {
            EventType.AGENT_RESPONSE,
            EventType.STOP,
        }:
            followup_kinds.append("auto_handoff")
        if (
            intervention is not None
            and intervention.policy_verdict == PolicyVerdict.ASK_HUMAN
            and intervention.proposed_action.type
            not in {InterventionType.NOTIFY, InterventionType.RESPOND_PERMISSION}
        ):
            followup_kinds.append("human_attention")
        plan["followup_kinds"] = followup_kinds
        committed = await self.store.commit_event_plan(
            event_id=event.event_id,
            owner=owner,
            plan=plan,
            session=session,
            context_items=plan_contexts,
            decisions=plan_decisions,
            intervention_updates=intervention_updates,
            intervention=intervention,
            main_effect=main_effect,
            followup_kinds=followup_kinds,
            receipt=receipt,
            reconcile_uncertain=reconcile_plan,
        )
        await self._publish_event_plan_commit(
            intervention_updates=intervention_updates,
            intervention=intervention,
        )
        return committed

    @staticmethod
    def _main_effect_state(outcome: str) -> str:
        if "delivery_uncertain" in outcome:
            return "delivery_uncertain"
        delivered = {
            "continued",
            "focused",
            "handoff_injected",
            "overlay_applied",
            "overlay_reverted",
            "permission_allow",
            "permission_allow_inline",
            "permission_deny",
            "permission_deny_inline",
            "sent",
            "verification_requested",
        }
        return "delivered" if outcome in delivered else "failed"

    async def _seal_main_event_effect(
        self,
        *,
        processing: dict,
        effect: dict,
        reserved: Intervention,
        session: HarnessSession | None,
        outcome: str,
        effect_state: str,
        code: str,
        publish: bool,
        effect_result: dict | None = None,
    ) -> Intervention:
        plan = processing.get("plan")
        if not isinstance(plan, dict):
            raise RuntimeError("planned event is missing its durable plan")
        final = reserved.model_copy(deep=True)
        final.result = outcome
        verification = dict(plan.get("verification") or {})
        _record_verification_dispatch(
            verification,
            final.proposed_action,
            final.policy_verdict,
            outcome,
        )
        final.metadata["verification"] = verification
        final.metadata["delivery"] = outcome
        final.metadata["delivery_code"] = code
        final.metadata["effect_id"] = effect["effect_id"]
        final.metadata["effect_state"] = effect_state
        worker_delivery_receipt = (
            effect_result.get("worker_delivery_receipt")
            if isinstance(effect_result, dict)
            else None
        )
        hook_preparation_receipt = (
            effect_result.get("hook_preparation_receipt")
            if isinstance(effect_result, dict)
            else None
        )
        if hook_preparation_receipt is not None:
            if (
                session is None
                or worker_delivery_receipt is not None
                or effect_state != "delivery_uncertain"
                or outcome != "hook_followup_prepared_delivery_uncertain"
            ):
                raise RuntimeError("Cursor hook preparation receipt is corrupt")
            normalized_preparation = validate_cursor_hook_preparation_receipt(
                hook_preparation_receipt,
                session=session,
                trigger_event_id=processing["event_id"],
            )
            final.metadata["hook_preparation_receipt"] = normalized_preparation
        if worker_delivery_receipt is not None:
            if session is None:
                raise RuntimeError("worker delivery receipt is corrupt")
            try:
                normalized_receipt = validate_worker_delivery_receipt_binding(
                    worker_delivery_receipt,
                    target_session_id=final.session_id,
                    vendor_session_id=session.vendor_session_id,
                    harness_type=session.harness_type,
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError("worker delivery receipt is corrupt") from exc
            if (
                worker_delivery_receipt != normalized_receipt
                or effect_state != "delivered"
                or not isinstance(effect_result, dict)
                or effect_result.get("status") != effect_state
                or effect_result.get("outcome") != outcome
                or effect_result.get("code") != code
                or final.proposed_action.type
                not in {
                    InterventionType.SEND_NUDGE,
                    InterventionType.INJECT_CONTEXT,
                    InterventionType.CONTINUE_SESSION,
                    InterventionType.REQUEST_VERIFICATION,
                    InterventionType.FRESH_HANDOFF,
                }
            ):
                raise RuntimeError("worker delivery receipt is corrupt")
            final.metadata["worker_delivery_receipt"] = dict(worker_delivery_receipt)
        if effect_state == "delivery_uncertain":
            final.outcome = "worker_delivery_uncertain"
            final.helped = None
        if (
            session is not None
            and effect_state == "delivered"
            and _requests_drifting(final.proposed_action)
        ):
            session.status = SessionStatus.DRIFTING
        if effect_result is None:
            effect_result = {
                "status": effect_state,
                "outcome": outcome,
                "code": code,
                "effect_id": effect["effect_id"],
            }
        downstream_operation_id = effect.get("downstream_operation_id")
        receipt = {
            "schema": "pex.event-processing.receipt.v1",
            "event_id": processing["event_id"],
            "status": "complete",
            "effect_id": effect["effect_id"],
            "effect_state": effect_state,
            "effect_result": effect_result,
            "downstream_operation_id": downstream_operation_id,
            "intervention": final.model_dump(mode="json"),
        }
        await self.store.finalize_event_processing(
            event_id=str(processing["event_id"]),
            effect_state=effect_state,
            effect_result=effect_result,
            intervention=final,
            receipt=receipt,
            session=session,
            downstream_operation_id=downstream_operation_id,
        )
        if publish:
            await self._publish_event_plan_commit(
                intervention_updates=[],
                intervention=final,
            )
        return final

    async def _reconcile_overlay_child_before_live_gates(
        self,
        processing: dict,
        effect: dict,
    ) -> bool:
        """Seal an exact overlay child result without reacquiring live authority.

        Overlay reservation binds the child to the main effect before adapter
        I/O. Once that link exists, the immutable child receipt is the only
        authority for parent recovery. Live session/goal reads are deliberately
        excluded: containment and terminal replay must survive pause, quarantine,
        and project A-to-B rebinding.

        ``True`` means the caller must not claim or dispatch the main effect.
        The child is either still in flight or its exact terminal result has
        already been reconciled into the event receipt.
        """

        plan = processing.get("plan")
        if not isinstance(plan, dict) or plan.get("effect_kind") != "worker_action":
            return False
        raw_action = plan.get("action")
        if not isinstance(raw_action, dict):
            return False
        action_type = str(raw_action.get("type") or "")
        expected_kind = {
            InterventionType.APPLY_OVERLAY.value: "apply",
            InterventionType.REVERT_OVERLAY.value: "revert",
        }.get(action_type)
        if expected_kind is None:
            return False
        if effect.get("kind") != "worker_action" or effect.get(
            "target_session_id"
        ) != processing.get("session_id"):
            raise RuntimeError("overlay parent effect binding is corrupt")

        operation_id = effect.get("downstream_operation_id")
        if not isinstance(operation_id, str) or not operation_id:
            if effect.get("state") == "dispatching":
                # A current-boot executor may still be between the parent marker
                # and the child reservation. Never steal or redispatch it.
                return True
            if effect.get("state") in EVENT_EFFECT_TERMINAL_STATES:
                # Startup recovery may observe the exact crash window after the
                # parent marker but before overlay reservation. There is no child
                # to inspect; the terminal parent receipt is the durable truth.
                intervention_id = str(plan.get("intervention_id") or "")
                reserved = await self.store.get_intervention(intervention_id)
                if reserved is None:
                    raise RuntimeError("planned overlay intervention disappeared")
                if (
                    reserved.session_id != processing.get("session_id")
                    or reserved.goal_id != processing.get("goal_id")
                    or reserved.proposed_action.model_dump(mode="json") != raw_action
                ):
                    raise RuntimeError("terminal overlay parent intervention differs")
                parent_result = effect.get("result")
                if not isinstance(parent_result, dict):
                    raise RuntimeError("terminal overlay parent result is corrupt")
                parent_state = str(effect["state"])
                code = str(parent_result.get("code") or parent_state)
                outcome = str(parent_result.get("outcome") or code)
                await self._seal_main_event_effect(
                    processing=processing,
                    effect=effect,
                    reserved=reserved,
                    session=None,
                    outcome=outcome,
                    effect_state=parent_state,
                    code=code,
                    publish=True,
                    effect_result=parent_result,
                )
                return True
            return False

        operation = await self.store.get_overlay_operation_for_authority(
            operation_id,
            require_live=False,
        )
        if operation is None:
            raise RuntimeError("linked overlay child operation disappeared")
        intervention_id = str(plan.get("intervention_id") or "")
        effect_payload = effect.get("payload")
        if not isinstance(effect_payload, dict):
            raise RuntimeError("overlay parent effect payload is corrupt")
        if (
            operation.get("operation_id") != operation_id
            or operation.get("parent_effect_id") != effect.get("effect_id")
            or operation.get("owner_intervention_id") != intervention_id
            or operation.get("session_id") != processing.get("session_id")
            or operation.get("kind") != expected_kind
            or effect_payload.get("intervention_id") != intervention_id
            or effect_payload.get("action") != raw_action
        ):
            raise RuntimeError("overlay parent/child immutable binding differs")
        action_payload = raw_action.get("payload")
        if not isinstance(action_payload, dict):
            raise RuntimeError("overlay action payload is corrupt")
        expected_overlay_id = (
            (action_payload.get("overlay") or {}).get("id")
            if expected_kind == "apply" and isinstance(action_payload.get("overlay"), dict)
            else action_payload.get("overlay_id")
        )
        if expected_overlay_id != operation.get("overlay_id"):
            raise RuntimeError("overlay action and child target differ")

        child_state = str(operation.get("state") or "")
        if child_state in {"reserved", "dispatching"}:
            # This is live current-boot work. It owns the one start CAS.
            return True
        if child_state not in EVENT_EFFECT_TERMINAL_STATES:
            raise RuntimeError("overlay child has an invalid lifecycle state")

        reserved = await self.store.get_intervention(intervention_id)
        if reserved is None:
            raise RuntimeError("planned overlay intervention disappeared")
        if (
            reserved.session_id != processing.get("session_id")
            or reserved.goal_id != processing.get("goal_id")
            or reserved.proposed_action.model_dump(mode="json") != raw_action
        ):
            raise RuntimeError("overlay child intervention binding differs")

        child_result = operation.get("result")
        if child_result is None:
            child_result = {}
        if not isinstance(child_result, dict):
            raise RuntimeError("terminal overlay child result is corrupt")
        code = str(child_result.get("code") or child_state)
        effect_result = {
            **child_result,
            "status": child_state,
            "code": code,
            "effect_id": effect["effect_id"],
            "outcome": code,
            "downstream_operation_id": operation_id,
        }
        if effect.get("state") in EVENT_EFFECT_TERMINAL_STATES and (
            effect.get("state") != child_state or effect.get("result") != effect_result
        ):
            raise RuntimeError("terminal overlay parent differs from its child receipt")
        await self._seal_main_event_effect(
            processing=processing,
            effect=effect,
            reserved=reserved,
            session=None,
            outcome=code,
            effect_state=child_state,
            code=code,
            publish=True,
            effect_result=effect_result,
        )
        return True

    async def _durably_reconcile_overlay_child(
        self,
        processing: dict,
        effect: dict,
    ) -> bool:
        """Retain and shield exact parent/child finalization from cancellation."""

        completion = asyncio.create_task(
            self._reconcile_overlay_child_before_live_gates(processing, effect)
        )
        self._overlay_reconciliation_tasks.add(completion)
        completion.add_done_callback(self._overlay_reconciliation_tasks.discard)
        cancelled = False
        while not completion.done():
            try:
                await asyncio.shield(completion)
            except asyncio.CancelledError:
                # Each cancellation applies only to the transient shield. Keep
                # waiting through repeated cancellation until the Store seal is
                # durably terminal, then propagate cancellation to the caller.
                cancelled = True
        result = completion.result()
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def _durably_refresh_overlay_child(
        self,
        processing: dict,
    ) -> tuple[bool, dict]:
        """Shield the post-executor parent refresh and child reconciliation."""

        async def refresh() -> tuple[bool, dict]:
            effect = await self.store.get_event_effect(str(processing["event_id"]), "main")
            if effect is None:
                raise RuntimeError("planned event main effect disappeared")
            handled = await self._reconcile_overlay_child_before_live_gates(
                processing,
                effect,
            )
            return handled, effect

        completion = asyncio.create_task(refresh())
        self._overlay_reconciliation_tasks.add(completion)
        completion.add_done_callback(self._overlay_reconciliation_tasks.discard)
        cancelled = False
        while not completion.done():
            try:
                await asyncio.shield(completion)
            except asyncio.CancelledError:
                cancelled = True
        result = completion.result()
        if cancelled:
            raise asyncio.CancelledError
        return result

    async def _durably_settle_main_result(
        self, *, processing: dict, reserved: Intervention, session: HarnessSession,
        outcome: str, effect_state: str, code: str, publish: bool,
        worker_delivery_receipt: dict | None = None,
        hook_preparation_receipt: dict | None = None,
    ) -> None:
        """Own the entire post-executor refresh/seal through observer cancellation."""

        async def finish() -> None:
            handled, effect = await self._durably_refresh_overlay_child(processing)
            if handled:
                return
            effect_result = None
            if worker_delivery_receipt is not None or hook_preparation_receipt is not None:
                effect_result = {
                    "status": effect_state, "outcome": outcome,
                    "code": code, "effect_id": effect["effect_id"],
                }
                if worker_delivery_receipt is not None:
                    effect_result["worker_delivery_receipt"] = worker_delivery_receipt
                if hook_preparation_receipt is not None:
                    effect_result["hook_preparation_receipt"] = hook_preparation_receipt
            await self._seal_main_event_effect(
                processing=processing, effect=effect, reserved=reserved, session=session,
                outcome=outcome, effect_state=effect_state, code=code, publish=publish,
                effect_result=effect_result,
            )

        completion = asyncio.create_task(finish(), name="pex-main-effect-settlement")
        self._main_effect_settlement_tasks.add(completion)
        completion.add_done_callback(self._main_effect_settlement_tasks.discard)
        cancelled = False
        while not completion.done():
            try:
                await asyncio.shield(completion)
            except asyncio.CancelledError:
                cancelled = True
        completion.result()
        if cancelled:
            raise asyncio.CancelledError

    async def _resume_planned_event(self, processing: dict, *, owner: str) -> None:
        current = await self.store.get_event_processing(str(processing["event_id"]))
        if current is None:
            raise RuntimeError("planned event processing row disappeared")
        if current["state"] in EVENT_PROCESSING_TERMINAL_STATES:
            return
        if current["state"] != "planned":
            return
        plan = current.get("plan")
        if not isinstance(plan, dict) or plan.get("effect_kind") != "worker_action":
            raise RuntimeError("planned event is missing its worker effect envelope")
        intervention_id = str(plan.get("intervention_id") or "")
        effect = await self.store.get_event_effect(str(current["event_id"]), "main")
        if effect is None:
            raise RuntimeError("planned event main effect disappeared")
        if await self._durably_reconcile_overlay_child(current, effect):
            return

        event, session, _ = await self._processing_inputs(current)
        reserved = await self.store.get_intervention_for_authority(intervention_id)
        if reserved is None:
            raise RuntimeError("planned event intervention disappeared")

        if effect["state"] in EVENT_EFFECT_TERMINAL_STATES:
            stored_result = effect.get("result")
            if not isinstance(stored_result, dict):
                raise RuntimeError("terminal main effect is missing its result")
            outcome = str(
                stored_result.get("outcome") or stored_result.get("code") or effect["state"]
            )
            await self._seal_main_event_effect(
                processing=current,
                effect=effect,
                reserved=reserved,
                session=session,
                outcome=outcome,
                effect_state=str(effect["state"]),
                code=str(stored_result.get("code") or "terminal_effect_replayed"),
                publish=True,
                effect_result=stored_result,
            )
            return
        if effect["state"] == "dispatching":
            # A dispatch marker is never a retry lease. Startup/cancellation
            # recovery turns it into a terminal uncertain effect first.
            return

        try:
            await self.store.require_session_workspace_current(session)
        except WorkspaceAuthorityError as exc:
            await self._seal_main_event_effect(
                processing=current,
                effect=effect,
                reserved=reserved,
                session=None,
                outcome=exc.code,
                effect_state="skipped",
                code=exc.code,
                publish=True,
            )
            return
        claim = await self.store.claim_main_event_effect(
            event_id=event.event_id,
            owner=owner,
            global_supervision_paused=self.supervision_paused,
        )
        if not claim["granted"]:
            reason = str(claim.get("reason") or "main_effect_dispatch_refused")
            claimed_effect = claim.get("effect")
            if (
                isinstance(claimed_effect, dict)
                and claimed_effect.get("state") in EVENT_EFFECT_TERMINAL_STATES
            ):
                stored_result = claimed_effect.get("result") or {}
                outcome = str(
                    stored_result.get("outcome")
                    or stored_result.get("code")
                    or claimed_effect["state"]
                )
                await self._seal_main_event_effect(
                    processing=current,
                    effect=claimed_effect,
                    reserved=reserved,
                    session=session,
                    outcome=outcome,
                    effect_state=str(claimed_effect["state"]),
                    code=str(stored_result.get("code") or reason),
                    publish=True,
                    effect_result=stored_result,
                )
                return
            retry_later = {
                "processing_claim_not_owned",
                "processing_lease_expired",
                "earlier_event_unfinished",
                "event_plan_not_dispatchable",
            }
            if reason in retry_later:
                return
            effect = claimed_effect if isinstance(claimed_effect, dict) else effect
            await self._seal_main_event_effect(
                processing=current,
                effect=effect,
                reserved=reserved,
                session=session,
                outcome=reason,
                effect_state="skipped",
                code=reason,
                publish=True,
            )
            return

        effect = claim["effect"]
        action = reserved.proposed_action
        verdict = reserved.policy_verdict
        worker_delivery_receipt = None
        hook_preparation_receipt = None
        try:
            if action.type in {
                InterventionType.APPLY_OVERLAY,
                InterventionType.REVERT_OVERLAY,
            }:
                outcome = await self.executor.execute(
                    action,
                    verdict,
                    operation_owner_id=reserved.id,
                    operation_parent_effect_id=effect["effect_id"],
                )
            else:
                if isinstance(effect.get("payload", {}).get("codex_correction"), dict):
                    frozen_action = action.model_copy(deep=True)
                    command = event.command or str(frozen_action.payload.get("command") or "")

                    def check_local_authority() -> None:
                        if self.supervision_paused or self.policy.decide(
                            frozen_action.model_copy(deep=True), command=command,
                        ) != PolicyVerdict.ALLOW:
                            raise ValueError("current local policy refuses shared correction")

                    execution = await self.executor.execute(
                        action, verdict,
                        main_effect_context=ClaimedMainEffect(
                            event_id=event.event_id, owner=owner,
                            effect_id=effect["effect_id"], effect_version=effect["version"],
                            check_local_authority=check_local_authority,
                        ),
                    )
                else:
                    execution = await self.executor.execute(action, verdict)
                if isinstance(execution, ActionExecutionResult):
                    outcome = execution.outcome
                    worker_delivery_receipt = execution.worker_delivery_receipt
                    hook_preparation_receipt = execution.hook_preparation_receipt
                else:
                    outcome = execution
        except asyncio.CancelledError:
            await self._durably_settle_main_result(
                processing=current, reserved=reserved, session=session,
                outcome="worker_delivery_uncertain", effect_state="delivery_uncertain",
                code="cancelled_after_dispatch_marker", publish=False,
            )
            raise
        except Exception:
            await self._durably_settle_main_result(
                processing=current, reserved=reserved, session=session,
                outcome="worker_delivery_uncertain", effect_state="delivery_uncertain",
                code="executor_failed_after_dispatch_marker", publish=False,
            )
            return
        await self._durably_settle_main_result(
            processing=current, reserved=reserved, session=session,
            outcome=outcome, effect_state=self._main_effect_state(outcome),
            code=outcome, publish=True,
            worker_delivery_receipt=worker_delivery_receipt,
            hook_preparation_receipt=hook_preparation_receipt,
        )

    async def recover_unfinished_events(self) -> list[str]:
        """Recover nonlegacy event heads after dependencies initialize."""

        await self.store.recover_dispatching_event_effects(
            release_startup_leases=True,
        )
        recovered: list[str] = []
        rows = await self.store.list_recoverable_event_processing()
        seen_sessions: set[str] = set()
        for row in rows:
            session_id = str(row["session_id"])
            if session_id in seen_sessions:
                continue
            seen_sessions.add(session_id)
            event_id = str(row["event_id"])
            try:
                await self._drain_event_processing(event_id)
            except ValueError:
                logger.exception(
                    "Skipping unfinished event %s during startup recovery", event_id
                )
                continue
            recovered.append(event_id)
        followup_rows = await self.store.list_recoverable_event_followups()
        for event_id in dict.fromkeys(str(row["event_id"]) for row in followup_rows):
            await self._drain_event_and_followups(event_id)
            if event_id not in recovered:
                recovered.append(event_id)
        return recovered

    async def close_presentations(self) -> None:
        """Cancel and join non-authoritative post-commit presentation work."""

        tasks = tuple(self._presentation_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._presentation_tasks.difference_update(tasks)
        reconciliations = tuple(
            self._overlay_reconciliation_tasks | self._main_effect_settlement_tasks
        )
        if reconciliations:
            await asyncio.gather(*reconciliations, return_exceptions=True)
        self._overlay_reconciliation_tasks.difference_update(reconciliations)
        self._main_effect_settlement_tasks.difference_update(reconciliations)

    async def _negotiate_capabilities(self, session: HarnessSession) -> bool:
        """Refresh the adapter snapshot, failing closed on an unavailable probe."""
        before = dict(session.capabilities)
        adapter = self.adapters.for_session(session.id)
        if adapter is None:
            caps = AdapterCapabilities(notes="No registered adapter; controls are unavailable.")
            source = "unregistered"
        else:
            try:
                caps = await asyncio.wait_for(adapter.probe(), timeout=2.0)
            except Exception:
                caps = AdapterCapabilities(
                    notes="Capability probe failed; controls are unavailable until a later probe."
                )
            source = adapter.name
        session.capabilities = caps.model_dump(mode="json")
        session.metadata["capabilities_adapter"] = source
        return session.capabilities != before

    async def _observe_prior_intervention(
        self,
        session: HarnessSession,
        event: HarnessEvent,
        verification: dict | None = None,
        *,
        persist: bool = True,
    ) -> list[Intervention]:
        updates: list[Intervention] = []
        if (
            event.session_id != session.id
            or event.harness_type != session.harness_type
            or (event.goal_id is not None and event.goal_id != session.goal_id)
            or (
                event.project_id is not None
                and not _same_project(event.project_id, session.project_id)
            )
        ):
            return updates
        observable = {
            EventType.AGENT_RESPONSE,
            EventType.FILE_EDIT,
            EventType.SHELL,
            EventType.TOOL_RESULT,
            EventType.STOP,
            EventType.ERROR,
        }
        if event.event_type not in observable:
            return updates
        active_actions = {
            InterventionType.SEND_NUDGE.value,
            InterventionType.CONTINUE_SESSION.value,
            InterventionType.INJECT_CONTEXT.value,
            InterventionType.FRESH_HANDOFF.value,
            InterventionType.REQUEST_VERIFICATION.value,
            InterventionType.ASK_HUMAN.value,
        }
        project_id = session.project_id or session.cwd
        if not session.goal_id or not project_id:
            return updates
        authority_interventions = await self.store.list_interventions_for_authority(
            session.id,
            goal_id=session.goal_id,
            project_id=project_id,
            harness_type=session.harness_type,
        )
        eligible = [
            item
            for item in authority_interventions
            if item.action_taken in active_actions
            # An intervention belongs to the intent envelope that created it.
            # Reattaching the same vendor session to a replacement goal must
            # never let new evidence satisfy or mutate the old intervention.
            and item.goal_id == session.goal_id
            and event.ts >= item.created_at
            and not (item.metadata or {}).get("outcome_final")
            and item.result
            in {
                "sent",
                "continued",
                "handoff_injected",
                "verification_requested",
                "verification_delivery_uncertain",
                "human_decision_delivered",
            }
        ]
        candidates: list[Intervention] = []
        for item in eligible:
            if "delivery_uncertain" in str(item.result):
                # Generic later activity cannot prove that an uncertain send
                # reached the worker. Keep the original attempt unresolved and
                # carry its durable verification receipt only to prevent retries.
                if (
                    verification is not None
                    and item.proposed_action.type
                    == InterventionType.REQUEST_VERIFICATION
                ):
                    prior_verification = (item.metadata or {}).get("verification")
                    prior_receipt = (
                        prior_verification.get("evidence_gathering")
                        if isinstance(prior_verification, dict)
                        else None
                    )
                    if isinstance(prior_receipt, dict):
                        try:
                            gathering = EvidenceGatheringReceipt.model_validate(
                                prior_receipt
                            )
                        except (TypeError, ValueError):
                            pass
                        else:
                            _merge_evidence_gathering(verification, gathering)
                continue
            if session.harness_type not in {
                HarnessType.CODEX,
                HarnessType.OPENCODE,
                HarnessType.SYNTHETIC,
            }:
                # A later event in the same session is not a descendant receipt.
                # Preserve the observation without converting unsupported
                # correlation into a claimed successful/failed intervention.
                self._record_observed_event(item, event)
                item.outcome = (
                    "worker_error_observed_after_intervention"
                    if event.event_type == EventType.ERROR
                    else "post_delivery_activity_observed_causality_unavailable"
                )
                item.helped = None
                if event.event_type != EventType.ERROR:
                    item.metadata["outcome_final"] = True
                item.metadata["causal_continuation_proven"] = False
                if persist:
                    await self.store.update_intervention(item)
                    await self.bus.publish("intervention", item.model_dump(mode="json"))
                updates.append(item)
                continue
            if (
                session.harness_type
                in {HarnessType.CODEX, HarnessType.OPENCODE, HarnessType.SYNTHETIC}
                and not isinstance(
                    (item.metadata or {}).get("worker_delivery_receipt"),
                    dict,
                )
            ):
                item.outcome = (
                    "worker_delivery_uncertain"
                    if "delivery_uncertain" in str(item.result)
                    else "worker_delivery_causality_unavailable_legacy"
                )
                item.helped = None
                item.metadata["outcome_final"] = True
                if persist:
                    await self.store.update_intervention(item)
                    await self.bus.publish(
                        "intervention", item.model_dump(mode="json")
                    )
                updates.append(item)
                continue
            try:
                matches_delivery = self._event_matches_worker_delivery(
                    item,
                    session,
                    event,
                )
            except RuntimeError:
                item.outcome = "worker_delivery_receipt_corrupt"
                item.helped = None
                item.metadata["outcome_final"] = True
                if persist:
                    await self.store.update_intervention(item)
                    await self.bus.publish(
                        "intervention", item.model_dump(mode="json")
                    )
                updates.append(item)
                continue
            if matches_delivery:
                candidates.append(item)
            elif session.harness_type == HarnessType.SYNTHETIC:
                # Synthetic attribution is causal only with the adapter-minted
                # event reference checked above. Manually shaped/generic events
                # remain observable but cannot earn helped credit.
                self._record_observed_event(item, event)
                item.outcome = "post_delivery_activity_observed_causality_unavailable"
                item.helped = None
                if event.phase == EventPhase.TERMINAL:
                    item.metadata["outcome_final"] = True
                    item.metadata["causal_continuation_proven"] = False
                if persist:
                    await self.store.update_intervention(item)
                    await self.bus.publish(
                        "intervention", item.model_dump(mode="json")
                    )
                updates.append(item)
        verification_request = next(
            (
                item
                for item in candidates
                if item.proposed_action.type == InterventionType.REQUEST_VERIFICATION
                and item.result in {"verification_requested", "verification_delivery_uncertain"}
            ),
            None,
        )
        if verification_request is not None:
            verification_update = await self._observe_verification_request(
                verification_request,
                session,
                event,
                verification,
                persist=persist,
            )
            if verification_update is not None:
                updates.append(verification_update)
        prior = next(
            (
                item
                for item in candidates
                if item.proposed_action.type != InterventionType.REQUEST_VERIFICATION
            ),
            None,
        )
        if prior is None or not self._record_observed_event(prior, event):
            return updates

        pytest_state = (event.process_state or {}).get("pytest")
        pytest_invocation = classify_pytest_invocation(event.command)
        if (
            isinstance(pytest_state, dict)
            and pytest_state.get("ok") is True
            and pytest_invocation is not None
            and pytest_invocation.scope.value == "full_suite"
        ):
            prior.outcome = "verification_passed_after_intervention"
        elif (
            isinstance(pytest_state, dict)
            and pytest_state.get("ok") is False
            and pytest_invocation is not None
        ):
            prior.outcome = "verification_failed_after_intervention"
        elif event.event_type == EventType.ERROR:
            # An intermediate worker error is an observation, not causal proof
            # that the intervention hurt and not a terminal outcome. Keep
            # watching for the next verification/STOP receipt.
            prior.outcome = "worker_error_observed_after_intervention"
            prior.helped = None
        elif event.event_type == EventType.FILE_EDIT:
            prior.outcome = "new_file_progress_observed"
        elif event.event_type == EventType.AGENT_RESPONSE:
            prior.outcome = "worker_responded"
        elif event.event_type == EventType.STOP:
            status = str((verification or {}).get("status") or "")
            acceptance_status = str((verification or {}).get("acceptance_status") or "")
            if status == "supported" or acceptance_status == "supported":
                prior.outcome = "goal_evidence_supported"
                prior.helped = True
            elif status in {"contradicted", "acceptance_gap"}:
                prior.outcome = "acceptance_still_unsatisfied"
                prior.helped = False
            else:
                prior.outcome = "worker_stopped_outcome_uncertain"
            prior.metadata["outcome_final"] = True
        else:
            prior.outcome = "worker_progress_observed"
        if persist:
            await self.store.update_intervention(prior)
            await self.bus.publish("intervention", prior.model_dump(mode="json"))
        updates.append(prior)
        return updates

    @staticmethod
    def _event_matches_worker_delivery(
        intervention: Intervention,
        session: HarnessSession,
        event: HarnessEvent,
    ) -> bool:
        """Require proven continuation identity before attributing worker outcomes."""

        if (
            intervention.session_id != session.id
            or intervention.goal_id != session.goal_id
            or event.session_id != session.id
            or event.harness_type != session.harness_type
            or (event.goal_id is not None and event.goal_id != session.goal_id)
            or (
                event.project_id is not None
                and not _same_project(event.project_id, session.project_id)
            )
        ):
            return False
        if session.harness_type.value == "cursor":
            # A queued response or even a flushed hook is not vendor acceptance.
            # The separate Cursor ledger records bounded, ordered observations;
            # it must not enter this generic causal/helpfulness path.
            return False
        if session.harness_type == HarnessType.OPENCODE:
            return event_matches_opencode_delivery(intervention, session, event)
        if session.harness_type == HarnessType.SYNTHETIC:
            receipt = (intervention.metadata or {}).get("worker_delivery_receipt")
            if not isinstance(receipt, dict) or set(receipt) != {
                "schema",
                "target_session_id",
                "vendor_session_id",
                "vendor_turn_id",
            }:
                return False
            if (
                receipt.get("schema") != "pex.worker-delivery.v1"
                or receipt.get("target_session_id") != session.id
                or receipt.get("vendor_session_id") != session.vendor_session_id
            ):
                return False
            turn_id = receipt.get("vendor_turn_id")
            if not isinstance(turn_id, str) or not turn_id:
                return False
            return (
                (event.metadata or {}).get("vendor_turn_id") == turn_id
                and Pipeline._synthetic_event_ref_is_adapter_minted(session, event)
            )
        if session.harness_type.value != "codex":
            # Each harness needs its own exact vendor continuation proof.
            # Generic acceptance is never sufficient for outcome attribution.
            return False
        receipt = (intervention.metadata or {}).get("worker_delivery_receipt")
        if not isinstance(receipt, dict):
            return False
        if (
            set(receipt)
            != {
                "schema",
                "target_session_id",
                "vendor_session_id",
                "vendor_turn_id",
            }
            or receipt.get("schema") != "pex.worker-delivery.codex-turn.v1"
            or receipt.get("target_session_id") != session.id
            or receipt.get("vendor_session_id") != session.vendor_session_id
        ):
            raise RuntimeError("Codex worker delivery receipt is corrupt")
        try:
            receipt_turn_id = bounded_adapter_id(
                receipt.get("vendor_turn_id"),
                field="Codex worker delivery turn id",
            )
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Codex worker delivery receipt is corrupt") from exc
        if (event.metadata or {}).get("vendor_turn_id") != receipt_turn_id:
            return False
        if not isinstance(event.raw_event_ref, str):
            return False
        try:
            raw_ref = json.loads(event.raw_event_ref)
        except (TypeError, ValueError):
            return False
        if not isinstance(raw_ref, dict):
            return False
        allowed_keys = {"schema", "thread_id", "turn_id", "item_id"}
        if (
            not {"schema", "thread_id", "turn_id"}.issubset(raw_ref)
            or not set(raw_ref).issubset(allowed_keys)
            or raw_ref.get("schema") != "pex.codex-event-ref.v1"
            or raw_ref.get("thread_id") != session.vendor_session_id
            or raw_ref.get("turn_id") != receipt_turn_id
            or event.raw_event_ref
            != json.dumps(raw_ref, sort_keys=True, separators=(",", ":"))
        ):
            return False
        if event.event_type == EventType.STOP:
            return (
                set(raw_ref) == {"schema", "thread_id", "turn_id"}
                and event.event_id == f"{session.id}:turn:{receipt_turn_id}"
            )
        item_id = raw_ref.get("item_id")
        return (
            isinstance(item_id, str)
            and bool(item_id)
            and event.event_id == f"{session.id}:item:{item_id}"
        )

    @staticmethod
    def _synthetic_event_ref_is_adapter_minted(
        session: HarnessSession,
        event: HarnessEvent,
    ) -> bool:
        turn_id = (event.metadata or {}).get("vendor_turn_id")
        if not isinstance(turn_id, str) or not turn_id:
            return False
        expected_ref = json.dumps(
            {
                "schema": "pex.synthetic-event-ref.v1",
                "session_id": session.id,
                "turn_id": turn_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return event.raw_event_ref == expected_ref

    @staticmethod
    def _record_observed_event(prior: Intervention, event: HarnessEvent) -> bool:
        """Attach one event to one outcome receipt exactly once."""

        observed_ids = list((prior.metadata or {}).get("outcome_event_ids") or [])
        if event.event_id in observed_ids:
            return False
        observed_ids.append(event.event_id)
        prior.metadata["outcome_event_ids"] = observed_ids[-20:]
        if event.message_delta:
            prior.worker_response = event.message_delta[:4000]
        elif event.file_paths:
            prior.worker_response = "edited " + ", ".join(event.file_paths[:8])
        elif event.command:
            prior.worker_response = f"ran {event.command[:500]}"
        return True

    async def _observe_verification_request(
        self,
        prior: Intervention,
        session: HarnessSession,
        event: HarnessEvent,
        verification: dict | None,
        *,
        persist: bool = True,
    ) -> Intervention | None:
        """Resolve a typed verification request independently of newer nudges."""

        prior_verification = (prior.metadata or {}).get("verification")
        prior_receipt = (
            prior_verification.get("evidence_gathering")
            if isinstance(prior_verification, dict)
            else None
        )
        if not isinstance(prior_receipt, dict):
            return None
        try:
            gathering = EvidenceGatheringReceipt.model_validate(prior_receipt)
        except (TypeError, ValueError):
            return None
        if not self._record_observed_event(prior, event):
            return None

        if event.event_type != EventType.STOP:
            execution = _matching_pytest_execution(
                prior, session, event, gathering
            ) or _matching_typed_execution(prior, session, event, gathering)
            if execution is not None:
                executed = EvidenceGatheringReceipt.model_validate(
                    {
                        **gathering.model_dump(mode="json"),
                        "state": EvidenceGatheringState.EXECUTED,
                        "sources": list(dict.fromkeys([*gathering.sources, "harness_execution"])),
                        "execution": execution.model_dump(mode="json"),
                        "reason": "matching_harness_result_observed",
                    }
                )
                updated_verification = dict(prior_verification)
                updated_verification["evidence_gathering"] = executed.model_dump(mode="json")
                prior.metadata["verification"] = updated_verification
                prior.outcome = (
                    "verification_passed_after_intervention"
                    if execution.result == VerificationExecutionResult.PASSED
                    else "verification_failed_after_intervention"
                )
                prior.helped = None
            elif event.event_type == EventType.ERROR:
                prior.outcome = "worker_error_observed_after_intervention"
                prior.helped = None
            elif event.event_type == EventType.FILE_EDIT:
                prior.outcome = "new_file_progress_observed"
            elif event.event_type == EventType.AGENT_RESPONSE:
                prior.outcome = "worker_responded"
            else:
                prior.outcome = "worker_progress_observed"
            if persist:
                await self.store.update_intervention(prior)
                await self.bus.publish("intervention", prior.model_dump(mode="json"))
            return prior

        merged = verification is not None and _merge_evidence_gathering(
            verification,
            gathering,
        )
        status = str((verification or {}).get("status") or "")
        acceptance_status = str((verification or {}).get("acceptance_status") or "")
        current_raw = (verification or {}).get("evidence_gathering")
        current = (
            EvidenceGatheringReceipt.model_validate(current_raw)
            if isinstance(current_raw, dict)
            else None
        )
        if gathering.state == EvidenceGatheringState.EXECUTED and not merged:
            current_event_id = str((verification or {}).get("pytest_event_id") or "")
            source_event_id = str(getattr(gathering.execution, "source_event_id", "") or "")
            if current is not None and current.probe is not None:
                verification["supersedes_probe_id"] = (
                    gathering.probe.id if gathering.probe is not None else None
                )
                prior.outcome = "verification_result_staled_by_later_progress"
            elif current_event_id and current_event_id != source_event_id:
                prior.outcome = "verification_superseded_by_newer_pytest"
            else:
                prior.outcome = "worker_stopped_outcome_uncertain"
            if prior.outcome != "worker_stopped_outcome_uncertain":
                prior.metadata["outcome_final"] = True
                prior.helped = None
        elif merged and gathering.state == EvidenceGatheringState.EXECUTED:
            if status == "supported" or acceptance_status == "supported":
                prior.outcome = "goal_evidence_supported"
                prior.helped = True
                prior.metadata["goal_satisfied"] = True
                prior.metadata["outcome_final"] = True
            elif status in {"contradicted", "acceptance_gap"}:
                prior.outcome = "verification_revealed_unsatisfied_goal"
                # The evidence request succeeded even though the task did not.
                prior.helped = True
                prior.metadata["goal_satisfied"] = False
                prior.metadata["outcome_final"] = True
            else:
                prior.outcome = "worker_stopped_outcome_uncertain"
            prior.metadata["evidence_collection_succeeded"] = True
        else:
            prior.outcome = "worker_stopped_outcome_uncertain"
        if persist:
            await self.store.update_intervention(prior)
            await self.bus.publish("intervention", prior.model_dump(mode="json"))
        return prior

    async def deliver_context_handoff(
        self,
        source: HarnessSession,
        target: HarnessSession,
        bundle: ContextBundle,
        event: HarnessEvent,
        *,
        human_requested: bool = False,
        diagnosis: str = "relevance_scored_context_handoff",
        request_identity: dict[str, object] | None = None,
    ) -> Intervention:
        """Compatibility wrapper routed through the canonical operator ledger."""

        if event.session_id != source.id or event.harness_type != source.harness_type:
            raise ValueError("handoff_event_source_mismatch")
        if not source.goal_id or target.goal_id != source.goal_id:
            raise ValueError("handoff_goal_mismatch")
        if bundle.goal_id != source.goal_id or bundle.target_session_id != target.id:
            raise ValueError("handoff_bundle_mismatch")
        if bundle.source_session_ids != [source.id]:
            raise ValueError("handoff_source_mismatch")
        if not _same_session_project(source, target):
            raise ValueError("handoff_project_mismatch")
        project_id = source.project_id or source.cwd
        for item in bundle.items:
            if item.goal_id != source.goal_id or not _same_project(
                item.project_id,
                project_id,
            ):
                raise ValueError("handoff_item_identity_mismatch")
            if item.sensitivity in {Sensitivity.SECRET, Sensitivity.LOCAL_ONLY}:
                raise ValueError("handoff_item_sensitivity_forbidden")
            if not item.source_refs:
                raise ValueError("handoff_item_provenance_missing")
            if (
                item.provenance not in {SourceKind.HUMAN, SourceKind.PEX}
                and str(item.metadata.get("source_session_id") or "") != source.id
            ):
                raise ValueError("handoff_item_source_session_mismatch")

        identity_payload = {
            "schema": "pex.internal-handoff-request.v1",
            "event_id": event.event_id,
            "source_session_id": source.id,
            "target_session_id": target.id,
            "goal_id": source.goal_id,
            "token_budget": 12_000,
            "item_ids": sorted(item.id for item in bundle.items),
            "request_identity": request_identity or {},
        }
        digest = hashlib.sha256(
            json.dumps(
                identity_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        request = ContextHandoffRequest(
            idempotency_key=f"internal-handoff-{digest}",
            target_session_id=target.id,
            token_budget=12_000,
        )
        # Compatibility callers cannot mint operator provenance with a Boolean.
        # Only the operator-only REST dependency can provide actor assurance.
        principal_id = "system_internal_handoff"
        async with self._handoff_mutation_lock:
            live_source = await self.store.get_session_for_authority(
                source.id,
                require_goal_binding=True,
            )
            live_target = await self.store.get_session_for_authority(
                target.id,
                require_goal_binding=True,
            )
            if live_source is None or live_target is None or not live_source.goal_id:
                raise ValueError("handoff requires stored source and target")
            goal = await self.store.get_goal_for_authority(live_source.goal_id)
            if goal is None:
                raise ValueError("handoff goal not found")
            if await self._negotiate_capabilities(live_target):
                await self.store.upsert_session(live_target)
            record = await self._reserve_context_handoff_locked(
                source=live_source,
                target=live_target,
                goal=goal,
                bundle=bundle,
                principal_id=principal_id,
                request=request,
                human_requested=human_requested,
                actor_assurance=None,
                diagnosis=diagnosis,
            )
        response = await self._dispatch_operator_handoff(
            record,
            replayed=not bool(record.get("created")),
        )
        return Intervention.model_validate(response["intervention"])

    async def _record_explicit_override(
        self,
        session: HarnessSession,
        goal: Goal,
        event: HarnessEvent,
    ) -> None:
        """Build-spec §14.3: persist an explicit override as a durable ledger decision."""
        projections = self._explicit_override_projections(session, goal, event)
        if projections is None:
            return
        decision, context = projections
        await self.store.add_decision_context_pair(decision, context)

    def _explicit_override_projections(
        self,
        session: HarnessSession,
        goal: Goal,
        event: HarnessEvent,
        *,
        stable: bool = False,
    ) -> tuple[Decision, ContextItem] | None:
        """Build the override ledger pair without performing Store writes."""

        if (
            event.harness_type == HarnessType.CODEX
            and event.metadata.get("raw_type") == "userMessage"
        ):
            content_status = event.metadata.get("content_status")
            if (
                not isinstance(content_status, str)
                or content_status not in {"complete", "legacy_top_level"}
                or event.metadata.get("content_truncated") is not False
                or event.metadata.get("content_redacted") is not False
            ):
                return None
        prompt, _ = redact_text(event.message_delta or "")
        statement = (prompt or "").strip()[:500]
        if not statement:
            return None
        now = event.ts if stable else utcnow()
        decision = Decision(
            id=(
                stable_event_artifact_id(event.event_id, "override_decision")
                if stable
                else new_id("dec_")
            ),
            goal_id=goal.id,
            statement=statement,
            rationale="Explicit user override of the persistent intent ledger.",
            source=DecisionSource.HUMAN,
            status=DecisionStatus.ACTIVE,
            created_at=now,
            metadata={
                "session_id": session.id,
                "trigger_event_id": event.event_id,
                "prompt_class": PromptClass.OVERRIDE.value,
            },
        )
        project_id = session.project_id or session.cwd or goal.project_id
        context = ContextItem(
            id=(
                stable_event_artifact_id(event.event_id, "override_context")
                if stable
                else new_id("ctx_")
            ),
            project_id=project_id,
            goal_id=goal.id,
            kind=ContextKind.DECISION,
            content=statement,
            source_refs=[event.event_id],
            provenance=SourceKind.HUMAN,
            confidence=0.9,
            relevance_tags=["override", "decision"],
            valid_from=event.ts or now,
            sensitivity=Sensitivity.INTERNAL,
            metadata={
                "decision_id": decision.id,
                "source_session_id": session.id,
                "status": DecisionStatus.ACTIVE.value,
            },
        )
        return decision, context

    def _mcp_trigger(
        self,
        session: HarnessSession,
        message: str,
        *,
        event_type: EventType = EventType.AGENT_RESPONSE,
    ) -> HarnessEvent:
        cleaned, _ = redact_text(message)
        return HarnessEvent(
            event_id=new_id("mcp_"),
            ts=utcnow(),
            harness_type=session.harness_type,
            session_id=session.id,
            project_id=session.project_id,
            event_type=event_type,
            phase=EventPhase.AFTER,
            message_delta=(cleaned or "")[:4_000],
        )

    async def record_reported_progress(
        self,
        session: HarnessSession,
        *,
        principal: MCPPrincipal,
        report: ProgressReport,
    ) -> dict:
        """Atomically persist one principal-bound, evidence-linked self-report."""

        if principal.kind != "session" or not principal.has_scope(MCP_REPORT_PROGRESS_SCOPE):
            raise PermissionError("a session-scoped MCP principal is required")
        live = await self.store.get_session_for_authority(
            session.id,
            require_goal_binding=True,
        )
        if live is None:
            raise ValueError("session not found")
        session = live
        if not session.goal_id:
            raise ValueError("session has no attached persistent goal")
        goal = await self.store.get_goal_for_authority(session.goal_id)
        if goal is None:
            raise ValueError("session goal not found")
        project_id = session.project_id or session.cwd
        if not project_id:
            raise ValueError("session has no project")
        if (
            principal.session_id != session.id
            or principal.goal_id != goal.id
            or principal.vendor_session_id != session.vendor_session_id
            or principal.harness_type != session.harness_type
            or not principal.project_id
        ):
            raise PermissionError("MCP principal does not match the live worker binding")
        live_project_binding = await self.store.project_binding_for_authority(principal.project_id)
        if live_project_binding != principal.project_binding:
            raise PermissionError("MCP principal project binding changed")
        if await self.store.has_goal_successor_for_authority(goal.id):
            raise PermissionError("MCP principal goal has been superseded")

        cleaned, _ = redact_text(report.summary)
        text = (cleaned or "").strip()
        if not text:
            raise ValueError("progress summary must not be empty")
        if len(text) > 4_000:
            raise ValueError("redacted progress summary exceeds its safety bound")
        refs = tuple(sorted(report.evidence_refs, key=lambda item: (item.type, item.id)))
        ref_labels = [f"{item.type}:{item.id}" for item in refs]
        request_fingerprint = reported_progress_request_fingerprint(
            principal_id=principal.principal_id,
            tool=MCP_REPORT_PROGRESS_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=project_id,
            summary=text,
            evidence_refs=refs,
        )
        artifact_key = hashlib.sha256(
            (
                f"pex.mcp.report_progress.v1\0{principal.principal_id}\0{report.idempotency_key}"
            ).encode()
        ).hexdigest()[:40]
        observed_at = utcnow()
        trigger = HarnessEvent(
            event_id=f"mcp_progress_event_{artifact_key}",
            ts=observed_at,
            harness_type=session.harness_type,
            session_id=session.id,
            project_id=project_id,
            goal_id=goal.id,
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.AFTER,
            message_delta=text,
            metadata={
                "source": "mcp_report_progress",
                "source_session_id": session.id,
                "mcp_principal_id": principal.principal_id,
                "verified": False,
            },
        )
        item = ContextItem(
            id=f"progress_{artifact_key}",
            project_id=project_id,
            goal_id=goal.id,
            kind=ContextKind.RESULT,
            content=text,
            source_refs=ref_labels,
            provenance=SourceKind.HARNESS,
            confidence=0.4,
            relevance_tags=["progress", "unverified"],
            valid_from=observed_at,
            sensitivity=Sensitivity.INTERNAL,
            metadata={
                "source_session_id": session.id,
                "mcp_principal_id": principal.principal_id,
                "status": "reported",
                "verified": False,
            },
        )
        action = ProposedAction(
            type=InterventionType.ANNOTATE,
            session_id=session.id,
            goal_id=goal.id,
            payload={"context_id": item.id, "channel": "mcp"},
            rationale="Bound worker reported progress with resolved provenance references.",
            evidence=ref_labels[:12],
            confidence=0.4,
            risk=RiskLevel.LOW,
            reversible=True,
        )
        result = SupervisorResult(
            action=action,
            used_llm=False,
            diagnosis="mcp_reported_progress",
        )
        verdict = self.policy.decide(action)
        if verdict != PolicyVerdict.ALLOW:
            raise PermissionError("local policy does not allow MCP progress annotation")
        outcome = "annotated"
        intervention = self._intervention(
            event=trigger,
            session=session,
            result=result,
            verdict=verdict,
            outcome=outcome,
            action_taken=action.type.value,
        )
        intervention.id = f"int_progress_{artifact_key}"
        intervention.created_at = observed_at
        intervention.metadata["mcp_principal_id"] = principal.principal_id
        response = {
            "ok": True,
            "verified": False,
            "item": item.model_dump(mode="json"),
            "intervention": intervention.model_dump(mode="json"),
        }
        committed = await self.store.commit_reported_progress(
            principal_id=principal.principal_id,
            tool=MCP_REPORT_PROGRESS_TOOL,
            request_id=report.idempotency_key,
            request_fingerprint=request_fingerprint,
            evidence_refs=refs,
            event=trigger,
            context_item=item,
            intervention=intervention,
            response=response,
        )
        stored_response = dict(committed["response"])
        stored_response["mutation_id"] = committed["mutation_id"]
        stored_response["replayed"] = not committed["created"]
        if committed["created"]:
            await self.bus.publish("intervention", stored_response["intervention"])
        return stored_response

    async def request_human_decision(
        self,
        session: HarnessSession,
        *,
        principal: MCPPrincipal,
        request: HumanDecisionRequest,
    ) -> dict:
        """Atomically open one principal-bound human decision. Never auto-resolve it."""

        if principal.kind != "session" or not principal.has_scope(MCP_REQUEST_DECISION_SCOPE):
            raise PermissionError("a session-scoped MCP principal is required")
        live = await self.store.get_session_for_authority(
            session.id,
            require_goal_binding=True,
        )
        if live is None:
            raise ValueError("session not found")
        session = live
        if session.status in {
            SessionStatus.STOPPED,
            SessionStatus.ERROR,
            SessionStatus.DETACHED,
        }:
            raise PermissionError("terminal sessions cannot request human decisions")
        if not session.goal_id:
            raise ValueError("session has no attached persistent goal")
        goal = await self.store.get_goal_for_authority(session.goal_id)
        if goal is None:
            raise ValueError("session goal not found")
        project_id = session.project_id or session.cwd
        if not project_id:
            raise ValueError("session has no project")
        if (
            principal.session_id != session.id
            or principal.goal_id != goal.id
            or principal.vendor_session_id != session.vendor_session_id
            or principal.harness_type != session.harness_type
            or not principal.project_id
        ):
            raise PermissionError("MCP principal does not match the live worker binding")
        live_project_binding = await self.store.project_binding_for_authority(principal.project_id)
        if live_project_binding != principal.project_binding:
            raise PermissionError("MCP principal project binding changed")
        if await self.store.has_goal_successor_for_authority(goal.id):
            raise PermissionError("MCP principal goal has been superseded")

        cleaned_question, _ = redact_text(request.question)
        cleaned_context, _ = redact_text(request.context)
        cleaned_options = tuple((redact_text(value)[0] or "").strip() for value in request.options)
        stored_request = HumanDecisionRequest(
            idempotency_key=request.idempotency_key,
            question=(cleaned_question or "").strip(),
            options=cleaned_options,
            urgency=request.urgency,
            context=(cleaned_context or "").strip(),
        )
        request_fingerprint = human_decision_request_fingerprint(
            tool=MCP_REQUEST_DECISION_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=project_id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
            question=stored_request.question,
            options=stored_request.options,
            urgency=stored_request.urgency,
            context=stored_request.context,
        )
        artifact_key = human_decision_logical_key(
            tool=MCP_REQUEST_DECISION_TOOL,
            request_id=stored_request.idempotency_key,
            session_id=session.id,
            goal_id=goal.id,
            project_id=project_id,
            vendor_session_id=session.vendor_session_id,
            harness_type=session.harness_type.value,
        )
        observed_at = utcnow()
        trigger = HarnessEvent(
            event_id=f"mcp_decision_event_{artifact_key}",
            ts=observed_at,
            harness_type=session.harness_type,
            session_id=session.id,
            project_id=project_id,
            goal_id=goal.id,
            event_type=EventType.USER_PROMPT,
            phase=EventPhase.AFTER,
            message_delta=stored_request.question,
            metadata={
                "source": "mcp_request_decision",
                "source_session_id": session.id,
                "mcp_principal_id": principal.principal_id,
            },
        )
        pending_context = ContextItem(
            id=f"decision_pending_{artifact_key}",
            project_id=project_id,
            goal_id=goal.id,
            kind=ContextKind.WARNING,
            content=stored_request.question,
            source_refs=[trigger.event_id],
            provenance=SourceKind.HARNESS,
            confidence=0.7,
            relevance_tags=["decision", "unresolved_question"],
            valid_from=observed_at,
            sensitivity=Sensitivity.INTERNAL,
            metadata={
                "source_session_id": session.id,
                "mcp_principal_id": principal.principal_id,
                "status": "pending",
                "options": list(stored_request.options),
                "urgency": stored_request.urgency,
            },
        )
        action = ProposedAction(
            type=InterventionType.ASK_HUMAN,
            session_id=session.id,
            goal_id=goal.id,
            payload={
                "question": stored_request.question,
                "options": list(stored_request.options),
                "urgency": stored_request.urgency,
                "context": stored_request.context,
                "channel": "mcp",
                "pending_context_id": pending_context.id,
                "source_project_id": project_id,
                "source_vendor_session_id": session.vendor_session_id,
                "source_harness_type": session.harness_type.value,
            },
            rationale="A worker asked PEX to route a human-only decision.",
            evidence=[trigger.event_id],
            confidence=0.7,
            risk=RiskLevel.MEDIUM,
            reversible=False,
            authority_required=Authority.HUMAN,
        )
        result = SupervisorResult(
            action=action,
            used_llm=False,
            diagnosis="mcp_request_decision",
        )
        verdict = self.policy.decide(action)
        if verdict != PolicyVerdict.ASK_HUMAN:
            raise ValueError("human-only decisions cannot be auto-resolved")
        outcome = "awaiting_human"
        intervention = self._intervention(
            event=trigger,
            session=session,
            result=result,
            verdict=verdict,
            outcome=outcome,
            action_taken=action.type.value,
        )
        intervention.id = f"int_decision_{artifact_key}"
        intervention.created_at = observed_at
        intervention.metadata.update(
            {
                "mcp_principal_id": principal.principal_id,
                "pending_context_id": pending_context.id,
                "trigger_event_id": trigger.event_id,
                "decision_kind": "mcp_human_request",
            }
        )
        committed = await self.store.commit_human_decision_request(
            principal_id=principal.principal_id,
            tool=MCP_REQUEST_DECISION_TOOL,
            request=stored_request,
            request_fingerprint=request_fingerprint,
            event=trigger,
            pending_context=pending_context,
            intervention=intervention,
        )
        stored_response = dict(committed["response"])
        stored_response["mutation_id"] = committed["mutation_id"]
        stored_response["replayed"] = not committed["created"]
        if committed["created"]:
            await self.bus.publish_committed("intervention", stored_response["intervention"])
            try:
                pet = await self.pet_snapshot()
            except Exception as exc:
                logger.warning(
                    "committed decision pet snapshot failed error=%s",
                    type(exc).__name__,
                )
            else:
                await self.bus.publish_committed("pet", pet)
        return stored_response

    async def _annotate_speculative_stop(
        self,
        session: HarnessSession,
        goal: Goal | None,
        decisions: list,
        scores,
        verification: dict,
        recent: list,
        context_items: list[ContextItem],
        *,
        persist_session: bool = True,
    ) -> None:
        """Attach §23 probe/compare facts. Never forks a worker from ingest."""

        pair = speculative_pair(session)
        if pair is not None:
            scores.features["in_speculative_pair"] = True
            result = probe_result_from_stop(session, verification, recent)
            metadata = dict(session.metadata or {})
            metadata["speculative_result"] = result
            session.metadata = metadata
            if persist_session:
                await self.store.upsert_session(session)
            sibling = await self.store.get_session_for_authority(
                str(pair.get("sibling_session_id") or ""),
                require_goal_binding=True,
            )
            sibling_result = (
                (sibling.metadata or {}).get("speculative_result") if sibling is not None else None
            )
            if isinstance(sibling_result, dict) and sibling is not None:
                parent_result, child_result = (
                    (result, sibling_result)
                    if str(pair.get("role") or "") != "b"
                    else (sibling_result, result)
                )
                scores.features["speculative_compare"] = compare_probe_results(
                    parent=parent_result,
                    child=child_result,
                )
            return
        if goal is None or (session.capabilities or {}).get("fork") is not True:
            return
        approaches = cheap_competing_approaches(decisions)
        if not approaches:
            return
        project_id = session.project_id or session.cwd or goal.project_id
        siblings = await self.store.list_sessions_for_goal_for_authority(
            goal.id,
            project_id=project_id,
        )
        if probe_already_running(siblings, goal_id=goal.id, current_session_id=session.id):
            scores.features["probe_already_running"] = True
            return
        try:
            bundle = build_bundle(
                goal,
                session,
                context_items,
                recent,
                [session.id],
            )
        except ValueError:
            return
        parent_objective = probe_instructions(approaches[0])
        child_objective = probe_instructions(approaches[1])
        bundle = bundle.model_copy(update={"next_objective": child_objective})
        scores.features["competing_approaches"] = approaches
        scores.features["parent_objective"] = parent_objective
        scores.features["probe_bundle"] = bundle.model_dump(mode="json")

    async def request_context_handoff(
        self,
        source: HarnessSession,
        *,
        principal_id: str,
        request: ContextHandoffRequest,
        human_requested: bool = False,
        actor_assurance: str | None = None,
    ) -> dict:
        """Route a minimum provenance-bound bundle from source to target."""

        if actor_assurance is not None and actor_assurance != "bridge_bearer":
            raise ValueError("operator actor assurance is invalid")
        actor_requested = actor_assurance == "bridge_bearer"
        async with self._handoff_mutation_lock:
            record = await self._request_context_handoff_locked(
                source,
                principal_id=principal_id,
                request=request,
                human_requested=actor_requested,
                actor_assurance=actor_assurance,
            )
        return await self._dispatch_operator_handoff(
            record,
            replayed=not bool(record.get("created")),
        )

    async def _request_context_handoff_locked(
        self,
        source: HarnessSession,
        *,
        principal_id: str,
        request: ContextHandoffRequest,
        human_requested: bool,
        actor_assurance: str | None,
    ) -> dict:
        """Reserve one caller-idempotent handoff without holding lock over I/O."""

        prior = await self.store.find_operator_handoff(
            principal_id=principal_id,
            idempotency_key=request.idempotency_key,
            source_session_id=source.id,
            target_session_id=request.target_session_id,
            token_budget=request.token_budget,
        )
        if prior is not None:
            return prior

        stored_source = await self.store.get_session_for_authority(
            source.id,
            require_goal_binding=True,
        )
        stored_target = await self.store.get_session_for_authority(
            request.target_session_id,
            require_goal_binding=True,
        )
        if stored_source is None or stored_target is None:
            raise ValueError("handoff requires stored source and target")
        source = stored_source
        target = stored_target
        if source.id == target.id:
            raise ValueError("handoff source and target must differ")
        if not source.goal_id or not target.goal_id:
            raise ValueError("handoff requires attached source and target")
        if target.goal_id != source.goal_id:
            raise ValueError("target is attached to a different goal")
        goal = await self.store.get_goal_for_authority(source.goal_id)
        if goal is None:
            raise ValueError("goal not found")
        if self.supervision_paused:
            raise ValueError("handoff_global_supervision_paused")
        if source.supervision_paused:
            raise ValueError("handoff_source_supervision_paused")
        if target.supervision_paused:
            raise ValueError("handoff_target_supervision_paused")
        if goal.paused:
            raise ValueError("handoff_goal_paused")
        if is_desktop_observe_session(source) or is_desktop_observe_session(target):
            raise ValueError("handoff_observe_desktop")
        if await self._negotiate_capabilities(target):
            await self.store.upsert_session(target)
        delivered = await self._delivered_context_item_ids(target, goal)
        source_project_id = source.project_id or source.cwd or goal.project_id
        items = await self.store.list_context_for_authority(
            source_project_id,
            goal_id=goal.id,
        )
        recent = await self.store.recent_events_for_authority(
            session_id=source.id,
            goal_id=goal.id,
            project_id=source_project_id,
            harness_type=source.harness_type.value,
        )
        bundle = build_bundle(
            goal,
            target,
            items,
            recent,
            [source.id],
            token_budget=request.token_budget,
            exclude_item_ids=delivered,
        )
        if not bundle.items:
            raise ValueError("no relevant provenance-backed context to hand off")
        return await self._reserve_context_handoff_locked(
            source=source,
            target=target,
            goal=goal,
            bundle=bundle,
            principal_id=principal_id,
            request=request,
            human_requested=human_requested,
            actor_assurance=actor_assurance,
            diagnosis=(
                "human_requested_context_handoff"
                if human_requested
                else "mcp_requested_context_handoff"
            ),
        )

    async def _reserve_context_handoff_locked(
        self,
        *,
        source: HarnessSession,
        target: HarnessSession,
        goal: Goal,
        bundle: ContextBundle,
        principal_id: str,
        request: ContextHandoffRequest,
        human_requested: bool,
        actor_assurance: str | None,
        diagnosis: str,
        origin_event: HarnessEvent | None = None,
    ) -> dict:
        """Mint the canonical reservation while the route lock is held."""

        if actor_assurance is not None and actor_assurance != "bridge_bearer":
            raise ValueError("operator actor assurance is invalid")
        human_requested = actor_assurance == "bridge_bearer"
        effect_id = stable_operator_effect_id(
            principal_id,
            "context_handoff",
            request.idempotency_key,
        )
        trigger = origin_event or HarnessEvent(
            event_id=stable_operator_artifact_id(effect_id, "event"),
            ts=utcnow(),
            harness_type=source.harness_type,
            session_id=source.id,
            project_id=source.project_id or source.cwd,
            goal_id=goal.id,
            event_type=EventType.USER_PROMPT,
            phase=EventPhase.AFTER,
            message_delta=(
                "User requested a context handoff to an attached session."
                if human_requested
                else "Worker requested a context handoff to an attached session."
            ),
        )
        evidence = list(dict.fromkeys(ref for item in bundle.items for ref in item.source_refs))[
            :12
        ]
        action = ProposedAction(
            type=InterventionType.FRESH_HANDOFF,
            session_id=target.id,
            goal_id=goal.id,
            payload={"bundle": bundle.model_dump(mode="json")},
            rationale="Share the minimum relevant provenance-backed context.",
            evidence=evidence,
            confidence=0.75,
            risk=RiskLevel.LOW,
            reversible=False,
            expected_benefit="Avoid duplicate investigation across sibling workers.",
            cooldown_seconds=_HANDOFF_COOLDOWN_SECONDS,
            requires_capability="inject_context",
        )
        can_inject = target.capabilities.get("inject_context", False)
        verdict = (
            (PolicyVerdict.ALLOW if human_requested else self.policy.decide(action))
            if can_inject
            else PolicyVerdict.DENY
        )
        if verdict != PolicyVerdict.ALLOW:
            raise PermissionError("handoff policy or capability denied delivery")
        intervention = self._intervention(
            event=trigger,
            session=target,
            result=SupervisorResult(
                action=action,
                used_llm=False,
                diagnosis=diagnosis,
            ),
            verdict=verdict,
            outcome="handoff_delivery_reserved",
            action_taken=InterventionType.NOOP.value,
            intervention_id=stable_operator_artifact_id(effect_id, "intervention"),
        )
        intervention.result = "handoff_delivery_reserved"
        intervention.outcome = "handoff_delivery_reserved"
        intervention.metadata["handoff_request"] = {
            "schema": "pex.operator-request.context-handoff.v1",
            "principal_id": principal_id,
            "idempotency_key": request.idempotency_key,
            "source_session_id": source.id,
            "target_session_id": target.id,
            "token_budget": request.token_budget,
        }
        intervention.metadata["human_requested"] = human_requested
        if origin_event is not None:
            intervention.metadata["origin_event_id"] = origin_event.event_id
        reserved = await self.store.reserve_operator_handoff(
            principal_id=principal_id,
            idempotency_key=request.idempotency_key,
            source_session_id=source.id,
            target_session_id=target.id,
            token_budget=request.token_budget,
            bundle=bundle,
            event=trigger,
            intervention=intervention,
            trigger_event_is_existing=origin_event is not None,
            actor_assurance=actor_assurance,
        )
        return reserved

    async def _operator_handoff_response(self, record: dict, *, replayed: bool) -> dict:
        effect = record["effect"]
        intervention = record["intervention"]
        bundle = record["bundle"]
        assimilation = await self.store.handoff_assimilation_status(str(effect["effect_id"]))
        bundle_receipt = handoff_bundle_receipt(intervention)
        if bundle_receipt is None:  # pragma: no cover - canonical Store invariant
            raise RuntimeError("operator handoff intervention lacks a typed bundle")
        return {
            "ok": effect["state"] == "delivered",
            "status": effect["state"],
            "effect": {
                key: effect.get(key)
                for key in (
                    "effect_id",
                    "action_kind",
                    "idempotency_key",
                    "request_hash",
                    "source_session_id",
                    "target_session_id",
                    "project_id",
                    "goal_id",
                    "state",
                    "reserved_at",
                    "dispatch_started_at",
                    "finished_at",
                    "result",
                )
            },
            "bundle": bundle.model_dump(mode="json"),
            "bundle_receipt": bundle_receipt,
            "intervention": public_intervention(intervention),
            "assimilation": assimilation,
            "replayed": replayed,
            "cooldown_seconds": _HANDOFF_COOLDOWN_SECONDS,
        }

    async def _dispatch_operator_handoff(self, record: dict, *, replayed: bool) -> dict:
        effect = record["effect"]
        if effect["state"] != "reserved":
            return await self._operator_handoff_response(record, replayed=replayed)
        adapter = self.adapters.for_session(str(effect["target_session_id"]))
        if adapter is None:
            final = await self.store.finalize_operator_handoff(
                effect_id=effect["effect_id"],
                state="skipped",
                result={"status": "skipped", "reason": "handoff_adapter_unavailable"},
            )
            return await self._operator_handoff_response(final, replayed=replayed)
        try:
            dispatch = await self.store.start_operator_handoff_dispatch(
                effect["effect_id"],
                global_supervision_paused=self.supervision_paused,
            )
        except (ProjectIdentityBlockedError, PermissionError, ValueError) as exc:
            reason = str(getattr(exc, "code", None) or str(exc))
            final = await self.store.finalize_operator_handoff(
                effect_id=effect["effect_id"],
                state="skipped",
                result={"status": "skipped", "reason": reason},
            )
            return await self._operator_handoff_response(final, replayed=replayed)
        if not dispatch["granted"]:
            return await self._operator_handoff_response(dispatch, replayed=replayed)

        async def durable_finalize(state_name: str, result: dict) -> dict:
            completion = asyncio.create_task(
                self.store.finalize_operator_handoff(
                    effect_id=effect["effect_id"],
                    state=state_name,
                    result=result,
                )
            )
            try:
                return await asyncio.shield(completion)
            except asyncio.CancelledError:
                await asyncio.gather(completion)
                raise

        try:
            ok = await asyncio.wait_for(
                self.executor._workspace_dispatch(
                    dispatch["target"],
                    lambda: adapter.inject_context(dispatch["target"], dispatch["bundle"]),
                    sources=(dispatch["source"],),
                ),
                timeout=HANDOFF_ADAPTER_TIMEOUT_SECONDS,
            )
        except _WorkspaceDispatchRefused:
            final = await durable_finalize(
                "failed",
                {
                    "status": "failed", "reason": WorkspaceAuthorityError.code,
                    "adapter_started": False,
                },
            )
        except asyncio.CancelledError:
            try:
                await durable_finalize(
                    "delivery_uncertain",
                    {
                        "status": "delivery_uncertain",
                        "reason": "handoff_request_cancelled_after_dispatch_started",
                    },
                )
            except Exception as exc:
                logger.error(
                    "Handoff cancellation receipt failed (%s)",
                    type(exc).__name__,
                )
            raise
        except TimeoutError:
            final = await durable_finalize(
                "delivery_uncertain",
                {
                    "status": "delivery_uncertain",
                    "reason": "handoff_adapter_timeout_after_dispatch_started",
                },
            )
        except Exception as exc:
            final = await durable_finalize(
                "delivery_uncertain",
                {
                    "status": "delivery_uncertain",
                    "reason": (
                        f"handoff_adapter_exception_after_dispatch_started:{type(exc).__name__}"
                    ),
                },
            )
        else:
            message_resolution = resolve_adapter_message_result(
                ok,
                session=dispatch["target"],
            )
            if message_resolution.status in {"delivery_uncertain", "hook_prepared"}:
                final = await durable_finalize(
                    "delivery_uncertain",
                    {
                        "status": "delivery_uncertain",
                        "reason": "handoff_invalid_adapter_receipt",
                    },
                )
            elif message_resolution.status == "rejected":
                final = await durable_finalize(
                    "failed",
                    {"status": "failed", "reason": "handoff_adapter_rejected"},
                )
            else:
                result = {"status": "delivered"}
                if message_resolution.worker_delivery_receipt is not None:
                    result["worker_delivery_receipt"] = (
                        message_resolution.worker_delivery_receipt
                    )
                final = await durable_finalize("delivered", result)
        response = await self._operator_handoff_response(final, replayed=replayed)
        await self.bus.publish("intervention", response["intervention"])
        await self.bus.publish("pet", await self.pet_snapshot())
        return response

    async def verify_reported_claim(
        self,
        session: HarnessSession,
        *,
        principal: MCPPrincipal,
        request: ClaimVerificationRequest,
    ) -> dict:
        """Atomically verify one principal-bound claim against scoped evidence."""

        if principal.kind != "session" or not principal.has_scope(MCP_VERIFY_CLAIM_SCOPE):
            raise PermissionError("a session-scoped MCP principal is required")
        live = await self.store.get_session_for_authority(
            session.id,
            require_goal_binding=True,
        )
        if live is None:
            raise ValueError("session not found")
        session = live
        if not session.goal_id:
            raise ValueError("session has no attached persistent goal")
        goal = await self.store.get_goal_for_authority(session.goal_id)
        if goal is None:
            raise ValueError("session goal not found")
        project_id = session.project_id or session.cwd
        if not project_id:
            raise ValueError("session has no project")
        if (
            principal.session_id != session.id
            or principal.goal_id != goal.id
            or principal.vendor_session_id != session.vendor_session_id
            or principal.harness_type != session.harness_type
            or not principal.project_id
        ):
            raise PermissionError("MCP principal does not match the live worker binding")
        live_project_binding = await self.store.project_binding_for_authority(principal.project_id)
        if live_project_binding != principal.project_binding:
            raise PermissionError("MCP principal project binding changed")
        if await self.store.has_goal_successor_for_authority(goal.id):
            raise PermissionError("MCP principal goal has been superseded")

        cleaned, _ = redact_text(request.claim)
        statement = (cleaned or "").strip()
        if not statement:
            raise ValueError("claim must not be empty")
        if len(statement) > 4_000:
            raise ValueError("redacted claim exceeds its safety bound")
        request_fingerprint = claim_verification_request_fingerprint(
            principal_id=principal.principal_id,
            tool=MCP_VERIFY_CLAIM_TOOL,
            session_id=session.id,
            goal_id=goal.id,
            project_id=project_id,
            claim=statement,
        )
        artifact_key = hashlib.sha256(
            (
                f"pex.mcp.verify_claim.v1\0{principal.principal_id}\0{request.idempotency_key}"
            ).encode()
        ).hexdigest()[:40]
        trigger_event_id = f"mcp_verify_event_{artifact_key}"
        recent = await self.store.recent_events_for_authority(
            session_id=session.id,
            goal_id=goal.id,
            project_id=project_id,
            harness_type=session.harness_type.value,
            limit=self.settings.max_recent_events,
        )
        recent = [event for event in recent if event.event_id != trigger_event_id]
        observed_at = utcnow()
        trigger = HarnessEvent(
            event_id=trigger_event_id,
            ts=observed_at,
            harness_type=session.harness_type,
            session_id=session.id,
            project_id=project_id,
            goal_id=goal.id,
            event_type=EventType.AGENT_RESPONSE,
            phase=EventPhase.AFTER,
            message_delta=statement,
            metadata={
                "source": "mcp_verify_claim",
                "source_session_id": session.id,
                "mcp_principal_id": principal.principal_id,
            },
        )
        extracted_claims = extract_claims([trigger])[:32]
        workspace: dict = {}
        if session.cwd:
            try:
                workspace = await self._snapshot_for_session(session)
            except WorkspaceAuthorityError:
                raise
            except Exception:
                workspace = {"error": "workspace_snapshot_failed"}
        verification = verify_claims(extracted_claims, recent, goal, workspace)
        raw_status = str(verification.get("status") or "uncertain")[:64]
        outcome = raw_status if raw_status in {"supported", "contradicted"} else "uncertain"
        evidence = [
            (redact_text(str(value))[0] or "")[:1_000]
            for value in list(verification.get("evidence") or [])[:24]
        ]
        evidence = [value for value in evidence if value]
        raw_correction = verification.get("correction")
        correction = None
        if raw_correction is not None:
            correction = (redact_text(str(raw_correction))[0] or "")[:4_000] or None
        evidence_event_ids = [event.event_id for event in recent]

        storage_claims = extracted_claims or [
            {
                "statement": statement,
                "kind": "unclassified",
                "polarity": "asserted",
                "confidence": 0.5,
                "source_event_id": trigger.event_id,
                "source_event_type": trigger.event_type.value,
            }
        ]
        claim_items = [
            ContextItem(
                id=f"claim_verify_{artifact_key}_{index:02d}",
                project_id=project_id,
                goal_id=goal.id,
                kind=ContextKind.CLAIM,
                content=str(extracted.get("statement") or statement)[:4_000],
                source_refs=[trigger.event_id],
                provenance=SourceKind.HARNESS,
                confidence=max(
                    0.0,
                    min(1.0, float(extracted.get("confidence") or 0.5)),
                ),
                relevance_tags=[
                    str(extracted.get("kind") or "claim")[:256],
                    str(extracted.get("polarity") or "")[:256],
                ],
                valid_from=observed_at,
                sensitivity=Sensitivity.INTERNAL,
                metadata={
                    **extracted,
                    "source_session_id": session.id,
                    "status": "reported",
                    "verified": False,
                },
            )
            for index, extracted in enumerate(storage_claims[:32])
        ]

        verified_items: list[ContextItem] = []
        if outcome == "supported":
            generated = items_from_verification(
                project_id,
                goal.id,
                trigger,
                verification,
                recent,
            )
            for index, item in enumerate(generated[:8]):
                item_evidence = [
                    (redact_text(str(value))[0] or "")[:1_000]
                    for value in list(item.metadata.get("evidence") or [])[:24]
                ]
                raw_claim = item.metadata.get("claim")
                bounded_claim = raw_claim if isinstance(raw_claim, dict) else {}
                verified_items.append(
                    item.model_copy(
                        update={
                            "id": f"result_verify_{artifact_key}_{index:02d}",
                            "content": item.content[:4_000],
                            "source_refs": [ref[:512] for ref in item.source_refs[:24] if ref],
                            "relevance_tags": [str(tag)[:256] for tag in item.relevance_tags[:24]],
                            "valid_from": observed_at,
                            "metadata": {
                                "verified": True,
                                "status": "supported",
                                "evidence": [value for value in item_evidence if value],
                                "claim": bounded_claim,
                                "source_session_id": session.id,
                            },
                        }
                    )
                )

        workspace_results = [
            item for item in verified_items if item.provenance == SourceKind.WORKSPACE
        ]
        if workspace_results:
            workspace_evidence = list(
                dict.fromkeys(
                    evidence_item
                    for item in workspace_results
                    for evidence_item in item.metadata.get("evidence", [])
                    if isinstance(evidence_item, str) and evidence_item
                )
            )
            if not workspace_evidence:
                raise ValueError("supported workspace verification lacks durable evidence")
            cleaned_workspace, _ = redact_mapping(workspace)
            snapshot_json = json.dumps(
                cleaned_workspace or {},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            trigger.metadata["workspace_snapshot"] = {
                "source": "pex_workspace_snapshot",
                "captured_at": observed_at.isoformat(),
                "sha256": hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest(),
                "evidence": workspace_evidence,
            }

        result_source_refs = [trigger.event_id]
        for item in verified_items:
            for source_ref in item.source_refs:
                if source_ref not in result_source_refs:
                    result_source_refs.append(source_ref)
        pytest_event_id = str(verification.get("pytest_event_id") or "")
        if pytest_event_id in evidence_event_ids and pytest_event_id not in result_source_refs:
            result_source_refs.append(pytest_event_id)
        summary_parts = [f"Claim verification outcome: {outcome}."]
        if evidence:
            summary_parts.append(f"Evidence: {', '.join(evidence)}.")
        if correction:
            summary_parts.append(f"Correction: {correction}")
        receipt_item = ContextItem(
            id=f"verification_{artifact_key}",
            project_id=project_id,
            goal_id=goal.id,
            kind=ContextKind.RESULT,
            content=" ".join(summary_parts)[:4_000],
            source_refs=result_source_refs[:24],
            provenance=SourceKind.PEX,
            confidence=0.95 if outcome != "uncertain" else 0.5,
            relevance_tags=["claim_verification", outcome],
            valid_from=observed_at,
            sensitivity=Sensitivity.INTERNAL,
            metadata={
                "receipt_type": "mcp_claim_verification",
                "source_session_id": session.id,
                "status": outcome,
                "raw_status": raw_status,
                # This PEX-authored object is an audit receipt, not independent
                # evidence. Only TEST/WORKSPACE results may be reusable proof.
                "verified": False,
                "evidence": evidence,
                "correction": correction,
            },
        )
        result_items = [receipt_item, *verified_items]
        verification_receipt = {
            "status": outcome,
            "raw_status": raw_status,
            "evidence_event_ids": evidence_event_ids,
            "evidence": evidence,
            "correction": correction,
        }
        action_evidence = [f"event:{trigger.event_id}"] + [
            f"event:{event_id}" for event_id in evidence_event_ids
        ]
        action = ProposedAction(
            type=InterventionType.ANNOTATE,
            session_id=session.id,
            goal_id=goal.id,
            payload={
                "context_ids": [item.id for item in (*claim_items, *result_items)],
                "verification_context_id": receipt_item.id,
                "channel": "mcp",
            },
            rationale="Persist a bounded claim-verification receipt with scoped evidence.",
            evidence=action_evidence[:12],
            confidence=0.95 if outcome != "uncertain" else 0.5,
            risk=RiskLevel.LOW,
            reversible=True,
        )
        supervisor_result = SupervisorResult(
            action=action,
            used_llm=False,
            diagnosis="mcp_claim_verification",
        )
        verdict = self.policy.decide(action)
        if verdict != PolicyVerdict.ALLOW:
            raise PermissionError("local policy does not allow MCP claim annotation")
        intervention = self._intervention(
            event=trigger,
            session=session,
            result=supervisor_result,
            verdict=verdict,
            outcome="annotated",
            action_taken=action.type.value,
            claims=extracted_claims,
            verification=verification_receipt,
        )
        intervention.id = f"int_verify_{artifact_key}"
        intervention.created_at = observed_at
        intervention.outcome = f"claim_verification_{outcome}"
        intervention.metadata["mcp_principal_id"] = principal.principal_id
        status = {
            "supported": "verified",
            "contradicted": "contradicted",
            "uncertain": "uncertain",
        }[outcome]
        response = {
            "status": status,
            "raw_status": raw_status,
            "outcome": outcome,
            "verified": outcome == "supported",
            "claims": extracted_claims,
            "evidence": evidence,
            "correction": correction,
            "verified_items": [item.model_dump(mode="json") for item in verified_items],
            "item": receipt_item.model_dump(mode="json"),
            "intervention": intervention.model_dump(mode="json"),
        }
        await self.store.require_session_workspace_current(session)
        committed = await self.store.commit_claim_verification(
            principal_id=principal.principal_id,
            tool=MCP_VERIFY_CLAIM_TOOL,
            request_id=request.idempotency_key,
            request_fingerprint=request_fingerprint,
            evidence_event_ids=evidence_event_ids,
            event=trigger,
            claim_items=claim_items,
            result_items=result_items,
            intervention=intervention,
            response=response,
        )
        stored_response = dict(committed["response"])
        stored_response["mutation_id"] = committed["mutation_id"]
        stored_response["replayed"] = not committed["created"]
        if committed["created"]:
            await self.bus.publish("intervention", stored_response["intervention"])
        return stored_response

    async def _delivered_context_item_ids(
        self,
        target: HarnessSession,
        goal: Goal,
    ) -> set[str]:
        project_id = target.project_id or target.cwd
        if not project_id:
            raise ProjectIdentityBlockedError(
                "handoff history requires an authoritative project binding",
                code="artifact_project_identity_unbound",
            )
        delivered: set[str] = set()
        for prior in await self.store.list_interventions_for_authority(
            target.id,
            goal_id=goal.id,
            project_id=project_id,
            harness_type=target.harness_type,
        ):
            if prior.proposed_action.type != InterventionType.FRESH_HANDOFF:
                continue
            delivery_status = str((prior.metadata or {}).get("handoff_delivery_status") or "")
            if prior.result != "handoff_injected" and delivery_status not in {
                "dispatching",
                "delivering",
                "delivered",
                "delivery_uncertain",
            }:
                continue
            raw_bundle = prior.proposed_action.payload.get("bundle")
            if not isinstance(raw_bundle, dict):
                continue
            for raw_item in raw_bundle.get("items") or []:
                if isinstance(raw_item, dict) and raw_item.get("id"):
                    delivered.add(str(raw_item["id"]))
        return delivered

    async def _duplicate_sibling_work(
        self,
        session: HarnessSession,
        event: HarnessEvent,
    ) -> dict[str, str] | None:
        """Detect overlapping observed work already done by another attached agent."""
        if not session.goal_id:
            return None
        siblings: list[tuple[str, str, list[HarnessEvent]]] = []
        project_id = session.project_id or session.cwd
        if not project_id:
            return None
        for row in await self.store.list_sessions_for_goal_for_authority(
            session.goal_id,
            project_id=project_id,
        ):
            if (
                row.id == session.id
                or row.goal_id != session.goal_id
                or row.status == SessionStatus.DETACHED
                or row.supervision_paused
            ):
                continue
            recent = await self.store.recent_events_for_authority(
                row.id,
                goal_id=session.goal_id,
                project_id=project_id,
                harness_type=row.harness_type,
                limit=40,
            )
            siblings.append((row.id, str(row.harness_type), recent))
        if not siblings:
            return None
        return duplicate_sibling_work(event, siblings)

    async def _maybe_auto_handoff(
        self,
        session: HarnessSession,
        event: HarnessEvent,
        verification: dict | None = None,
    ) -> None:
        """Move each newly relevant observed item once, without transcript dumping."""
        live_source = await self.store.get_session_for_authority(
            session.id,
            require_goal_binding=True,
        )
        if live_source is None or live_source.goal_id != session.goal_id:
            return
        session = live_source
        content = (event.message_delta or event.command or "").strip()
        project_key = session.project_id or session.cwd
        explicitly_relevant = bool((event.metadata or {}).get("handoff_relevant"))
        if len(content) < 12 or not session.goal_id or not project_key:
            return
        if is_desktop_observe_session(session):
            return
        if not explicitly_relevant and _HANDOFF_SIGNAL.search(content) is None:
            return
        if (
            event.event_type == EventType.STOP
            and not explicitly_relevant
            and _COMPLETION_SIGNAL.search(content)
            and str((verification or {}).get("status") or "") != "supported"
        ):
            # Never propagate a completion claim before independent support exists.
            return
        if session.supervision_paused or self.supervision_paused:
            return
        goal = await self.store.get_goal_for_authority(session.goal_id)
        if goal is None:
            return
        active_targets = {
            SessionStatus.WORKING,
            SessionStatus.VERIFYING,
            SessionStatus.DRIFTING,
            SessionStatus.BLOCKED,
        }
        siblings = [
            row
            for row in await self.store.list_sessions_for_goal_for_authority(
                goal.id,
                project_id=project_key,
            )
            if row.id != session.id
            and row.goal_id == session.goal_id
            and row.status in active_targets
            and not row.supervision_paused
            and not is_desktop_observe_session(row)
        ]
        if not siblings:
            return
        items = await self.store.list_context_for_authority(
            project_key,
            goal_id=goal.id,
        )
        recent = await self.store.recent_events_for_authority(
            session_id=session.id,
            goal_id=goal.id,
            project_id=project_key,
            harness_type=session.harness_type.value,
            limit=12,
        )
        for candidate in siblings:
            record: dict | None = None
            async with self._handoff_mutation_lock:
                target = await self.store.get_session_for_authority(
                    candidate.id,
                    require_goal_binding=True,
                )
                if (
                    target is None
                    or target.goal_id != session.goal_id
                    or target.status not in active_targets
                    or target.supervision_paused
                    or is_desktop_observe_session(target)
                ):
                    continue
                if await self._negotiate_capabilities(target):
                    await self.store.upsert_session(target)
                delivered = await self._delivered_context_item_ids(target, goal)
                bundle = build_bundle(
                    goal,
                    target,
                    items,
                    recent,
                    [session.id],
                    token_budget=12_000,
                    exclude_item_ids=delivered,
                )
                if not bundle.items:
                    continue
                item_ids = sorted(item.id for item in bundle.items)
                request = ContextHandoffRequest(
                    idempotency_key=_auto_handoff_idempotency_key(
                        event_id=event.event_id,
                        source_session_id=session.id,
                        target_session_id=target.id,
                        goal_id=goal.id,
                        token_budget=12_000,
                        item_ids=item_ids,
                    ),
                    target_session_id=target.id,
                    token_budget=12_000,
                )
                try:
                    record = await self._reserve_context_handoff_locked(
                        source=session,
                        target=target,
                        goal=goal,
                        bundle=bundle,
                        principal_id="system_auto_handoff",
                        request=request,
                        human_requested=False,
                        actor_assurance=None,
                        diagnosis="relevance_scored_automatic_context_handoff",
                        origin_event=event,
                    )
                except PermissionError as exc:
                    if str(exc) == "handoff policy or capability denied delivery":
                        continue
                    raise
            if record is None:
                continue
            result = await self._dispatch_operator_handoff(
                record,
                replayed=not bool(record.get("created")),
            )
            if result["status"] in {"reserved", "dispatching"}:
                raise RuntimeError("automatic handoff dispatch remains pending")

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
        verification: dict | None = None,
        intervention_id: str | None = None,
        created_at: datetime | None = None,
    ) -> Intervention:
        action = result.action
        return Intervention(
            id=intervention_id or new_id("int_"),
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
            created_at=created_at or utcnow(),
            metadata={
                "used_llm": result.used_llm,
                "traces": result.traces,
                "inference_request_id": result.inference_request_id,
                "local_invocation_id": result.local_invocation_id,
                "inference_status": result.inference_status,
                "model_call_count": result.model_call_count,
                "model_name": result.model_name,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "backend": result.backend,
                "provider": result.provider,
                "base_url": result.base_url,
                "auth_mode": result.auth_mode,
                "config_fingerprint": result.config_fingerprint,
                "runtime": result.runtime,
                "runtime_version": result.runtime_version,
                "model_class": result.model_class,
                "evidence_tools": result.evidence_tools,
                "evidence_refs": list(result.evidence_refs),
                "evidence_observations": [
                    item.model_dump(mode="json") for item in result.evidence_observations
                ],
                "independent_verifier": (
                    result.independent_verifier.model_dump(mode="json")
                    if result.independent_verifier is not None else None
                ),
                "execution_mode": result.execution_mode,
                "transport": result.transport,
                "transport_invocation_id": result.transport_invocation_id,
                "transport_request_id": result.transport_request_id,
                "transport_status": result.transport_status,
                "latency_ms": result.latency_ms,
                "claims": claims or [],
                "verification": verification or {},
                "trigger_event_id": event.event_id,
                "permission_request_id": (
                    action.payload.get("request_id")
                    if action.type == InterventionType.RESPOND_PERMISSION
                    else None
                ),
            },
        )

    async def refresh_desktop_sessions(self) -> None:
        now = time.monotonic()
        last_attempt = self._desktop_refresh_attempted_at
        if self._desktop_refresh_lock.locked() or (
            last_attempt is not None
            and now - last_attempt < DESKTOP_REFRESH_MIN_INTERVAL_SECONDS
        ):
            return
        live = {"working", "verifying", "drifting", "needs_decision", "blocked"}
        idle = {"idle", "discovered"}

        async def discover_one(name: str) -> tuple[str, list[HarnessSession] | None]:
            adapter = self.adapters.get(name)
            if adapter is None:
                return name, None
            try:
                return name, await asyncio.wait_for(
                    adapter.discover_sessions(),
                    timeout=DESKTOP_DISCOVERY_TIMEOUT_SECONDS,
                )
            except Exception:
                return name, None

        async with self._desktop_refresh_lock:
            last_attempt = self._desktop_refresh_attempted_at
            if last_attempt is not None and (
                time.monotonic() - last_attempt < DESKTOP_REFRESH_MIN_INTERVAL_SECONDS
            ):
                return
            # Record the attempt before adapter work. Even a caller-cancelled or
            # failed discovery receives a short backoff instead of hot-looping.
            self._desktop_refresh_attempted_at = time.monotonic()
            from pex_bridge.adapters.desktop import (
                capture_running_image_snapshot,
                scoped_running_image_snapshot,
            )

            process_snapshot = await asyncio.to_thread(capture_running_image_snapshot)
            with scoped_running_image_snapshot(process_snapshot):
                discoveries = await asyncio.gather(
                    *(discover_one(name) for name in DESKTOP_REFRESH_ADAPTERS)
                )
            seen: dict[str, set[str]] = {}
            for name, discovered in discoveries:
                if discovered is None:
                    continue
                discovery_generation = f"{name}:{uuid4().hex}"
                seen[name] = {session.id for session in discovered}
                for session in discovered:
                    session.metadata["discovery_generation"] = discovery_generation
                    existing = await self.store.get_session_for_authority(session.id)
                    observe_tile = is_desktop_observe_session(session)
                    if existing:
                        session.goal_id = None if observe_tile else existing.goal_id
                        session.supervision_paused = existing.supervision_paused
                        source = (session.metadata or {}).get("source") or (
                            existing.metadata or {}
                        ).get("source")
                        if (
                            existing.status.value in live
                            and session.status.value in idle
                            and source != "desktop"
                        ):
                            session.status = existing.status
                            session.last_activity = existing.last_activity
                    await self.store.upsert_session(
                        session,
                        allow_goal_change=observe_tile,
                    )
            for listed in await self.store.list_sessions():
                prefix = listed.id.split(":", 1)[0]
                if prefix == "claude":
                    prefix = "claude_code"
                if prefix not in seen:
                    continue
                if listed.id in seen[prefix]:
                    continue
                control = await self.store.get_session_control_state(listed.id)
                if control is None:
                    continue
                stored = control["session"]
                if stored.id in seen[prefix]:
                    continue
                source = str((stored.metadata or {}).get("source") or "")
                desktop_row = stored.vendor_session_id == "desktop" or source == "desktop"
                stale_listed_codex = (
                    prefix == "codex"
                    and not desktop_row
                    and stored.status in {SessionStatus.DISCOVERED, SessionStatus.IDLE}
                )
                if not desktop_row and not stale_listed_codex:
                    continue
                await self.store.mark_session_detached(
                    stored.id,
                    expected_revision=control["revision"],
                    expected_discovery_generation=control["discovery_generation"],
                )
            self._desktop_refresh_attempted_at = time.monotonic()

    async def current_projection(
        self,
        *,
        session_limit: int,
        session_scan_limit: int,
        intervention_limit: int,
        event_limit: int,
    ) -> dict[str, object]:
        """Build a bounded present-tense view without promoting forensic history."""

        if not 1 <= session_limit <= session_scan_limit <= 1_000:
            raise ValueError("current projection session limits are invalid")
        if not 0 <= intervention_limit <= 1_000:
            raise ValueError("current projection intervention limit is invalid")
        if not 0 <= event_limit <= 1_000:
            raise ValueError("current projection event limit is invalid")

        forensic_sessions = await self.store.list_sessions(limit=session_scan_limit)
        current_sessions: list[HarnessSession] = []
        for forensic_session in forensic_sessions:
            try:
                current = await self.store.get_session_for_authority(forensic_session.id)
            except ProjectIdentityBlockedError:
                continue
            if current is not None:
                current_sessions.append(current)

        sessions = current_sessions[:session_limit]
        goals: dict[str, Goal] = {}
        interventions_by_id: dict[str, Intervention] = {}
        interventions_truncated = False
        events_by_id: dict[str, HarnessEvent] = {}
        accepted_sessions: list[HarnessSession] = []
        for session in sessions:
            if session.goal_id is None:
                accepted_sessions.append(session)
                continue
            try:
                goal = goals.get(session.goal_id)
                if goal is None:
                    goal = await self.store.get_goal_for_authority(session.goal_id)
                    if goal is None:
                        continue
                    goals[goal.id] = goal
                project_id = session.project_id or session.cwd
                if project_id is None:
                    continue
                if intervention_limit:
                    per_session_limit = min(intervention_limit + 1, 1_000)
                    rows = await self.store.list_interventions_for_authority(
                        session.id,
                        goal_id=goal.id,
                        project_id=project_id,
                        harness_type=session.harness_type,
                        limit=per_session_limit,
                    )
                    if len(rows) > intervention_limit or (
                        intervention_limit == 1_000 and len(rows) == intervention_limit
                    ):
                        interventions_truncated = True
                    interventions_by_id.update({row.id: row for row in rows})
                if event_limit:
                    rows = await self.store.recent_events_for_authority(
                        session.id,
                        goal_id=goal.id,
                        project_id=project_id,
                        harness_type=session.harness_type,
                        limit=event_limit,
                    )
                    events_by_id.update({row.event_id: row for row in rows})
            except ProjectIdentityBlockedError:
                # The binding may have been quarantined or rebound between the
                # session read and its related artifact reads.  In that case the
                # whole row is history, not a partially current projection.
                goals.pop(session.goal_id, None)
                continue
            accepted_sessions.append(session)

        interventions = sorted(
            interventions_by_id.values(),
            key=lambda row: (row.created_at, row.id),
            reverse=True,
        )[:intervention_limit]
        if len(interventions_by_id) > intervention_limit:
            interventions_truncated = True
        events = sorted(
            events_by_id.values(),
            key=lambda row: (row.ts, row.event_id),
            reverse=True,
        )[:event_limit]
        return {
            "sessions": accepted_sessions,
            "goals": goals,
            "interventions": interventions,
            "events": events,
            "sessions_truncated": (
                len(current_sessions) > session_limit
                or len(forensic_sessions) == session_scan_limit
            ),
            "interventions_truncated": interventions_truncated,
        }

    async def pet_snapshot(self) -> dict:
        projection = await self.current_projection(
            session_limit=1_000,
            session_scan_limit=1_000,
            intervention_limit=1,
            event_limit=120,
        )
        sessions = projection["sessions"]
        interventions = projection["interventions"]
        goals = projection["goals"]
        now = datetime.now(UTC)
        events = projection["events"]
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
        last_message, last_source = await self._latest_visible_line(last, events)
        transition_mood, transition_headline = pet_transition(last, now)
        if needs:
            named = needs[0].harness_type.value.replace("_", " ").title()
            headline = f"{named} needs a decision"
        elif working:
            headline = f"{working} working · {len(needs)} need you"
            if drifting:
                headline += f" · {drifting} drifting"
            if blocked:
                headline += f" · {blocked} blocked"
        elif drifting:
            drifted = [item for item in live if item.status.value == "drifting"]
            named = drifted[0].harness_type.value.replace("_", " ").title()
            headline = f"{named} drifting" if len(drifted) == 1 else f"{drifting} drifting"
            if blocked:
                headline += f" · {blocked} blocked"
        elif blocked:
            headline = f"{blocked} blocked"
        else:
            headline = "quiet"
        if not needs and not drifting and transition_mood in {"handoff", "approved"}:
            headline = transition_headline or headline
        elif not drifting and not working and not blocked and transition_mood == "observing":
            headline = transition_headline or headline
        mood = (
            "decision"
            if needs
            else "warning"
            if blocked
            else "drift"
            if drifting
            else transition_mood
            if transition_mood in {"handoff", "approved"}
            else "working"
            if working
            else transition_mood or "idle"
        )
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
            "mood": mood,
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
                "verification_status": (
                    ((last.metadata or {}).get("verification") or {}).get("status")
                ),
                "evidence_tools": list((last.metadata or {}).get("evidence_tools") or [])[:12],
            },
            "sessions": sessions_out,
            "ts": now.isoformat(),
        }

    async def _latest_visible_line(
        self,
        last: Intervention | None,
        events: list[HarnessEvent],
    ) -> tuple[str | None, str | None]:
        fallback: tuple[str | None, str | None] = (None, None)
        for event in events:
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
            if (
                text
                and "deterministic_triage" not in text.lower()
                and text.lower() not in {"noop", "ok"}
            ):
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
            # A newly confirmed shared Codex subscription deliberately has no
            # invented activity timestamp. It must still be selectable so the
            # operator can attach the persistent goal before the first event.
            # Detached/unknown historical rows remain excluded by status and
            # connection-kind checks.
            if (session.metadata or {}).get("connection_kind") != "codex_shared":
                continue
            extras.append(session)
            seen.add(key)
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
