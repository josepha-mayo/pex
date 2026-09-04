from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

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
    """A bounded, closed action vocabulary crossing the supervisor boundary."""

    model_config = ConfigDict(extra="forbid")

    type: InterventionType
    session_id: str = Field(min_length=1, max_length=512)
    goal_id: str | None = Field(default=None, min_length=1, max_length=512)
    payload: dict[str, Any] = Field(default_factory=dict, max_length=256)
    rationale: str = Field(min_length=1, max_length=16_384)
    evidence: list[Annotated[str, Field(max_length=8192)]] = Field(
        default_factory=list,
        max_length=128,
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: RiskLevel = RiskLevel.LOW
    reversible: bool = False
    expected_benefit: str = Field(default="", max_length=8192)
    cooldown_seconds: int = Field(default=30, ge=0, le=86_400)
    authority_required: Authority = Authority.LOCAL_POLICY
    requires_capability: str | None = Field(default=None, min_length=1, max_length=128)
