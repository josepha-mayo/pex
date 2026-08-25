from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OverlayDiff(BaseModel):
    system_instructions: str | None = None
    tools_enabled: list[str] | None = None
    tools_disabled: list[str] | None = None
    mcp_servers: dict[str, Any] | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    permission_policy: dict[str, Any] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Overlay(BaseModel):
    id: str
    session_id: str
    reason: str
    diff: OverlayDiff
    ttl_seconds: int = 3600
    scope: str = "session"
    applied_at: datetime | None = None
    reverted_at: datetime | None = None
    rollback: dict[str, Any] = Field(default_factory=dict)
    promoted: bool = False
