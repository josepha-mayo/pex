from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from pex_protocol.actions import ProposedAction
from pex_protocol.enums import PolicyVerdict


class Intervention(BaseModel):
    id: str
    session_id: str
    goal_id: str | None = None
    trigger: str
    evidence: list[str] = Field(default_factory=list)
    diagnosis: str
    proposed_action: ProposedAction
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk: str
    reversible: bool = True
    authority_required: str
    action_taken: str
    policy_verdict: PolicyVerdict
    result: str = ""
    helped: bool | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
