from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from pex_protocol.enums import Authority


class InterventionType(StrEnum):
    NOOP = "NOOP"
    ANNOTATE = "ANNOTATE"
    NOTIFY = "NOTIFY"
    SEND_NUDGE = "SEND_NUDGE"
    INJECT_CONTEXT = "INJECT_CONTEXT"
    CONTINUE_SESSION = "CONTINUE_SESSION"
    REQUEST_VERIFICATION = "REQUEST_VERIFICATION"
    RESPOND_PERMISSION = "RESPOND_PERMISSION"
    APPLY_OVERLAY = "APPLY_OVERLAY"
    REVERT_OVERLAY = "REVERT_OVERLAY"
    FRESH_HANDOFF = "FRESH_HANDOFF"
    START_AGENT = "START_AGENT"
    STOP_AGENT = "STOP_AGENT"
    FORK_PROBE = "FORK_PROBE"
    CLEANUP = "CLEANUP"
    FOCUS_UI = "FOCUS_UI"
    ASK_HUMAN = "ASK_HUMAN"


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    IRREVERSIBLE = "irreversible"


class ProposedAction(BaseModel):
    type: InterventionType
    session_id: str
    goal_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: RiskLevel = RiskLevel.LOW
    reversible: bool = True
    expected_benefit: str = ""
    cooldown_seconds: int = 30
    authority_required: Authority = Authority.LOCAL_POLICY
    requires_capability: str | None = None
