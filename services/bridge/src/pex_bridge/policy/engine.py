from __future__ import annotations

import re

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, AutonomyLevel, PolicyVerdict
from pex_protocol.overlay import Overlay, locally_proven_session_overlay
from pydantic import ValidationError

_AUTO_ALLOW = [
    re.compile(r"^(pytest|python\s+-m\s+pytest)\b", re.I),
    re.compile(r"^(npm|pnpm|yarn)\s+test\b", re.I),
    re.compile(r"^cargo\s+test\b", re.I),
    re.compile(r"^go\s+test\b", re.I),
    re.compile(r"^(ruff|eslint|tsc|mypy|pyright|black|prettier)\b", re.I),
    re.compile(r"^(npm|pnpm|yarn)\s+run\s+(lint|typecheck|test)\b", re.I),
    re.compile(r"^(npm|pnpm)\s+run\s+build\b", re.I),
]

# An allowlisted prefix does not make a compound shell program safe. Keep
# routine test/lint approvals single-command; shell control, substitution, or
# redirection returns to the human even when the first token is ``pytest``.
_SHELL_CONTROL = re.compile(r"(?:\r|\n|&&|\|\||[;|&<>]|`|\$\()")

_ALWAYS_ASK = [
    re.compile(r"\bgit\s+push\b.*(?:--force|-f)\b", re.I),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.I),
    re.compile(r"\bgit\s+clean\b.*\s-[a-z]*f", re.I),
    re.compile(r"\brm\s+(-rf|--recursive)\b", re.I),
    re.compile(r"\bremove-item\b.*(?:-recurse|-force)", re.I),
    re.compile(r"\b(?:del|erase|rmdir|rd)\b.*(?:/s|/q)", re.I),
    re.compile(r"\bdrop\s+table\b", re.I),
    re.compile(r"\bkubectl\s+delete\b", re.I),
    re.compile(r"\bterraform\s+destroy\b", re.I),
    re.compile(r"\baws\s+.*delete\b", re.I),
    re.compile(r"\bchmod\s+777\b", re.I),
    re.compile(r"\bcurl\b.*\|\s*(ba)?sh\b", re.I),
    re.compile(r"\b(?:npm|pnpm|yarn)\s+publish\b", re.I),
    re.compile(r"\b(?:vercel|netlify|wrangler)\b.*\b(?:--prod|deploy|publish)\b", re.I),
    re.compile(
        r"\b(?:get-content|type|cat)\b.*(?:\.env\b|id_rsa\b|auth\.json\b|credentials)", re.I
    ),
]

_RISK_ORDER = {
    RiskLevel.NONE: 0,
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.IRREVERSIBLE: 4,
}


