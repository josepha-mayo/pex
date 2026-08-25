from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from pex_protocol.enums import ContextKind, Sensitivity, SourceKind


class ContextItem(BaseModel):
    id: str
    project_id: str
    goal_id: str | None = None
    kind: ContextKind
    content: str
    source_refs: list[str] = Field(default_factory=list)
    provenance: SourceKind = SourceKind.PEX
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    relevance_tags: list[str] = Field(default_factory=list)
    valid_from: datetime
    stale_after: datetime | None = None
    supersedes: str | None = None
    sensitivity: Sensitivity = Sensitivity.INTERNAL
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextBundle(BaseModel):
    goal_id: str
    target_session_id: str
    source_session_ids: list[str] = Field(default_factory=list)
    goal_summary: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    critical_decisions: list[str] = Field(default_factory=list)
    relevant_artifacts: list[str] = Field(default_factory=list)
    direct_evidence: list[str] = Field(default_factory=list)
    recent_progress: list[str] = Field(default_factory=list)
    next_objective: str = ""
    do_not_redo: list[str] = Field(default_factory=list)
    deep_links: list[str] = Field(default_factory=list)
    items: list[ContextItem] = Field(default_factory=list)
    token_estimate: int = 0
    created_at: datetime
