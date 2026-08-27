from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from pex_protocol.enums import DecisionSource, DecisionStatus, Sensitivity


class Goal(BaseModel):
    id: str
    project_id: str
    title: str
    objective: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    forbidden_outcomes: list[str] = Field(default_factory=list)
    non_goals: list[str] = Field(default_factory=list)
    priority: int = 0
    deadline: datetime | None = None
    evidence_requirements: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    supersedes: str | None = None
    paused: bool = False


class Decision(BaseModel):
    id: str
    goal_id: str
    statement: str
    rationale: str = ""
    alternatives_rejected: list[str] = Field(default_factory=list)
    scope: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: DecisionSource = DecisionSource.HUMAN
    status: DecisionStatus = DecisionStatus.ACTIVE
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    sensitivity: Sensitivity = Sensitivity.INTERNAL
