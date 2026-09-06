from __future__ import annotations

import re
from pathlib import PurePosixPath
from uuid import uuid4

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, EventPhase, EventType, HarnessType
from pex_protocol.overlay import Overlay, OverlayDiff
from pex_protocol.supervisor import SupervisorRequest

from pex_supervisor.background import find_abandoned_background
from pex_supervisor.drift import unrelated_refactor
from pex_supervisor.verify import required_files


def _noop(
    request: SupervisorRequest, rationale: str, evidence: list[str] | None = None
) -> ProposedAction:
    return ProposedAction(
        type=InterventionType.NOOP,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={},
        rationale=rationale,
        evidence=evidence or [],
        confidence=0.7,
        risk=RiskLevel.NONE,
        reversible=False,
        cooldown_seconds=5,
    )


def _nudge(
    request: SupervisorRequest,
    rationale: str,
    evidence: list[str],
    message: str,
    *,
    session_status: str | None = None,
) -> ProposedAction:
    payload: dict = {"text": message}
    if session_status:
        payload["session_status"] = session_status
    return ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload=payload,
        rationale=rationale,
        evidence=evidence,
        confidence=0.86,
        risk=RiskLevel.LOW,
        reversible=False,
        expected_benefit=(
            "Redirect the worker toward evidenced progress without interrupting the human."
        ),
        cooldown_seconds=45,
        requires_capability="send_message",
    )


_TYPED_VERIFICATION_KINDS = {
    "pytest",
    "file_count",
    "artifact_tail",
    "command_exit",
    "service_health",
}


def _verification_request_copy(kind: str, relative_targets: list[str], evidence: list[str]) -> str:
    named = ", ".join(relative_targets)
    later_edit = next(
        (
            item.removeprefix("later_edit:")
            for item in reversed(evidence)
            if item.startswith("later_edit:")
        ),
        None,
    )
    after_edit = f" after edit event {later_edit}" if later_edit else ""
    if kind == "pytest":
        scope = (
            f"the requested pytest targets ({named})"
            if relative_targets
            else "the full pytest suite"
        )
        missing = f"No attributable terminal result for {scope} is visible{after_edit}."
        return (
            f"The test-backed completion criterion is unresolved: {missing} "
            f"Run {scope} from the current project root now. Return the exact "
            "command, terminal exit code, and first failing test node if it fails. "
            "Do not claim completion until that result is visible."
        )
    if kind == "file_count":
        scope = named or "the required goal files"
        return (
            f"The file-count completion criterion is unresolved{after_edit}. "
            f"From the current project root, count {scope}. Return the exact "
            "command, terminal exit code, and observed count. Do not claim "
            "completion until that result is visible."
        )
    if kind == "artifact_tail":
        scope = named or "the required artifact"
        return (
            f"The artifact-tail completion criterion is unresolved{after_edit}. "
            f"From the current project root, show a bounded tail of {scope}. "
            "Return the exact command, terminal exit code, and observed tail. "
            "Do not claim completion until that result is visible."
        )
    if kind == "command_exit":
        scope = named or "the required project-relative check"
        return (
            f"The command-exit completion criterion is unresolved{after_edit}. "
            f"From the current project root, run {scope}. Return the exact "
            "command and terminal exit code. Do not claim completion until that "
            "result is visible."
        )
    return (
        f"The service-health completion criterion is unresolved{after_edit}. "
        "From this project, check the local health endpoint. Return the exact "
        "command, terminal exit code, and whether it responded healthy. Do not "
        "claim completion until that result is visible."
    )


def _request_verification(
    request: SupervisorRequest,
    probe: dict,
    evidence: list[str],
) -> ProposedAction:
    kind = str(probe.get("kind") or "")
    if kind not in _TYPED_VERIFICATION_KINDS:
        return _noop(
            request,
            "No safe typed verification backend is available for this uncertainty.",
            [*evidence, f"unsupported_probe:{kind or 'unknown'}"],
        )
    relative_targets = [
        str(item).strip()
        for item in (probe.get("relative_targets") or [])
        if str(item).strip()
    ]
    return ProposedAction(
        type=InterventionType.REQUEST_VERIFICATION,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={
            "probe": probe,
            "text": _verification_request_copy(kind, relative_targets, evidence),
        },
        rationale=(
            "The completion state depends on typed evidence, but no current "
            "matching terminal result is observable. Request evidence before "
            "judging the claim."
        ),
        evidence=evidence,
        confidence=0.9,
        risk=RiskLevel.LOW,
        reversible=False,
        expected_benefit="Replace uncertainty with an attributable pass or exact failure.",
        cooldown_seconds=120,
        requires_capability="send_message",
    )


