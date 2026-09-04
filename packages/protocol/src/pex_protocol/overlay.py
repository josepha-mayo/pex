from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_OVERLAY_TTL_SECONDS = 86_400
OverlayName = Annotated[str, Field(min_length=1, max_length=512)]
_DEBUG_INSTRUCTIONS = {
    (
        "Stay on the failing reproduction. Do not start unrelated research. "
        "Preserve the failing state until the attached acceptance criteria move."
    ),
    (
        "Stay on the failing reproduction. Do not start unrelated research. "
        "Preserve the failing state until the attached acceptance criteria move. "
        "Do not treat a stop as done without the attached acceptance evidence."
    ),
}


class OverlayDiff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_instructions: str | None = Field(default=None, max_length=32_768)
    tools_enabled: list[OverlayName] | None = Field(default=None, max_length=256)
    tools_disabled: list[OverlayName] | None = Field(default=None, max_length=256)
    mcp_servers: dict[str, Any] | None = Field(default=None, max_length=128)
    model: str | None = Field(default=None, max_length=512)
    reasoning_effort: str | None = Field(default=None, max_length=128)
    permission_policy: dict[str, Any] | None = Field(default=None, max_length=256)
    extra: dict[str, Any] = Field(default_factory=dict, max_length=128)

    @field_validator("tools_enabled", "tools_disabled")
    @classmethod
    def validate_tool_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if len(value) != len(set(value)):
            raise ValueError("overlay tool names must be unique")
        for name in value:
            if name != name.strip() or any(ord(char) < 0x20 or ord(char) == 0x7F for char in name):
                raise ValueError("overlay tool names must be trimmed control-free text")
        return value

    @model_validator(mode="after")
    def require_an_actual_change(self) -> "OverlayDiff":
        values = self.model_dump(exclude={"extra"})
        if not any(value is not None for value in values.values()) and not self.extra:
            raise ValueError("overlay diff must contain at least one change")
        return self


class Overlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=512)
    session_id: str = Field(min_length=1, max_length=512)
    reason: str = Field(min_length=1, max_length=8192)
    diff: OverlayDiff
    ttl_seconds: int = Field(default=3600, gt=0, le=MAX_OVERLAY_TTL_SECONDS)
    scope: Literal["session"] = "session"
    applied_at: datetime | None = None
    expires_at: datetime | None = None
    reverted_at: datetime | None = None
    revert_reason: str | None = Field(default=None, max_length=8192)
    rollback: dict[str, Any] = Field(default_factory=dict, max_length=256)
    promoted: bool = False

    @field_validator("id", "session_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if value != value.strip() or any(
            ord(char) < 0x20 or ord(char) == 0x7F for char in value
        ):
            raise ValueError("overlay identifiers must be trimmed control-free text")
        return value

    @field_validator("reason", "revert_reason")
    @classmethod
    def validate_explanatory_text(cls, value: str | None) -> str | None:
        if value is not None and "\x00" in value:
            raise ValueError("overlay text cannot contain NUL bytes")
        return value

    @model_validator(mode="after")
    def derive_and_validate_lifecycle(self) -> "Overlay":
        if self.applied_at is None and self.expires_at is not None:
            raise ValueError("an unapplied overlay cannot have an expiry")
        if self.applied_at is None and self.reverted_at is not None:
            raise ValueError("an unapplied overlay cannot be reverted")
        if self.applied_at is not None and self.expires_at is None:
            self.expires_at = self.applied_at + timedelta(seconds=self.ttl_seconds)
        if (
            self.applied_at is not None
            and self.expires_at is not None
            and _as_utc(self.expires_at) <= _as_utc(self.applied_at)
        ):
            raise ValueError("overlay expiry must be after its applied timestamp")
        if (
            self.applied_at is not None
            and self.expires_at is not None
            and _as_utc(self.expires_at)
            > _as_utc(self.applied_at) + timedelta(seconds=self.ttl_seconds)
        ):
            raise ValueError("overlay expiry cannot exceed its bounded TTL")
        if (
            self.applied_at is not None
            and self.reverted_at is not None
            and _as_utc(self.reverted_at) < _as_utc(self.applied_at)
        ):
            raise ValueError("overlay cannot be reverted before it is applied")
        return self

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.promoted or self.applied_at is None or self.reverted_at is not None:
            return False
        expires_at = self.expires_at or self.applied_at + timedelta(seconds=self.ttl_seconds)
        return _as_utc(now or datetime.now(UTC)) >= _as_utc(expires_at)


def locally_proven_session_overlay(overlay: Overlay) -> bool:
    """Recognize only bounded, authority-nonexpanding bridge overlay profiles."""

    diff = overlay.diff
    if any(
        value is not None
        for value in (
            diff.tools_enabled,
            diff.mcp_servers,
            diff.model,
            diff.reasoning_effort,
            diff.permission_policy,
        )
    ):
        return False
    if set(diff.extra) - {"phase", "pin", "fingerprint_overlay"}:
        return False
    if any(
        not isinstance(value, str)
        or len(value) > 512
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
        for value in diff.extra.values()
    ):
        return False
    phase = str(diff.extra.get("phase") or "")
    pin = str(diff.extra.get("pin") or "")
    fingerprint = str(diff.extra.get("fingerprint_overlay") or "")
    if phase not in {"", "debug", "evidence-before-done", "context-health", "implementation"}:
        return False
    if fingerprint not in {"", "evidence-before-done"}:
        return False
    instructions = (diff.system_instructions or "").strip()
    if not instructions:
        return bool(diff.tools_disabled or phase or pin or fingerprint)
    if "\x00" in instructions or len(instructions) > 8192:
        return False
    if phase == "debug":
        return instructions in _DEBUG_INSTRUCTIONS
    if phase == "context-health":
        return (
            instructions.startswith("Persistent ledger '")
            and "Acceptance:" in instructions
            and instructions.endswith("Keep these facts in working context.")
        )
    if phase == "evidence-before-done":
        lowered = instructions.casefold()
        return "\n" not in instructions and any(
            marker in lowered
            for marker in ("acceptance", "evidence", "test", "verify", "verification")
        )
    return False


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