class PolicyEngine:
    def __init__(self, autonomy: AutonomyLevel = AutonomyLevel.MANAGE) -> None:
        self.autonomy = autonomy

    def command_risk(self, command: str | None) -> RiskLevel:
        if not command:
            return RiskLevel.LOW
        if any(p.search(command) for p in _ALWAYS_ASK):
            return RiskLevel.IRREVERSIBLE
        if _SHELL_CONTROL.search(command):
            return RiskLevel.HIGH
        if any(p.search(command) for p in _AUTO_ALLOW):
            return RiskLevel.NONE
        return RiskLevel.MEDIUM

    def decide(self, action: ProposedAction, command: str | None = None) -> PolicyVerdict:
        if self.autonomy == AutonomyLevel.OBSERVE:
            return PolicyVerdict.DENY
        if self.autonomy == AutonomyLevel.ASSIST and action.type not in {
            InterventionType.ANNOTATE,
            InterventionType.NOTIFY,
            InterventionType.ASK_HUMAN,
            InterventionType.NOOP,
        }:
            return PolicyVerdict.DENY

        command = command or str(action.payload.get("command") or "")
        risk = action.risk
        if command and action.type == InterventionType.RESPOND_PERMISSION:
            # A command classifier may only increase risk.  The supervisor's
            # explicit risk label can carry context that is not visible in the
            # command string (paid compute, production scope, or a one-shot
            # action), so an allowlisted prefix must never downgrade it.
            command_risk = self.command_risk(command)
            deterministic_local_classification = (
                action.payload.get("decision_source") == "local_policy"
                and risk not in {RiskLevel.HIGH, RiskLevel.IRREVERSIBLE}
            )
            if deterministic_local_classification:
                risk = command_risk
            elif _RISK_ORDER[command_risk] > _RISK_ORDER[risk]:
                risk = command_risk

        if action.type == InterventionType.ASK_HUMAN:
            return PolicyVerdict.ASK_HUMAN
        if risk in {RiskLevel.HIGH, RiskLevel.IRREVERSIBLE}:
            return PolicyVerdict.ASK_HUMAN
        if action.authority_required == Authority.HUMAN:
            return PolicyVerdict.ASK_HUMAN

        if action.type == InterventionType.RESPOND_PERMISSION:
            if risk in {RiskLevel.NONE, RiskLevel.LOW} and self.autonomy in {
                AutonomyLevel.MANAGE,
                AutonomyLevel.AUTOPILOT,
            }:
                return PolicyVerdict.ALLOW
            return PolicyVerdict.ASK_HUMAN

        if action.type in {
            InterventionType.SEND_NUDGE,
            InterventionType.INJECT_CONTEXT,
            InterventionType.CONTINUE_SESSION,
            InterventionType.REQUEST_VERIFICATION,
            InterventionType.ANNOTATE,
            InterventionType.NOTIFY,
            InterventionType.NOOP,
            InterventionType.FOCUS_UI,
        }:
            if self.autonomy in {
                AutonomyLevel.NUDGE,
                AutonomyLevel.MANAGE,
                AutonomyLevel.AUTOPILOT,
            }:
                if (
                    action.type == InterventionType.CONTINUE_SESSION
                    and self.autonomy == AutonomyLevel.NUDGE
                ):
                    return PolicyVerdict.DENY
                return PolicyVerdict.ALLOW
            return PolicyVerdict.DENY

        if action.type == InterventionType.FRESH_HANDOFF:
            # Context messages cannot be recalled. Manage/Autopilot is the
            # user's standing authority for a low-risk, privacy-filtered
            # same-goal handoff; never mislabel delivery as reversible.
            if self.autonomy in {AutonomyLevel.MANAGE, AutonomyLevel.AUTOPILOT} and risk in {
                RiskLevel.NONE,
                RiskLevel.LOW,
            }:
                return PolicyVerdict.ALLOW
            return PolicyVerdict.DENY

        if action.type == InterventionType.APPLY_OVERLAY:
            try:
                overlay = Overlay.model_validate(action.payload.get("overlay"))
            except (TypeError, ValidationError):
                overlay = None
            if (
                self.autonomy in {AutonomyLevel.MANAGE, AutonomyLevel.AUTOPILOT}
                and action.reversible
                and risk in {RiskLevel.NONE, RiskLevel.LOW}
                and action.requires_capability == "modify_config"
                and any(str(item).strip() for item in action.evidence)
                and overlay is not None
                and locally_proven_session_overlay(overlay)
            ):
                return PolicyVerdict.ALLOW
            return PolicyVerdict.ASK_HUMAN

        if action.type == InterventionType.REVERT_OVERLAY:
            # Reversion restores the prior authority surface. Automatic expiry
            # uses the original bounded TTL receipt; any newly proposed revert
            # requires an authenticated operator decision.
            return PolicyVerdict.ASK_HUMAN

        if action.type == InterventionType.CLEANUP:
            # Quarantine moves are reversible in principle but still alter the
            # filesystem. Until a standing cleanup policy is explicit and
            # durably bound, every cleanup requires a human dispatch grant.
            return PolicyVerdict.ASK_HUMAN

        if action.type in {
            InterventionType.STOP_AGENT,
            InterventionType.START_AGENT,
            InterventionType.FORK_PROBE,
        }:
            # Starting a turn can spend money, stopping can discard active
            # state, and a fork can duplicate spend. Require a real
            # authenticated human decision even in Autopilot.
            return PolicyVerdict.ASK_HUMAN

        return PolicyVerdict.ASK_HUMAN