def _can_overlay(request: SupervisorRequest) -> bool:
    caps = request.session.capabilities or {}
    if caps.get("modify_config") is True:
        return True
    return request.session.harness_type == HarnessType.SYNTHETIC


_DELETE_COMMAND = re.compile(
    r"\b(?:rm|del|erase|rmdir|rd|remove-item|unlink|shutil\.rmtree|os\.remove)\b",
    re.I,
)


def _deletes_required_artifact(command: str | None, goal) -> str | None:
    if not command or goal is None:
        return None
    if _DELETE_COMMAND.search(command) is None:
        return None
    haystack = command.replace("\\", "/").casefold()
    for name in required_files(goal):
        needle = PurePosixPath(str(name).replace("\\", "/")).name.casefold()
        if not needle:
            continue
        if re.search(rf"(?<![a-z0-9._-]){re.escape(needle)}(?![a-z0-9._-])", haystack):
            return name
    return None


_CONSUMER_COMMAND = re.compile(
    r"\b(?:eval_runner|eval(?:uate)?|train(?:ing)?|deploy|bench(?:mark)?|inferenc(?:e|ing))\b",
    re.I,
)
_PRODUCER_COMMAND = re.compile(
    r"\b(?:generat|prepar|creat|write|dump|export|download|ingest|fetch)\b",
    re.I,
)


def _is_downstream_consumer(command: str, missing: list[str]) -> bool:
    text = command.strip()
    if not text or not missing:
        return False
    if _PRODUCER_COMMAND.search(text):
        return False
    lowered = text.replace("\\", "/").casefold()
    if any(PurePosixPath(name.replace("\\", "/")).name.casefold() in lowered for name in missing):
        return False
    return _CONSUMER_COMMAND.search(text) is not None


_EVIDENCE_BEFORE_DONE = "evidence-before-done"
_FINGERPRINT_OVERLAY_MIN_SAMPLES = 2
_CONTEXT_HEALTH_OVERLAY_MIN_COMPACTIONS = 2


def _forgotten_facts(request: SupervisorRequest) -> list[str]:
    raw = request.scores.features.get("forgotten_facts") or []
    if not isinstance(raw, list):
        return []
    facts: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in facts:
            facts.append(text[:400])
        if len(facts) >= 6:
            break
    return facts


def _context_health_overlay_ready(request: SupervisorRequest) -> bool:
    health = request.scores.features.get("context_health")
    try:
        score = float(health) if health is not None else 1.0
    except (TypeError, ValueError):
        score = 1.0
    compaction_count = int(request.scores.features.get("compaction_count") or 0)
    return (
        compaction_count >= _CONTEXT_HEALTH_OVERLAY_MIN_COMPACTIONS
        and bool(_forgotten_facts(request))
        and score < 0.6
        and _can_overlay(request)
    )


def _recommended_overlays(request: SupervisorRequest) -> list[str]:
    raw = request.scores.features.get("recommended_overlays") or []
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if str(item).strip()]


def _fingerprint_overlay_ready(request: SupervisorRequest) -> bool:
    gap_stops = int(request.scores.features.get("gap_stop_sessions") or 0)
    return (
        gap_stops >= _FINGERPRINT_OVERLAY_MIN_SAMPLES
        and _EVIDENCE_BEFORE_DONE in _recommended_overlays(request)
        and _can_overlay(request)
    )


def _drift_redirect_threshold(request: SupervisorRequest) -> float:
    if int(request.scores.features.get("gap_stop_sessions") or 0) >= (
        _FINGERPRINT_OVERLAY_MIN_SAMPLES
    ):
        return 0.6
    return 0.75


