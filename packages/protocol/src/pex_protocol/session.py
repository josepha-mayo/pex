from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from pex_protocol.enums import (
    EventPhase,
    EventType,
    HarnessType,
    SessionStatus,
)


class HarnessSession(BaseModel):
    id: str
    harness_type: HarnessType
    vendor_session_id: str
    project_id: str | None = None
    goal_id: str | None = None
    cwd: str | None = None
    repo: str | None = None
    branch: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    status: SessionStatus = SessionStatus.DISCOVERED
    context_health: float = Field(default=1.0, ge=0.0, le=1.0)
    last_activity: datetime | None = None
    capabilities: dict[str, Any] = Field(default_factory=dict)
    external_url: str | None = None
    local_window_id: str | None = None
    supervision_paused: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class HarnessEvent(BaseModel):
    event_id: str
    ts: datetime
    harness_type: HarnessType
    session_id: str
    project_id: str | None = None
    # Bound by Store.add_event from the live session at ingest time. Historical
    # rows without a goal remain readable but cannot serve as goal-scoped proof.
    goal_id: str | None = None
    event_type: EventType
    phase: EventPhase = EventPhase.DURING
    raw_event_ref: str | None = None
    message_delta: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    tool_output_ref: str | None = None
    command: str | None = None
    file_paths: list[str] = Field(default_factory=list)
    diff_ref: str | None = None
    approval_request: dict[str, Any] | None = None
    token_usage: dict[str, Any] | None = None
    cost: float | None = None
    process_state: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
