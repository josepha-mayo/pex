from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pex_protocol.actions import ProposedAction
from pex_protocol.enums import PolicyVerdict


class Intervention(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=512)
    session_id: str = Field(min_length=1, max_length=512)
    goal_id: str | None = Field(default=None, min_length=1, max_length=512)
    trigger: str = Field(min_length=1, max_length=128)
    evidence: list[Annotated[str, Field(max_length=8192)]] = Field(
        default_factory=list,
        max_length=128,
    )
    diagnosis: str = Field(max_length=16_384)
    proposed_action: ProposedAction
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: str = Field(min_length=1, max_length=64)
    reversible: bool = False
    authority_required: str = Field(min_length=1, max_length=128)
    action_taken: str = Field(min_length=1, max_length=128)
    policy_verdict: PolicyVerdict
    result: str = Field(default="", max_length=16_384)
    worker_response: str = Field(default="", max_length=65_536)
    outcome: str = Field(default="", max_length=16_384)
    helped: bool | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=256)

    @model_validator(mode="after")
    def require_action_snapshot_consistency(self) -> "Intervention":
        action = self.proposed_action
        if action.session_id != self.session_id or action.goal_id != self.goal_id:
            raise ValueError("intervention/action identity mismatch")
        if self.evidence != action.evidence:
            raise ValueError("intervention/action evidence mismatch")
        if self.confidence != action.confidence:
            raise ValueError("intervention/action confidence mismatch")
        if self.risk != action.risk.value:
            raise ValueError("intervention/action risk mismatch")
        if self.reversible != action.reversible:
            raise ValueError("intervention/action reversibility mismatch")
        if self.authority_required != action.authority_required.value:
            raise ValueError("intervention/action authority mismatch")
        return self
