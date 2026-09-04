import ipaddress
import os
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOW_TEST_NO_AUTH: ContextVar[bool] = ContextVar(
    "pex_allow_test_no_auth",
    default=False,
)


def _scrub_operator_token_environment() -> None:
    for name in tuple(os.environ):
        if name.casefold() == "pex_token":
            os.environ.pop(name, None)


def normalize_loopback_host(value: str) -> str:
    host = value.strip()
    if host.casefold() == "localhost":
        return "localhost"
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("PEX bridge host must be localhost or a loopback IP address") from exc
    if not address.is_loopback:
        raise ValueError("PEX bridge host must be localhost or a loopback IP address")
    return address.compressed


def validate_bridge_token(value: str, *, label: str = "PEX bridge token") -> str:
    token = value.strip()
    if not 32 <= len(token) <= 512 or any(not 0x21 <= ord(char) <= 0x7E for char in token):
        raise ValueError(f"{label} must be 32-512 printable ASCII characters")
    return token


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PEX_", extra="ignore")

    host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    port: int = Field(default=7420, ge=1, le=65_535)
    home: Path = Field(default_factory=lambda: Path.home() / ".pex")
    autonomy: Literal["observe", "assist", "nudge", "manage", "autopilot"] = "manage"
    cloud_reasoning: bool = True
    require_auth: bool = True
    token: str | None = Field(default=None, max_length=512, repr=False, exclude=True)
    db_path: Path | None = None
    supervisor_mode: Literal["local", "agentcore", "hybrid"] = "local"
    agentcore_runtime_arn: str | None = Field(default=None, max_length=2048)
    agentcore_region: str | None = Field(default=None, max_length=64)
    agentcore_qualifier: str = "DEFAULT"
    agentcore_timeout_seconds: float = Field(default=25.0, gt=0.0, le=28.0)
    agentcore_max_request_bytes: int = Field(default=262_144, ge=1_024, le=1_048_576)
    agentcore_max_response_bytes: int = Field(default=1_048_576, ge=1_024, le=4_194_304)
    opencode_url: str | None = Field(default=None, max_length=2048)
    qwen_url: str | None = Field(default=None, max_length=2048)
    qwen_token: str | None = Field(default=None, max_length=4096)
    devin_url: str | None = Field(default=None, max_length=2048)
    devin_token: str | None = Field(default=None, max_length=4096)
    devin_org_id: str | None = Field(default=None, max_length=256)
    codex_bin: str | None = Field(default=None, max_length=4096)
    codex_attach: bool = False
    cursor_agent: str | None = Field(default=None, max_length=4096)
    cursor_attach: bool = False
    max_recent_events: int = Field(default=80, ge=1, le=500)
    suppress_routine_success: bool = True
    notify_file: bool = True

    @classmethod
    def for_test(
        cls,
        *,
        require_auth: Literal[False],
        **values: Any,
    ) -> "Settings":
        """Construct an explicitly test-scoped unauthenticated bridge config.

        The process-local gate exists only while this synchronous constructor is
        validating. Environment variables and release entrypoints cannot select it.
        Callers must also spell ``require_auth=False`` so no ambient PEX setting can
        silently turn an ordinary test fixture into an unauthenticated bridge.
        """

        if require_auth is not False:
            raise ValueError("test settings require require_auth=False")
        gate = _ALLOW_TEST_NO_AUTH.set(True)
        try:
            return cls(require_auth=False, **values)
        finally:
            _ALLOW_TEST_NO_AUTH.reset(gate)

    @model_validator(mode="after")
    def validate_supervisor_route(self) -> "Settings":
        self.host = normalize_loopback_host(self.host)
        if not self.require_auth and not _ALLOW_TEST_NO_AUTH.get():
            raise ValueError(
                "unauthenticated bridge settings are available only through "
                "Settings.for_test(require_auth=False, ...)"
            )
        if self.token is not None:
            configured_token = self.token.strip()
            self.token = validate_bridge_token(configured_token) if configured_token else None
        # BaseSettings has already copied a valid operator bearer into this model.
        # Remove the inherited source before any adapter or supervisor subprocess
        # can be created, including direct ASGI factory imports that bypass main().
        _scrub_operator_token_environment()
        if self.supervisor_mode in {"agentcore", "hybrid"}:
            if not self.cloud_reasoning:
                raise ValueError(
                    "PEX_CLOUD_REASONING=false cannot be combined with an AgentCore mode"
                )
            if not (self.agentcore_runtime_arn or "").strip():
                raise ValueError(
                    "PEX_AGENTCORE_RUNTIME_ARN is required when PEX_SUPERVISOR_MODE "
                    "is agentcore or hybrid"
                )
        qualifier = self.agentcore_qualifier.strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", qualifier):
            raise ValueError(
                "PEX_AGENTCORE_QUALIFIER must be a valid AgentCore endpoint name"
            )
        self.agentcore_qualifier = qualifier
        if self.agentcore_region is not None:
            self.agentcore_region = self.agentcore_region.strip() or None
        return self

    @property
    def data_dir(self) -> Path:
        self.home.mkdir(parents=True, exist_ok=True)
        return self.home

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path:
            return self.db_path
        return self.data_dir / "pex.sqlite"

    @property
    def token_path(self) -> Path:
        # Operator bearer lives in this owner-only file (and process memory).
        # Do not persist PEX_TOKEN in the process environment: workers inherit it.
        return self.data_dir / "bridge.token"
