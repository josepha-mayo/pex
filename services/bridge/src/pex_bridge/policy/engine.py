from __future__ import annotations

import re

from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, AutonomyLevel, PolicyVerdict

_AUTO_ALLOW = [
    re.compile(r"^(pytest|python\s+-m\s+pytest)\b", re.I),
    re.compile(r"^(npm|pnpm|yarn)\s+test\b", re.I),
    re.compile(r"^cargo\s+test\b", re.I),
    re.compile(r"^go\s+test\b", re.I),
    re.compile(r"^(ruff|eslint|tsc|mypy|pyright|black|prettier)\b", re.I),
    re.compile(r"^(npm|pnpm|yarn)\s+run\s+(lint|typecheck|test)\b", re.I),
    re.compile(r"^(npm|pnpm)\s+run\s+build\b", re.I),
]

_ALWAYS_ASK = [
    re.compile(r"\bgit\s+push\s+.*--force\b", re.I),
    re.compile(r"\brm\s+(-rf|--recursive)\b", re.I),
    re.compile(r"\bdrop\s+table\b", re.I),
    re.compile(r"\bkubectl\s+delete\b", re.I),
    re.compile(r"\bterraform\s+destroy\b", re.I),
    re.compile(r"\baws\s+.*delete\b", re.I),
    re.compile(r"\bchmod\s+777\b", re.I),
    re.compile(r"\bcurl\b.*\|\s*(ba)?sh\b", re.I),
]


class PolicyEngine:
    def __init__(self, autonomy: AutonomyLevel = AutonomyLevel.MANAGE) -> None:
        self.autonomy = autonomy

    def command_risk(self, command: str | None) -> RiskLevel:
        if not command:
            return RiskLevel.LOW
        if any(p.search(command) for p in _ALWAYS_ASK):
            return RiskLevel.IRREVERSIBLE
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
        if command:
            risk = self.command_risk(command)

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
            if self.autonomy in {AutonomyLevel.NUDGE, AutonomyLevel.MANAGE, AutonomyLevel.AUTOPILOT}:
                if action.type in {InterventionType.CONTINUE_SESSION, InterventionType.INJECT_CONTEXT} and self.autonomy == AutonomyLevel.NUDGE:
                    return PolicyVerdict.DENY
                return PolicyVerdict.ALLOW
            return PolicyVerdict.DENY

        if action.type in {
            InterventionType.APPLY_OVERLAY,
            InterventionType.REVERT_OVERLAY,
            InterventionType.FRESH_HANDOFF,
            InterventionType.CLEANUP,
        }:
            if self.autonomy in {AutonomyLevel.MANAGE, AutonomyLevel.AUTOPILOT} and action.reversible:
                return PolicyVerdict.ALLOW
            return PolicyVerdict.ASK_HUMAN

        if action.type in {InterventionType.STOP_AGENT, InterventionType.START_AGENT, InterventionType.FORK_PROBE}:
            return PolicyVerdict.ASK_HUMAN if self.autonomy != AutonomyLevel.AUTOPILOT else PolicyVerdict.ALLOW

        return PolicyVerdict.ASK_HUMAN