def _debug_overlay(request: SupervisorRequest, evidence: list[str]) -> ProposedAction:
    instructions = (
        "Stay on the failing reproduction. Do not start unrelated research. "
        "Preserve the failing state until the attached acceptance criteria move."
    )
    extra = {"phase": "debug", "pin": evidence[0] if evidence else ""}
    if _EVIDENCE_BEFORE_DONE in _recommended_overlays(request):
        instructions += (
            " Do not treat a stop as done without the attached acceptance evidence."
        )
        extra["fingerprint_overlay"] = _EVIDENCE_BEFORE_DONE
    overlay = Overlay(
        id=f"ovl_{uuid4().hex[:12]}",
        session_id=request.session.id,
        reason="Repeated identical failures; switch to a debug-phase overlay.",
        diff=OverlayDiff(
            tools_disabled=["WebSearch", "Browser", "web_search"],
            extra=extra,
            system_instructions=instructions,
        ),
        ttl_seconds=1800,
        scope="session",
    )
    return ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={
            "overlay": overlay.model_dump(mode="json"),
            "session_status": "drifting",
        },
        rationale="Current harness shape is wasting work on repeated identical failures.",
        evidence=evidence,
        confidence=0.8,
        risk=RiskLevel.LOW,
        reversible=True,
        expected_benefit="Temporarily pin debug tools and drop unrelated research tools.",
        cooldown_seconds=120,
        requires_capability="modify_config",
    )


def _evidence_overlay(
    request: SupervisorRequest, evidence: list[str], correction: str
) -> ProposedAction:
    overlay = Overlay(
        id=f"ovl_{uuid4().hex[:12]}",
        session_id=request.session.id,
        reason="Harness fingerprint shows repeated premature STOPs; pin evidence-before-done.",
        diff=OverlayDiff(
            extra={"phase": "evidence-before-done"},
            system_instructions=correction,
        ),
        ttl_seconds=1800,
        scope="session",
    )
    return ProposedAction(
        type=InterventionType.APPLY_OVERLAY,
        session_id=request.session.id,
        goal_id=request.goal.id if request.goal else None,
        payload={"overlay": overlay.model_dump(mode="json")},
        rationale=(
            "This harness has repeated premature STOPs; apply a reversible "
            "evidence-before-done overlay with the specific missing evidence."
        ),
        evidence=[*evidence, "fingerprint:evidence-before-done"],
        confidence=0.82,
        risk=RiskLevel.LOW,
        reversible=True,
        expected_benefit="Keep the worker on the attached acceptance evidence before stopping.",
        cooldown_seconds=120,
        requires_capability="modify_config",
    )


