"""Durable, secret-safe configuration for the PEX supervisor model.

The JSON control file contains routing facts only.  A pasted credential is kept
in the operating-system credential store and is addressed by an opaque local
reference that is never returned by the HTTP API.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_SUPERVISOR_CHOICE_BYTES = 16_384
MAX_SUPERVISOR_SECRET_CHARS = 16_384
_SECRET_REF = re.compile(r"sec_[a-f0-9]{32}\Z")


class SupervisorSecretStoreError(RuntimeError):
    """The OS credential store could not complete an operation safely."""


class SupervisorSecretStore(Protocol):
    """Minimal injectable secret-store contract used by config transactions."""

    def put(self, value: str, *, audience: str) -> str: ...

    def get(self, reference: str, *, audience: str) -> str | None: ...

    def delete(self, reference: str) -> None: ...


class KeyringSupervisorSecretStore:
    """Store supervisor credentials in the current user's OS keyring."""

    service_name = "PEX Supervisor"

    def _keyring(self) -> Any:
        try:
            import keyring
            from keyring.errors import KeyringError
        except ImportError as exc:  # pragma: no cover - packaging failure guard
            raise SupervisorSecretStoreError(
                "OS credential storage is unavailable in this build"
            ) from exc
        backend = keyring.get_keyring()
        module = type(backend).__module__
        allowed = (
            ("keyring.backends.Windows",)
            if os.name == "nt"
            else ("keyring.backends.macOS",)
            if sys.platform == "darwin"
            else (
                "keyring.backends.SecretService",
                "keyring.backends.kwallet",
            )
        )
        if not module.startswith(allowed):
            raise SupervisorSecretStoreError(
                "a supported operating-system credential backend is unavailable"
            )
        return keyring, KeyringError

    @staticmethod
    def _validate_reference(reference: str) -> str:
        if not _SECRET_REF.fullmatch(reference):
            raise SupervisorSecretStoreError("invalid supervisor secret reference")
        return reference

    def put(self, value: str, *, audience: str) -> str:
        secret = validate_supervisor_secret(value)
        audience = validate_secret_audience(audience)
        reference = f"sec_{secrets.token_hex(16)}"
        keyring, keyring_error = self._keyring()
        envelope = json.dumps(
            {"version": 1, "audience": audience, "secret": secret},
            separators=(",", ":"),
        )
        try:
            keyring.set_password(self.service_name, reference, envelope)
        except keyring_error as exc:
            raise SupervisorSecretStoreError(
                "the operating-system credential store rejected the supervisor key"
            ) from exc
        return reference

    def get(self, reference: str, *, audience: str) -> str | None:
        safe_reference = self._validate_reference(reference)
        audience = validate_secret_audience(audience)
        keyring, keyring_error = self._keyring()
        try:
            value = keyring.get_password(self.service_name, safe_reference)
        except keyring_error as exc:
            raise SupervisorSecretStoreError(
                "the operating-system credential store could not read the supervisor key"
            ) from exc
        if value is None:
            return None
        if len(value) > MAX_SUPERVISOR_SECRET_CHARS + 512:
            raise SupervisorSecretStoreError("invalid supervisor credential envelope")
        try:
            envelope = json.loads(value, object_pairs_hook=_unique_object)
            if set(envelope) != {"version", "audience", "secret"}:
                raise ValueError("unexpected credential envelope fields")
            if envelope["version"] != 1:
                raise ValueError("unsupported credential envelope version")
            stored_audience = envelope["audience"]
            secret = envelope["secret"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise SupervisorSecretStoreError("invalid supervisor credential envelope") from exc
        if not isinstance(stored_audience, str) or not secrets.compare_digest(
            stored_audience, audience
        ):
            raise SupervisorSecretStoreError("supervisor credential audience mismatch")
        return validate_supervisor_secret(secret)

    def delete(self, reference: str) -> None:
        safe_reference = self._validate_reference(reference)
        keyring, keyring_error = self._keyring()
        try:
            keyring.delete_password(self.service_name, safe_reference)
        except keyring_error as exc:
            # A missing entry is already the desired terminal state.  Backends do
            # not expose one portable missing-entry exception, so verify once.
            try:
                if keyring.get_password(self.service_name, safe_reference) is None:
                    return
            except keyring_error:
                pass
            raise SupervisorSecretStoreError(
                "the operating-system credential store could not delete the supervisor key"
            ) from exc


def validate_supervisor_secret(value: str) -> str:
    """Accept a bounded opaque token without normalizing its bytes."""

    if not isinstance(value, str):
        raise ValueError("api_key must be text")
    if not 1 <= len(value) <= MAX_SUPERVISOR_SECRET_CHARS:
        raise ValueError("api_key must be between 1 and 16384 characters")
    if any(char in value for char in ("\r", "\n", "\x00")):
        raise ValueError("api_key must be a single-line value")
    return value


def validate_secret_audience(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("invalid supervisor credential audience")
    return value


class SupervisorChoice(BaseModel):
    """Versioned routing snapshot safe to persist and expose after redaction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    revision: int = Field(default=1, ge=1, le=2_147_483_647)
    provider: str | None = Field(default=None, max_length=256)
    model_id: str | None = Field(default=None, max_length=512)
    auth_mode: Literal[
        "api_key", "login", "local", "custom", "bedrock", "agentcore"
    ] | None = None
    protocol: Literal["openai", "anthropic"] | None = None
    base_url: str | None = Field(default=None, max_length=2048)
    credential_source: Literal["none", "environment", "secret_store"] = "none"
    secret_ref: str | None = Field(default=None, max_length=64, repr=False)

    @field_validator("provider", "model_id", "base_url", mode="before")
    @classmethod
    def _canonical_optional_text(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("configuration values must be text")
        if value != value.strip() or any(char in value for char in ("\r", "\n", "\x00")):
            raise ValueError("configuration values must be canonical single-line text")
        return value or None

    @field_validator("provider")
    @classmethod
    def _canonical_provider(cls, value: str | None) -> str | None:
        return value.casefold() if value else None

    @field_validator("secret_ref")
    @classmethod
    def _opaque_reference(cls, value: str | None) -> str | None:
        if value is not None and not _SECRET_REF.fullmatch(value):
            raise ValueError("invalid supervisor secret reference")
        return value

    @model_validator(mode="after")
    def _coherent_secret_source(self) -> SupervisorChoice:
        if (self.credential_source == "secret_store") != (self.secret_ref is not None):
            raise ValueError("secret_store credential source requires exactly one secret reference")
        return self

    def public_dict(self, *, has_api_key: bool) -> dict[str, Any]:
        data = self.model_dump(exclude={"secret_ref"})
        data["has_api_key"] = has_api_key
        data["credential_configured"] = self.credential_source != "none"
        return data

    def audience(self) -> tuple[str | None, str | None, str | None, str | None]:
        """Return the routing identity to which a stored credential is bound."""

        return (self.provider, self.auth_mode, self.protocol, self.base_url)

    def credential_audience(self) -> str:
        payload = json.dumps(self.audience(), separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_supervisor_choice(path: Path) -> SupervisorChoice | None:
    if not path.is_file():
        return None
    if path.is_symlink():
        raise ValueError("supervisor choice file must not be a symbolic link")
    with path.open("rb") as handle:
        raw = handle.read(MAX_SUPERVISOR_CHOICE_BYTES + 1)
    if len(raw) > MAX_SUPERVISOR_CHOICE_BYTES:
        raise ValueError("supervisor choice file exceeds its safety bound")
    try:
        text = raw.decode("utf-8")
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant {value!r} is not allowed")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("supervisor choice file must contain strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("supervisor choice file must contain an object")
    # Migrate the original provider/model-only snapshot without inventing a key.
    if "version" not in payload and set(payload) <= {"provider", "model_id"}:
        payload = {
            "version": 1,
            "revision": 1,
            **payload,
            "credential_source": "environment",
        }
    return SupervisorChoice.model_validate(payload)


def save_supervisor_choice(path: Path, choice: SupervisorChoice) -> None:
    """Durably replace the routing snapshot with user-only permissions on POSIX."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    payload = choice.model_dump_json(indent=2, exclude_none=False) + "\n"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "KeyringSupervisorSecretStore",
    "MAX_SUPERVISOR_CHOICE_BYTES",
    "MAX_SUPERVISOR_SECRET_CHARS",
    "SupervisorChoice",
    "SupervisorSecretStore",
    "SupervisorSecretStoreError",
    "load_supervisor_choice",
    "save_supervisor_choice",
    "validate_supervisor_secret",
    "validate_secret_audience",
]