def plan_deterministic(request: SupervisorRequest) -> ProposedAction:
    """Cheap facts only. Stop/completion copy is never canned worker text.

    A stop event is a trigger to inspect (via the supervisor model), not to nag.
    """
    event = request.event
    goal = request.goal
    if event.event_type == EventType.USER_PROMPT and request.notes.startswith(
        "possible_contradiction"
    ):
        constraint = ""
        if ":" in request.notes:
            # Pipeline notes append transport policy as a separate paragraph.
            # That policy is context, never part of the human's ledger rule.
            constraint = request.notes.split("\n\n", 1)[0].split(":", 1)[1].strip()[:200]
        question = (
            (
                f"This conflicts with the active constraint '{constraint}'. "
                "Did you mean to keep that ledger rule, or is this an explicit override?"
            )
            if constraint
            else (
                "This prompt conflicts with a persistent constraint. "
                "Confirm override or keep the ledger."
            )
        )
        return ProposedAction(
            type=InterventionType.ASK_HUMAN,
            session_id=request.session.id,
            goal_id=goal.id if goal else None,
            payload={
                "prompt": event.message_delta,
                "question": question,
            },
            rationale="Human prompt appears to contradict the persistent intent ledger.",
            evidence=[request.notes, event.message_delta or ""],
            confidence=0.8,
            risk=RiskLevel.MEDIUM,
            reversible=False,
            authority_required=Authority.HUMAN,
        )

    if event.event_type == EventType.USER_PROMPT and request.notes.startswith(
        "dangerous_ambiguity"
    ):
        title = ((goal.title if goal else "") or "the attached goal").strip()
        return ProposedAction(
            type=InterventionType.ANNOTATE,
            session_id=request.session.id,
            goal_id=goal.id if goal else None,
            payload={
                "prompt": event.message_delta,
                "text": (
                    f"Interpret this request as work on '{title}'. "
                    "The prompt is ambiguous; keep the attached acceptance criteria and "
                    "constraints. Do not treat speed or vagueness as permission to skip "
                    "required evidence."
                ),
            },
            rationale="User prompt is accidentally ambiguous relative to the attached ledger.",
            evidence=[request.notes, event.message_delta or ""],
            confidence=0.78,
            risk=RiskLevel.LOW,
            reversible=False,
        )

    command = event.command or (event.tool_input or {}).get("command")
    doomed = _deletes_required_artifact(str(command or ""), goal)
    if doomed and event.event_type in {
        EventType.PERMISSION_REQUEST,
        EventType.SHELL,
        EventType.TOOL_CALL,
        EventType.FILE_EDIT,
    }:
        evidence = [f"required:{doomed}", str(command or "")[:200]]
        if event.phase == EventPhase.BEFORE:
            return ProposedAction(
                type=InterventionType.ASK_HUMAN,
                session_id=request.session.id,
                goal_id=goal.id if goal else None,
                payload={
                    "command": command,
                    "question": (
                        f"{doomed} is still required by the attached ledger. "
                        "Keep that artifact, or confirm this is an explicit cleanup override."
                    ),
                },
                rationale=(
                    "Worker is about to delete an artifact still required by the attached goal."
                ),
                evidence=evidence,
                confidence=0.86,
                risk=RiskLevel.HIGH,
                reversible=False,
                authority_required=Authority.HUMAN,
            )
        return _nudge(
            request,
            "Worker deleted or is deleting an artifact still required by the attached goal.",
            evidence,
            (
                f"{doomed} is still required by the attached ledger. "
                "Restore that artifact before continuing."
            ),
        )

    if request.notes.startswith("agent_contradiction"):
        constraint = ""
        if ":" in request.notes:
            constraint = request.notes.split(":", 1)[1].strip()[:200]
        named = f" '{constraint}'" if constraint else ""
        evidence = [request.notes, str(event.command or event.message_delta or "")[:200]]
        if event.phase == EventPhase.BEFORE:
            return ProposedAction(
                type=InterventionType.ASK_HUMAN,
                session_id=request.session.id,
                goal_id=goal.id if goal else None,
                payload={
                    "command": command,
                    "question": (
                        f"This action conflicts with the active constraint{named}. "
                        "Keep that ledger rule, or confirm an explicit override."
                    ),
                },
                rationale="Observed worker action conflicts with the persistent intent ledger.",
                evidence=evidence,
                confidence=0.82,
                risk=RiskLevel.MEDIUM,
                reversible=False,
                authority_required=Authority.HUMAN,
            )
        return _nudge(
            request,
            "Observed worker action conflicts with the persistent intent ledger.",
            evidence,
            (
                f"That action conflicts with the active constraint{named}. "
                "Stay on the attached ledger."
            ),
        )

    if (
        event.event_type
        in {
            EventType.PERMISSION_REQUEST,
            EventType.SHELL,
            EventType.TOOL_CALL,
            EventType.FILE_READ,
        }
        and event.phase == EventPhase.BEFORE
    ):
        return ProposedAction(
            type=InterventionType.RESPOND_PERMISSION,
            session_id=request.session.id,
            goal_id=goal.id if goal else None,
            payload={
                "request_id": (event.approval_request or {}).get("request_id") or event.event_id,
                "command": command,
                "decision_source": "local_policy",
                "approval_method": (event.approval_request or {}).get("method")
                or (event.approval_request or {}).get("hook"),
                "file_paths": list(event.file_paths or []),
                "tool_name": event.tool_name,
            },
            rationale="Routine permission brokered by local policy.",
            evidence=[
                str(command or event.tool_name or "permission request"),
                *(f"path:{path}" for path in event.file_paths),
            ],
            confidence=0.7,
            risk=RiskLevel.MEDIUM,
            reversible=False,
        )

    missing = [
        str(item)
        for item in (request.scores.features.get("missing_prerequisites") or [])
        if str(item).strip()
    ]
    if (
        event.event_type in {EventType.SHELL, EventType.TOOL_CALL}
        and event.phase == EventPhase.DURING
        and missing
        and _is_downstream_consumer(str(command or ""), missing)
    ):
        name = missing[0]
        return _nudge(
            request,
            "Downstream command started before a required artifact exists.",
            [*(f"missing:{item}" for item in missing[:8]), str(command or "")[:200]],
            (
                f"{name} is missing from the workspace. Produce that artifact "
                "before continuing this command."
            ),
        )

    duplicate = request.scores.features.get("duplicate_work")
    if isinstance(duplicate, dict) and duplicate.get("harness"):
        target = str(duplicate.get("path") or duplicate.get("command") or "that work")
        return _noop(
            request,
            "Sibling overlap needs semantic review; "
            "shared paths or commands do not prove duplicate work.",
            [
                f"sibling:{duplicate.get('sibling_session_id') or 'unknown'}",
                f"overlap:{target[:200]}",
            ],
        )

    drifted = unrelated_refactor(event, goal)
    if drifted and event.event_type not in {EventType.STOP, EventType.USER_PROMPT}:
        return _nudge(
            request,
            "Worker started a broad refactor unrelated to the attached acceptance criteria.",
            [f"unrelated:{drifted}"],
            (
                f"Recent edits ({drifted}) do not serve the attached ledger. "
                "Return to the remaining acceptance criterion and produce the required evidence."
            ),
            session_status="drifting",
        )

    if (
        event.event_type not in {EventType.STOP, EventType.USER_PROMPT}
        and request.scores.drift >= _drift_redirect_threshold(request)
        and int(request.scores.features.get("repeated_command_count") or 0) >= 3
    ):
        evidence = [
            f"drift={request.scores.drift}",
            f"repeated_command_count={request.scores.features.get('repeated_command_count')}",
            f"identical_error_count={request.scores.features.get('identical_error_count') or 0}",
        ]
        if int(request.scores.features.get("identical_error_count") or 0) >= 1 and _can_overlay(
            request
        ):
            return _debug_overlay(request, evidence)
        return _nudge(
            request,
            "Trajectory is repeating low-information work instead of attached acceptance criteria.",
            evidence,
            (
                "Recent actions repeated without moving the attached acceptance criteria. "
                "Return to the remaining criterion and produce the required evidence."
            ),
            session_status="drifting",
        )

    if event.event_type == EventType.STOP:
        features = request.scores.features or {}
        if features.get("speculative_compare") or features.get("in_speculative_pair"):
            speculative = _speculative_action(request)
            if speculative is not None:
                return speculative
            return _noop(
                request,
                "Waiting for the sibling speculative probe to finish.",
                ["speculative:waiting"],
            )
        verification = features.get("verification") or {}
        correction = str(verification.get("correction") or "").strip()
        evidence = [str(item) for item in (verification.get("evidence") or []) if item]
        if (
            verification.get("status") in {"contradicted", "acceptance_gap"}
            and correction
            and evidence
        ):
            if _fingerprint_overlay_ready(request):
                return _evidence_overlay(request, evidence, correction)
            rationale = (
                "Observed workspace state does not satisfy an explicit acceptance criterion."
                if verification.get("status") == "acceptance_gap"
                else "Worker completion claim is contradicted by observed state."
            )
            return _nudge(
                request,
                rationale,
                evidence,
                correction,
            )
        gathering = verification.get("evidence_gathering") or {}
        probe = gathering.get("probe")
        if (
            verification.get("status") in {"uncertain", "no_claims"}
            and isinstance(probe, dict)
            and gathering.get("state") == "inspected"
        ):
            probe_id = str(probe.get("id") or "unknown")
            uncertain_evidence = [
                f"verification:{verification.get('status')}",
                f"probe:{probe_id}",
                *(
                    str(item)
                    for verdict in verification.get("verdicts") or []
                    if isinstance(verdict, dict)
                    for item in verdict.get("evidence") or []
                ),
            ]
            return _request_verification(
                request,
                probe,
                list(dict.fromkeys(uncertain_evidence))[:128],
            )
        if "abandoned_background" in (request.scores.features or {}):
            abandoned = request.scores.features.get("abandoned_background")
        else:
            abandoned = find_abandoned_background(request.recent_events)
        job = abandoned if isinstance(abandoned, dict) else None
        command_text = str((job or {}).get("command") or "").strip()
        if command_text and job is not None:
            pid = job.get("pid")
            pid_note = f" (pid {pid})" if isinstance(pid, int) else ""
            table = job.get("process_table")
            where = "in the process table" if table == "running" else "in the background"
            return _nudge(
                request,
                "Worker launched a background job and then stopped monitoring it.",
                [
                    f"command:{command_text[:200]}",
                    *([f"pid:{pid}"] if isinstance(pid, int) else []),
                    *([f"process_table:{table}"] if table else []),
                ],
                (
                    f"{command_text}{pid_note} is still running {where}. "
                    "Check that job and wait for it, or collect its output, before stopping."
                ),
            )

    if event.event_type == EventType.STOP:
        speculative = _speculative_action(request)
        if speculative is not None:
            return speculative

    if event.event_type == EventType.COMPACTION and goal is not None:
        title = (goal.title or "").strip() or "attached goal"
        acceptance = "; ".join(item for item in goal.acceptance_criteria[:3] if item) or (
            goal.objective[:200]
        )
        constraints = "; ".join(item for item in goal.constraints[:3] if item)
        files = ", ".join(required_files(goal)[:6])
        forgotten = _forgotten_facts(request)
        lines = [f"Persistent ledger '{title}' still applies after compaction."]
        if acceptance:
            lines.append(f"Acceptance: {acceptance}")
        if constraints:
            lines.append(f"Constraints: {constraints}")
        if files:
            lines.append(f"Required files: {files}")
        if forgotten:
            lines.append("Do not forget: " + "; ".join(forgotten[:4]))
        lines.append("Keep these facts in working context.")
        evidence = [f"goal:{goal.id}", "event:compaction", *forgotten[:4]]
        correction = " ".join(lines)
        if _context_health_overlay_ready(request):
            overlay = Overlay(
                id=f"ovl_{uuid4().hex[:12]}",
                session_id=request.session.id,
                reason=(
                    "Context health degraded after repeated forgotten facts; "
                    "checkpoint durable context and drop unrelated research tools."
                ),
                diff=OverlayDiff(
                    tools_disabled=["WebSearch", "Browser", "web_search"],
                    extra={"phase": "context-health", "pin": "durable-facts"},
                    system_instructions=correction,
                ),
                ttl_seconds=1800,
                scope="session",
            )
            return ProposedAction(
                type=InterventionType.APPLY_OVERLAY,
                session_id=request.session.id,
                goal_id=goal.id,
                payload={"overlay": overlay.model_dump(mode="json")},
                rationale=(
                    "Worker context compacted twice and re-acquired durable facts; "
                    "pin those facts and reduce irrelevant tools."
                ),
                evidence=evidence,
                confidence=0.8,
                risk=RiskLevel.LOW,
                reversible=True,
                expected_benefit=(
                    "Keep forgotten facts loaded without asking the human to babysit context."
                ),
                cooldown_seconds=120,
                requires_capability="modify_config",
            )
        if event.phase == EventPhase.BEFORE:
            return ProposedAction(
                type=InterventionType.ANNOTATE,
                session_id=request.session.id,
                goal_id=goal.id,
                payload={"text": correction},
                rationale="Worker context is about to compact; checkpoint the attached ledger.",
                evidence=evidence,
                confidence=0.86,
                risk=RiskLevel.LOW,
                reversible=False,
                expected_benefit="Keep durable ledger facts in the compacted working context.",
                cooldown_seconds=45,
            )
        return _nudge(
            request,
            "Worker context is about to compact; checkpoint the attached ledger.",
            evidence,
            correction,
        )

    return _noop(
        request,
        (
            "No deterministic fact requires interruption. "
            "Stop/completion needs supervisor inference or silence."
        ),
        [event.event_type.value],
    )


def _can_fork(request: SupervisorRequest) -> bool:
    return (request.session.capabilities or {}).get("fork") is True


def _speculative_action(request: SupervisorRequest) -> ProposedAction | None:
    """Build spec §23: human-gated isolated probes, then keep the winner."""

    features = request.scores.features or {}
    goal = request.goal
    compare = features.get("speculative_compare")
    if isinstance(compare, dict):
        reasons = [str(item) for item in (compare.get("reasons") or []) if item]
        winner_id = str(compare.get("winner_session_id") or "")
        loser_id = str(compare.get("loser_session_id") or "")
        if compare.get("winner") == "tie":
            return ProposedAction(
                type=InterventionType.ASK_HUMAN,
                session_id=request.session.id,
                goal_id=goal.id if goal else None,
                payload={
                    "question": (
                        "Both isolated probes finished similarly. "
                        f"A: {compare.get('winner_approach') or 'first approach'}. "
                        f"B: {compare.get('loser_approach') or 'second approach'}. "
                        "Which should continue?"
                    )
                },
                rationale="Two cheap probes returned comparable evidence; a human should pick.",
                evidence=reasons or ["speculative:tie"],
                confidence=0.7,
                risk=RiskLevel.LOW,
                reversible=False,
                authority_required=Authority.HUMAN,
            )
        if loser_id == request.session.id:
            if (request.session.capabilities or {}).get("stop") is True:
                return ProposedAction(
                    type=InterventionType.STOP_AGENT,
                    session_id=request.session.id,
                    goal_id=goal.id if goal else None,
                    payload={},
                    rationale=(
                        "This isolated probe underperformed the sibling approach; "
                        "dispose it and keep the winner."
                    ),
                    evidence=reasons or ["speculative:loser"],
                    confidence=0.78,
                    risk=RiskLevel.MEDIUM,
                    reversible=False,
                    authority_required=Authority.HUMAN,
                    requires_capability="stop",
                    expected_benefit="Stop the losing probe without leaving a duplicate worker.",
                    cooldown_seconds=60,
                )
            return ProposedAction(
                type=InterventionType.ASK_HUMAN,
                session_id=request.session.id,
                goal_id=goal.id if goal else None,
                payload={
                    "question": (
                        "This probe lost to the sibling approach. "
                        "Stop this worker and keep the winner?"
                    )
                },
                rationale=(
                    "The losing probe should be disposed by a human because stop is unavailable."
                ),
                evidence=reasons or ["speculative:loser"],
                confidence=0.76,
                risk=RiskLevel.MEDIUM,
                reversible=False,
                authority_required=Authority.HUMAN,
            )
        if winner_id == request.session.id:
            winner_approach = str(compare.get("winner_approach") or "this approach")
            loser_approach = str(compare.get("loser_approach") or "the sibling approach")
            return _nudge(
                request,
                "Isolated probe of this approach outperformed the sibling.",
                reasons or ["speculative:winner"],
                (
                    f"Continue {winner_approach}. "
                    f"{loser_approach} did worse on the bounded probe. "
                    "Keep those findings and do not restart the losing worker."
                ),
            )

    if features.get("in_speculative_pair") or features.get("probe_already_running"):
        return None
    if not _can_fork(request) or goal is None:
        return None
    approaches = features.get("competing_approaches")
    bundle = features.get("probe_bundle")
    parent_objective = str(features.get("parent_objective") or "").strip()
    if (
        not isinstance(approaches, list)
        or len(approaches) < 2
        or not isinstance(bundle, dict)
        or not parent_objective
    ):
        return None
    cleaned = [str(item).strip() for item in approaches[:2] if str(item).strip()]
    if len(cleaned) < 2:
        return None
    return ProposedAction(
        type=InterventionType.FORK_PROBE,
        session_id=request.session.id,
        goal_id=goal.id,
        payload={
            "bundle": bundle,
            "parent_objective": parent_objective,
            "approaches": cleaned,
            "probe_budget_tool_calls": 8,
        },
        rationale=(
            "Two cheap approaches are plausible; probe them in isolation "
            "instead of guessing on one worker."
        ),
        evidence=[f"approach:{item[:200]}" for item in cleaned],
        confidence=0.74,
        risk=RiskLevel.MEDIUM,
        reversible=False,
        authority_required=Authority.HUMAN,
        requires_capability="fork",
        expected_benefit="Compare two bounded probes and keep only the winner.",
        cooldown_seconds=180,
    )
