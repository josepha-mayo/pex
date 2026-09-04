"""Durable, fail-closed accounting for potentially billable hatch effects.

The hatch registry deliberately owns a separate SQLite database instead of using
the bridge event store.  A hatch image request is an external, potentially
billable effect and must be reserved durably before it can be dispatched.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import secrets
import sqlite3
import stat
import unicodedata
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

JOBS_TOTAL = 1
MAX_HATCH_RECORD_BYTES = 65_536
MAX_HATCH_JOBS = 1_000
DISPATCH_GRACE_SECONDS = 60.0
MIN_DISPATCH_WINDOW_SECONDS = 180.0
MAX_AUTHORIZATION_LIFETIME_SECONDS = 15 * 60
MAX_AUTHORIZATION_CLOCK_SKEW_SECONDS = 30
MAX_CANDIDATE_RECEIPT_BYTES = 16_384
MAX_BASE_PROMPT_BYTES = 32_768

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_PROCESS_BOOT_ID = secrets.token_hex(32)
_TERMINAL_EFFECT_STATES = frozenset(
    {"delivered", "failed", "delivery_uncertain", "skipped"}
)


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(callable(is_junction) and is_junction())


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_existing_regular_file(path: Path, *, label: str) -> None:
    """Validate one filesystem snapshot while allowing a concurrently removed file."""

    try:
        snapshot = path.lstat()
    except FileNotFoundError:
        return
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(snapshot, "st_file_attributes", 0)
    if (
        not stat.S_ISREG(snapshot.st_mode)
        or stat.S_ISLNK(snapshot.st_mode)
        or bool(reparse_flag and file_attributes & reparse_flag)
    ):
        raise HatchAuthorizationError(f"{label} is unsafe")


def _assert_contained_without_links(root: Path, target: Path) -> Path:
    """Validate target syntax and every existing component at or below root."""

    root_absolute = _absolute_path(root)
    target_absolute = _absolute_path(target)
    try:
        relative = target_absolute.relative_to(root_absolute)
    except ValueError as exc:
        raise HatchAuthorizationError("hatch artifact path escaped its root") from exc
    if not root_absolute.exists() or not root_absolute.is_dir():
        raise HatchAuthorizationError("hatch artifact root is unavailable")
    if _is_link_or_junction(root_absolute):
        raise HatchAuthorizationError("hatch artifact root cannot be a link or junction")
    current = root_absolute
    for component in relative.parts:
        if component in {"", ".", ".."}:
            raise HatchAuthorizationError("hatch artifact path is invalid")
        current /= component
        if _is_link_or_junction(current):
            raise HatchAuthorizationError(
                "hatch artifact path cannot contain a link or junction"
            )
    return target_absolute


def prepare_hatch_artifact_dirs(
    root: Path, job_id: str, *, require_empty: bool = False
) -> Path:
    """Create and verify the only directories/files used by a hatch dispatch."""

    if not _SAFE_COMPONENT.fullmatch(job_id):
        raise HatchAuthorizationError("invalid hatch job id")
    root.mkdir(parents=True, exist_ok=True)
    job_dir = _assert_contained_without_links(root, root / job_id)
    if job_dir.exists() and not job_dir.is_dir():
        raise HatchAuthorizationError("hatch job artifact path is not a directory")
    job_dir.mkdir(exist_ok=True)
    _assert_contained_without_links(root, job_dir)
    for name in ("decoded", "references"):
        directory = _assert_contained_without_links(root, job_dir / name)
        if directory.exists() and not directory.is_dir():
            raise HatchAuthorizationError("hatch artifact directory is invalid")
        directory.mkdir(exist_ok=True)
        _assert_contained_without_links(root, directory)
    expected_files = (
        job_dir / "decoded" / "base.png",
        job_dir / "references" / "canonical-base.png",
        job_dir / "candidate-receipt.json",
    )
    for path in expected_files:
        _assert_contained_without_links(root, path)
        if _is_link_or_junction(path) or (path.exists() and not path.is_file()):
            raise HatchAuthorizationError("hatch artifact file is invalid")
        if require_empty and path.exists():
            raise HatchAuthorizationError(
                "pre-existing hatch artifacts require operator reconciliation"
            )
    return job_dir


class HatchConflictError(ValueError):
    """An idempotency, request, provider, or authorization binding conflicts."""


class HatchAuthorizationError(ValueError):
    """A billable hatch effect lacks a valid, exact authorization."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_id(prefix: str, domain: str, parts: list[Any]) -> str:
    """Hash a canonical tuple; never create identities by joining delimiters."""

    return f"{prefix}{_sha256(_canonical_json([domain, *parts]))}"


def _utcnow_datetime() -> datetime:
    return datetime.now(UTC)


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("invalid timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _bounded_text(value: str, *, name: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized or len(normalized.encode("utf-8")) > maximum:
        raise ValueError(f"invalid {name}")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise ValueError(f"invalid {name}")
    return normalized


def _safe_provider_binding(config: Mapping[str, Any]) -> dict[str, Any]:
    """Return a secret-free exact provider binding for hashing and persistence."""

    if not isinstance(config, Mapping):
        raise HatchAuthorizationError("image provider configuration is invalid")
    try:
        raw_provider = config["provider"]
        raw_model = config["model_id"]
        raw_endpoint = config["base_url"]
        if not all(
            isinstance(value, str)
            for value in (raw_provider, raw_model, raw_endpoint)
        ):
            raise ValueError("provider binding fields must be text")
        if any(
            unicodedata.normalize("NFKC", value.strip()) != value.strip()
            for value in (raw_provider, raw_model, raw_endpoint)
        ):
            raise ValueError("provider binding fields must already be canonical")
        provider = _bounded_text(raw_provider, name="provider", maximum=256)
        model_id = _bounded_text(raw_model, name="model", maximum=256)
        base_url_raw = _bounded_text(
            raw_endpoint, name="provider endpoint", maximum=2_048
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HatchAuthorizationError("image provider configuration is invalid") from exc

    try:
        if "\\" in base_url_raw or "%" in base_url_raw:
            raise ValueError("ambiguous endpoint spelling")
        parsed = urlsplit(base_url_raw)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.netloc.endswith(":")
        ):
            raise ValueError("invalid endpoint shape")
        port = parsed.port
        if port is not None and not 1 <= port <= 65_535:
            raise ValueError("invalid endpoint port")
    except ValueError as exc:
        raise HatchAuthorizationError("image provider configuration is invalid") from exc

    raw_host = parsed.hostname
    try:
        parsed_ip = ipaddress.ip_address(raw_host)
        host = str(parsed_ip).lower()
        if raw_host.lower() != host:
            raise ValueError("noncanonical IP address")
    except ValueError as ip_error:
        if "noncanonical" in str(ip_error):
            raise HatchAuthorizationError(
                "image provider configuration is invalid"
            ) from ip_error
        try:
            raw_host.encode("ascii")
        except UnicodeEncodeError as exc:
            raise HatchAuthorizationError(
                "image provider configuration is invalid"
            ) from exc
        host = raw_host.lower()
        labels = host.split(".")
        if (
            len(host) > 253
            or host.endswith(".")
            or ".." in host
            or bool(re.fullmatch(r"[0-9.]+", host))
            or bool(re.fullmatch(r"0x[0-9a-f]+", host))
            or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in labels
            )
        ):
            raise HatchAuthorizationError(
                "image provider configuration is invalid"
            ) from ip_error

    if ":" in host and not parsed.netloc.startswith("["):
        raise HatchAuthorizationError("image provider configuration is invalid")
    port_text: str | None = None
    if parsed.netloc.startswith("["):
        close = parsed.netloc.find("]")
        suffix = parsed.netloc[close + 1 :] if close >= 0 else "invalid"
        if close < 0 or suffix not in {"", f":{port}"}:
            raise HatchAuthorizationError("image provider configuration is invalid")
        if suffix.startswith(":"):
            port_text = suffix[1:]
    elif ":" in parsed.netloc:
        _, port_text = parsed.netloc.rsplit(":", 1)
    if port_text is not None and (
        not port_text.isascii() or not port_text.isdigit() or str(port) != port_text
    ):
        raise HatchAuthorizationError("image provider configuration is invalid")
    if (parsed.scheme == "https" and port == 443) or (
        parsed.scheme == "http" and port == 80
    ):
        raise HatchAuthorizationError("image provider configuration is invalid")

    path = parsed.path
    if path.endswith("//"):
        raise HatchAuthorizationError("image provider configuration is invalid")
    if path.endswith("/") and path != "/":
        path = path[:-1]
    if path in {"", "/"}:
        path = ""
    else:
        if not re.fullmatch(r"(?:/[A-Za-z0-9._~-]+)*", path):
            raise HatchAuthorizationError("image provider configuration is invalid")
        segments = path.split("/")[1:]
        if (
            any(segment in {"", ".", ".."} for segment in segments)
            or path.lower().endswith(("/images/generations", "/images/edits"))
        ):
            raise HatchAuthorizationError("image provider configuration is invalid")
    if host == "api.openai.com" and (
        parsed.scheme != "https" or port is not None or path != "/v1"
    ):
        raise HatchAuthorizationError("image provider configuration is invalid")
    if parsed.scheme == "http" and host not in {"127.0.0.1", "::1"}:
        raise HatchAuthorizationError("image provider configuration is invalid")

    display_host = f"[{host}]" if ":" in host else host
    netloc = display_host if port is None else f"{display_host}:{port}"
    endpoint = urlunsplit((parsed.scheme, netloc, path, "", ""))

    raw_key = config.get("api_key")
    if raw_key is not None:
        if not isinstance(raw_key, str):
            raise HatchAuthorizationError("image provider configuration is invalid")
        cleaned_key = raw_key.strip()
        if (
            not cleaned_key
            or len(cleaned_key.encode("utf-8")) > 16_384
            or any(char in cleaned_key for char in ("\r", "\n", "\x00"))
        ):
            raise HatchAuthorizationError("image provider configuration is invalid")
    credential_present = bool(raw_key)
    if provider == "hatch":
        credential_scope = "explicit_hatch_endpoint"
    elif endpoint == "https://api.openai.com/v1":
        credential_scope = "canonical_openai_endpoint"
    else:
        credential_scope = "provider_scoped_configuration"
    try:
        timeout = float(config.get("timeout", 90.0))
    except (TypeError, ValueError, OverflowError) as exc:
        raise HatchAuthorizationError("image provider configuration is invalid") from exc
    if not math.isfinite(timeout):
        raise HatchAuthorizationError("image provider configuration is invalid")
    timeout = min(120.0, max(1.0, timeout))

    return {
        "provider": provider,
        "endpoint": endpoint,
        "model_id": model_id,
        "credential_present": credential_present,
        "credential_scope": credential_scope,
        "timeout_seconds": timeout,
    }


class HatchJob(BaseModel):
    """Public hatch projection; a delivered result is still only candidate art."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_SAFE_COMPONENT.pattern)
    pet_id: str = Field(pattern=_SAFE_COMPONENT.pattern)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(max_length=4096)
    style_preset: str = Field(default="plush", min_length=1, max_length=64)
    pet_notes: str = Field(default="", max_length=8192)
    status: Literal[
        "queued",
        "probing",
        "running",
        "needs_authorization",
        "awaiting_assembly_qa",
        "delivery_uncertain",
        "failed",
        "interrupted",
        "complete",
    ] = "queued"
    step: str = Field(default="Getting pet ready.", max_length=1024)
    jobs_complete: int = Field(default=0, ge=0, le=JOBS_TOTAL)
    jobs_total: int = Field(default=JOBS_TOTAL, ge=JOBS_TOTAL, le=JOBS_TOTAL)
    error: str | None = Field(default=None, max_length=4096)
    spritesheet: str | None = Field(default=None, max_length=4096)
    image_backend: str | None = Field(default=None, max_length=256)
    image_model: str | None = Field(default=None, max_length=256)
    paid_generation_acknowledged: bool = False
    created_at: str = Field(
        default_factory=lambda: _format_utc(_utcnow_datetime()), max_length=64
    )
    updated_at: str = Field(
        default_factory=lambda: _format_utc(_utcnow_datetime()), max_length=64
    )
    request_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    provider_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    request_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    effect_id: str | None = Field(default=None, pattern=r"^effect_[0-9a-f]{64}$")
    effect_status: Literal[
        "reserved",
        "dispatching",
        "delivered",
        "failed",
        "delivery_uncertain",
        "skipped",
    ] | None = None
    candidate_asset: str | None = Field(default=None, max_length=4096)
    candidate_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    authorization_expires_at: str | None = Field(default=None, max_length=64)
    possible_duplicate_acknowledged: bool = False

    def public(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class HatchAuthorization(BaseModel):
    """Exact authorization for one provider call and no playable-pet claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authorization_id: str = Field(pattern=r"^hauth_[0-9a-f]{64}$")
    principal: str = Field(min_length=1, max_length=256, repr=False)
    idempotency_key: str = Field(
        min_length=16,
        max_length=128,
        pattern=_IDEMPOTENCY_KEY.pattern,
        repr=False,
    )
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1, max_length=256)
    endpoint: str = Field(min_length=1, max_length=2048)
    model_id: str = Field(min_length=1, max_length=256)
    credential_present: bool
    credential_scope: Literal[
        "explicit_hatch_endpoint",
        "canonical_openai_endpoint",
        "provider_scoped_configuration",
    ]
    provider_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_calls: Literal[1] = 1
    issued_at: str = Field(max_length=64)
    expires_at: str = Field(max_length=64)
    acknowledge_possible_duplicate: bool = False
    duplicate_risk_job_id: str | None = Field(
        default=None, pattern=_SAFE_COMPONENT.pattern
    )
    duplicate_risk_effect_id: str | None = Field(
        default=None, pattern=r"^effect_[0-9a-f]{64}$"
    )

    @field_validator("principal", "idempotency_key")
    @classmethod
    def _normalize_identity(cls, value: str, info: Any) -> str:
        maximum = 128 if info.field_name == "idempotency_key" else 256
        normalized = _bounded_text(value, name=info.field_name, maximum=maximum)
        if info.field_name == "idempotency_key" and (
            normalized != value or not _IDEMPOTENCY_KEY.fullmatch(normalized)
        ):
            raise ValueError("invalid idempotency_key")
        return normalized

    @model_validator(mode="after")
    def _validate_exact_binding(self) -> HatchAuthorization:
        binding = {
            "provider": self.provider,
            "endpoint": self.endpoint,
            "model_id": self.model_id,
            "credential_present": self.credential_present,
            "credential_scope": self.credential_scope,
        }
        expected_provider = _sha256(
            _canonical_json(["pex.hatch.provider.v1", binding])
        )
        if self.provider_fingerprint != expected_provider:
            raise ValueError("provider fingerprint does not match authorization fields")
        if self.acknowledge_possible_duplicate:
            if not self.duplicate_risk_job_id or not self.duplicate_risk_effect_id:
                raise ValueError("duplicate-risk acknowledgement must bind a prior effect")
        elif self.duplicate_risk_job_id or self.duplicate_risk_effect_id:
            raise ValueError("duplicate-risk binding requires explicit acknowledgement")
        issued = _parse_utc(self.issued_at)
        expires = _parse_utc(self.expires_at)
        if expires <= issued:
            raise ValueError("authorization expiry must be after issue time")
        if (expires - issued).total_seconds() > MAX_AUTHORIZATION_LIFETIME_SECONDS:
            raise ValueError("authorization lifetime exceeds the 15 minute maximum")
        expected_id = _stable_id(
            "hauth_",
            "pex.hatch.authorization.v1",
            [
                self.principal,
                self.idempotency_key,
                self.request_hash,
                self.provider_fingerprint,
                self.request_fingerprint,
                self.max_calls,
                self.issued_at,
                self.expires_at,
                self.acknowledge_possible_duplicate,
                self.duplicate_risk_job_id,
                self.duplicate_risk_effect_id,
            ],
        )
        if self.authorization_id != expected_id:
            raise ValueError("authorization id does not match its canonical fields")
        return self


class HatchEffect(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    effect_id: str = Field(pattern=r"^effect_[0-9a-f]{64}$")
    job_id: str = Field(pattern=_SAFE_COMPONENT.pattern)
    state: Literal[
        "reserved",
        "dispatching",
        "delivered",
        "failed",
        "delivery_uncertain",
        "skipped",
    ]
    attempt_count: int = Field(ge=0, le=1)
    dispatch_token: str | None = Field(default=None, max_length=128, repr=False)
    dispatch_deadline_at: str | None = Field(default=None, max_length=64)
    intended_asset: str = Field(max_length=4096)
    asset_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    asset_bytes: int | None = Field(default=None, ge=1, le=25 * 1024 * 1024)
    last_error_code: str | None = Field(default=None, max_length=256)


class HatchCandidateReceipt(BaseModel):
    """Strict local provenance required before an effect can become delivered."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_: Literal["pex.hatch.base-candidate-receipt.v1"] = Field(alias="schema")
    job_id: str = Field(pattern=_SAFE_COMPONENT.pattern)
    effect_id: str = Field(pattern=r"^effect_[0-9a-f]{64}$")
    result_state: Literal["base_candidate_persisted"]
    request_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset: str = Field(min_length=1, max_length=4096)
    asset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_bytes: int = Field(ge=1, le=25 * 1024 * 1024)
    playable_pet: Literal[False]
    qa_status: Literal["awaiting_grounded_assembly_and_independent_qa"]


class DispatchClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claimed: bool
    reason: Literal[
        "claimed",
        "already_terminal",
        "already_dispatching",
        "global_dispatch_busy",
        "not_reserved",
        "authorization_expired",
        "provider_mismatch",
    ]
    job: HatchJob
    effect: HatchEffect | None


class _LegacyHatchJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_SAFE_COMPONENT.pattern)
    pet_id: str = Field(pattern=_SAFE_COMPONENT.pattern)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=4096)
    style_preset: str = Field(default="plush", min_length=1, max_length=64)
    pet_notes: str = Field(default="", max_length=8192)
    status: str = Field(default="queued", max_length=64)
    step: str = Field(default="Getting pet ready.", max_length=1024)
    jobs_complete: int = Field(default=0, ge=0, le=64)
    jobs_total: int = Field(default=13, ge=1, le=64)
    error: str | None = Field(default=None, max_length=4096)
    spritesheet: str | None = Field(default=None, max_length=4096)
    image_backend: str | None = Field(default=None, max_length=256)
    image_model: str | None = Field(default=None, max_length=256)
    paid_generation_acknowledged: bool = False
    created_at: str = Field(
        default_factory=lambda: _format_utc(_utcnow_datetime()), max_length=64
    )
    updated_at: str = Field(
        default_factory=lambda: _format_utc(_utcnow_datetime()), max_length=64
    )


def hatch_request_hash(job: HatchJob) -> str:
    payload = {
        "pet_id": job.pet_id,
        "display_name": job.display_name,
        "description": job.description,
        "style_preset": job.style_preset,
        "pet_notes": job.pet_notes,
        "output_contract": "unverified_base_candidate_only",
    }
    return _sha256(_canonical_json(["pex.hatch.pet-request.v1", payload]))


def base_candidate_prompt(job: HatchJob) -> str:
    identity = job.pet_notes or job.description
    return (
        "One centered full-body pet on a flat #00FF55 chroma-key background. "
        "No scenery, shadows, floor, text, labels, grids, atlas, contact sheet, "
        "or detached effects. This is one unverified base identity candidate only, "
        "not an animation row or playable pet. "
        f"Style `{job.style_preset}`. Identity: {identity} "
        f"Named {job.display_name}. Compact whole-body mascot readable at 192x208."
    )


def _provider_fingerprint(binding: Mapping[str, Any]) -> str:
    public = {
        "provider": binding["provider"],
        "endpoint": binding["endpoint"],
        "model_id": binding["model_id"],
        "credential_present": binding["credential_present"],
        "credential_scope": binding["credential_scope"],
    }
    return _sha256(_canonical_json(["pex.hatch.provider.v1", public]))


def _generate_request_fingerprint(job: HatchJob, provider_fingerprint: str) -> str:
    prompt = base_candidate_prompt(job)
    if len(prompt.encode("utf-8")) > MAX_BASE_PROMPT_BYTES:
        raise HatchAuthorizationError("base candidate prompt exceeds the 32 KiB limit")
    request = {
        "provider_fingerprint": provider_fingerprint,
        "path": "/images/generations",
        "model_binding": "provider_fingerprint",
        "prompt": prompt,
        "size": "1024x1024",
        "n": 1,
        "response_format": "b64_json",
    }
    return _sha256(_canonical_json(["pex.hatch.generate-request.v1", request]))


def authorize_hatch(
    job: HatchJob,
    *,
    principal: str,
    idempotency_key: str,
    config: Mapping[str, Any],
    expires_at: datetime | str,
    acknowledge_possible_duplicate: bool = False,
    duplicate_risk_job_id: str | None = None,
    duplicate_risk_effect_id: str | None = None,
    issued_at: datetime | str | None = None,
) -> HatchAuthorization:
    """Create a secret-free, exact one-call authorization for ``job``."""

    binding = _safe_provider_binding(config)
    provider_fingerprint = _provider_fingerprint(binding)
    request_hash = hatch_request_hash(job)
    request_fingerprint = _generate_request_fingerprint(job, provider_fingerprint)
    issued_value = issued_at or _utcnow_datetime()
    issued_text = (
        _format_utc(issued_value)
        if isinstance(issued_value, datetime)
        else _format_utc(_parse_utc(issued_value))
    )
    expires_text = (
        _format_utc(expires_at)
        if isinstance(expires_at, datetime)
        else _format_utc(_parse_utc(expires_at))
    )
    try:
        normalized_principal = _bounded_text(
            principal,
            name="principal",
            maximum=256,
        )
        normalized_key = _bounded_text(
            idempotency_key,
            name="idempotency_key",
            maximum=128,
        )
    except ValueError as exc:
        raise HatchAuthorizationError(str(exc)) from exc
    if normalized_key != idempotency_key or not _IDEMPOTENCY_KEY.fullmatch(
        normalized_key
    ):
        raise HatchAuthorizationError("invalid idempotency_key")
    parts = [
        normalized_principal,
        normalized_key,
        request_hash,
        provider_fingerprint,
        request_fingerprint,
        1,
        issued_text,
        expires_text,
        acknowledge_possible_duplicate,
        duplicate_risk_job_id,
        duplicate_risk_effect_id,
    ]
    return HatchAuthorization(
        authorization_id=_stable_id(
            "hauth_", "pex.hatch.authorization.v1", parts
        ),
        principal=normalized_principal,
        idempotency_key=normalized_key,
        request_hash=request_hash,
        provider=binding["provider"],
        endpoint=binding["endpoint"],
        model_id=binding["model_id"],
        credential_present=binding["credential_present"],
        credential_scope=binding["credential_scope"],
        provider_fingerprint=provider_fingerprint,
        request_fingerprint=request_fingerprint,
        issued_at=issued_text,
        expires_at=expires_text,
        acknowledge_possible_duplicate=acknowledge_possible_duplicate,
        duplicate_risk_job_id=duplicate_risk_job_id,
        duplicate_risk_effect_id=duplicate_risk_effect_id,
    )


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


class HatchRegistry:
    """SQLite-backed hatch job/effect registry safe across processes and threads."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] = _utcnow_datetime,
        process_boot_id: str | None = None,
    ) -> None:
        root_absolute = _absolute_path(root)
        if root_absolute.exists() and _is_link_or_junction(root_absolute):
            raise HatchAuthorizationError(
                "hatch artifact root cannot be a link or junction"
            )
        root_absolute.mkdir(parents=True, exist_ok=True)
        _assert_contained_without_links(root_absolute, root_absolute)
        self.root = root_absolute
        self.db_path = self.root / "hatch.sqlite3"
        self._clock = clock
        self._boot_id = process_boot_id or _PROCESS_BOOT_ID
        self._pid = os.getpid()
        self._initialize_schema()
        self._import_legacy_records()
        self.reconcile_persisted_assets()
        self.recover_expired_dispatches()

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("hatch registry clock must be timezone-aware")
        return value.astimezone(UTC)

    def _path(self, job_id: str) -> Path:
        """Legacy record path helper retained only for validation/inspection."""

        if not _SAFE_COMPONENT.fullmatch(job_id):
            raise ValueError("invalid hatch job id")
        return self.root / f"{job_id}.json"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        for candidate in (
            self.db_path,
            Path(f"{self.db_path}-wal"),
            Path(f"{self.db_path}-shm"),
        ):
            _assert_contained_without_links(self.root, candidate)
            _assert_existing_regular_file(candidate, label="hatch database path")
        connection = sqlite3.connect(
            self.db_path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS hatch_schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                INSERT OR IGNORE INTO hatch_schema_meta(key, value)
                VALUES ('schema_version', '1');

                CREATE TABLE IF NOT EXISTS hatch_jobs (
                    id TEXT PRIMARY KEY,
                    pet_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    description TEXT NOT NULL,
                    style_preset TEXT NOT NULL,
                    pet_notes TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step TEXT NOT NULL,
                    jobs_complete INTEGER NOT NULL CHECK (jobs_complete BETWEEN 0 AND 1),
                    jobs_total INTEGER NOT NULL CHECK (jobs_total = 1),
                    error TEXT,
                    spritesheet TEXT,
                    image_backend TEXT,
                    image_model TEXT,
                    paid_generation_acknowledged INTEGER NOT NULL
                        CHECK (paid_generation_acknowledged IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    legacy_source TEXT
                );

                CREATE TABLE IF NOT EXISTS hatch_authorizations (
                    authorization_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE REFERENCES hatch_jobs(id) ON DELETE CASCADE,
                    principal TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    model_id TEXT NOT NULL,
                    credential_present INTEGER NOT NULL CHECK (credential_present IN (0, 1)),
                    credential_scope TEXT NOT NULL,
                    provider_fingerprint TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    max_calls INTEGER NOT NULL CHECK (max_calls = 1),
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    acknowledge_possible_duplicate INTEGER NOT NULL
                        CHECK (acknowledge_possible_duplicate IN (0, 1)),
                    duplicate_risk_job_id TEXT,
                    duplicate_risk_effect_id TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(principal, idempotency_key)
                );

                CREATE TABLE IF NOT EXISTS hatch_effects (
                    effect_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE REFERENCES hatch_jobs(id) ON DELETE CASCADE,
                    effect_key TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (
                        state IN (
                            'reserved', 'dispatching', 'delivered', 'failed',
                            'delivery_uncertain', 'skipped'
                        )
                    ),
                    provider_fingerprint TEXT NOT NULL,
                    request_fingerprint TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL CHECK (attempt_count BETWEEN 0 AND 1),
                    owner_boot_id TEXT,
                    owner_pid INTEGER,
                    dispatch_token TEXT,
                    dispatch_started_at TEXT,
                    dispatch_deadline_at TEXT,
                    intended_asset TEXT NOT NULL,
                    asset_sha256 TEXT,
                    asset_bytes INTEGER,
                    last_error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(job_id, effect_key)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS hatch_one_global_dispatch
                ON hatch_effects((1)) WHERE state = 'dispatching';

                CREATE INDEX IF NOT EXISTS hatch_uncertain_request
                ON hatch_authorizations(principal, request_hash);

                CREATE TABLE IF NOT EXISTS hatch_legacy_imports (
                    source_name TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    outcome TEXT NOT NULL,
                    reason_code TEXT NOT NULL,
                    imported_job_id TEXT,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY(source_name, content_sha256)
                );
                """
            )

    @staticmethod
    def _job_insert_values(job: HatchJob, *, legacy_source: str | None) -> tuple[Any, ...]:
        return (
            job.id,
            job.pet_id,
            job.display_name,
            job.description,
            job.style_preset,
            job.pet_notes,
            job.status,
            job.step,
            job.jobs_complete,
            job.jobs_total,
            job.error,
            job.spritesheet,
            job.image_backend,
            job.image_model,
            int(job.paid_generation_acknowledged),
            job.created_at,
            job.updated_at,
            legacy_source,
        )

    @staticmethod
    def _insert_job(
        connection: sqlite3.Connection,
        job: HatchJob,
        *,
        legacy_source: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO hatch_jobs(
                id, pet_id, display_name, description, style_preset, pet_notes,
                status, step, jobs_complete, jobs_total, error, spritesheet,
                image_backend, image_model, paid_generation_acknowledged,
                created_at, updated_at, legacy_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            HatchRegistry._job_insert_values(job, legacy_source=legacy_source),
        )

    def _import_legacy_records(self) -> None:
        for path in sorted(self.root.glob("*.json")):
            self._import_legacy_record(path)

    def _import_legacy_record(self, path: Path) -> None:
        reason = "ok"
        raw = b""
        try:
            _assert_contained_without_links(self.root, path)
            if _is_link_or_junction(path) or not path.is_file():
                reason = "unsafe_file_type"
                metadata = path.lstat()
                raw = _canonical_json([path.name, metadata.st_size, metadata.st_mode])
            else:
                size = path.stat().st_size
                if size > MAX_HATCH_RECORD_BYTES:
                    reason = "record_too_large"
                    raw = _canonical_json([path.name, size, path.stat().st_mtime_ns])
                else:
                    raw = path.read_bytes()
                    if len(raw) > MAX_HATCH_RECORD_BYTES:
                        reason = "record_too_large"
        except (HatchAuthorizationError, OSError) as exc:
            reason = "unsafe_or_unreadable_record"
            raw = _canonical_json([path.name, type(exc).__name__])
        content_sha = _sha256(raw)
        with self._connect() as connection:
            exists = connection.execute(
                """
                SELECT 1 FROM hatch_legacy_imports
                WHERE source_name = ? AND content_sha256 = ?
                """,
                (path.name, content_sha),
            ).fetchone()
        if exists is not None:
            return

        legacy: _LegacyHatchJob | None = None
        if reason == "ok":
            try:
                decoded = json.loads(
                    raw.decode("utf-8"),
                    parse_constant=_reject_json_constant,
                    object_pairs_hook=_unique_json_object,
                )
                legacy = _LegacyHatchJob.model_validate(decoded)
                if legacy.id != path.stem:
                    reason = "job_id_path_mismatch"
                    legacy = None
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                reason = "invalid_record"

        now = _format_utc(self._now())
        if legacy is None:
            job_id = _stable_id(
                "legacy_corrupt_",
                "pex.hatch.legacy-corrupt.v1",
                [path.name, content_sha, reason],
            )[:80]
            job = HatchJob(
                id=job_id,
                pet_id="legacy-corrupt",
                display_name="Corrupt legacy hatch record",
                description="A legacy hatch record could not be imported safely.",
                status="failed",
                step="Legacy hatch record requires operator review.",
                error=f"Legacy hatch import failed ({reason}).",
                created_at=now,
                updated_at=now,
            )
            outcome = "corrupt_visible"
        else:
            job = self._map_legacy_job(legacy, now=now)
            job_id = job.id
            outcome = "imported_unverified"

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing_audit = connection.execute(
                    """
                    SELECT 1 FROM hatch_legacy_imports
                    WHERE source_name = ? AND content_sha256 = ?
                    """,
                    (path.name, content_sha),
                ).fetchone()
                if existing_audit is not None:
                    connection.rollback()
                    return
                existing_job = connection.execute(
                    "SELECT 1 FROM hatch_jobs WHERE id = ?", (job_id,)
                ).fetchone()
                if existing_job is None:
                    self._insert_job(connection, job, legacy_source=path.name)
                else:
                    outcome = "duplicate_existing"
                connection.execute(
                    """
                    INSERT INTO hatch_legacy_imports(
                        source_name, content_sha256, outcome, reason_code,
                        imported_job_id, observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (path.name, content_sha, outcome, reason, job_id, now),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _map_legacy_job(legacy: _LegacyHatchJob, *, now: str) -> HatchJob:
        if legacy.status in {"queued", "probing", "running"}:
            status = "needs_authorization"
            step = "Legacy generation was interrupted; exact authorization is required."
            error = "Legacy in-progress work will not be replayed automatically."
            complete = 0
        elif legacy.status in {"complete", "awaiting_assembly_qa"}:
            status = "awaiting_assembly_qa"
            step = "Legacy candidate art is unverified and still requires full assembly and QA."
            error = "Legacy provider calls have no exact durable provenance receipt."
            complete = 1 if legacy.jobs_complete else 0
        elif legacy.status == "failed":
            status = "failed"
            step = legacy.step
            error = legacy.error
            complete = 0
        else:
            status = "interrupted"
            step = "Legacy hatch was imported without replay."
            error = legacy.error or "Legacy hatch requires operator review."
            complete = 0
        return HatchJob(
            id=legacy.id,
            pet_id=legacy.pet_id,
            display_name=legacy.display_name,
            description=legacy.description,
            style_preset=legacy.style_preset,
            pet_notes=legacy.pet_notes,
            status=status,
            step=step,
            jobs_complete=complete,
            error=error,
            spritesheet=None,
            image_backend=legacy.image_backend,
            image_model=legacy.image_model,
            paid_generation_acknowledged=False,
            created_at=legacy.created_at,
            updated_at=now,
        )

    def _row_to_job(self, row: sqlite3.Row) -> HatchJob:
        return HatchJob(
            id=row["id"],
            pet_id=row["pet_id"],
            display_name=row["display_name"],
            description=row["description"],
            style_preset=row["style_preset"],
            pet_notes=row["pet_notes"],
            status=row["status"],
            step=row["step"],
            jobs_complete=row["jobs_complete"],
            jobs_total=row["jobs_total"],
            error=row["error"],
            spritesheet=row["spritesheet"],
            image_backend=row["image_backend"],
            image_model=row["image_model"],
            paid_generation_acknowledged=bool(row["paid_generation_acknowledged"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            request_hash=row["request_hash"],
            provider_fingerprint=row["provider_fingerprint"],
            request_fingerprint=row["request_fingerprint"],
            effect_id=row["effect_id"],
            effect_status=row["effect_status"],
            candidate_asset=row["intended_asset"] if row["asset_sha256"] else None,
            candidate_sha256=row["asset_sha256"],
            authorization_expires_at=row["expires_at"],
            possible_duplicate_acknowledged=bool(
                row["acknowledge_possible_duplicate"] or 0
            ),
        )

    @staticmethod
    def _job_select() -> str:
        return """
            SELECT j.*,
                   a.request_hash,
                   a.provider_fingerprint,
                   a.request_fingerprint,
                   a.expires_at,
                   a.acknowledge_possible_duplicate,
                   e.effect_id,
                   e.state AS effect_status,
                   e.intended_asset,
                   e.asset_sha256
            FROM hatch_jobs AS j
            LEFT JOIN hatch_authorizations AS a ON a.job_id = j.id
            LEFT JOIN hatch_effects AS e ON e.job_id = j.id
        """

    def list_jobs(self) -> list[HatchJob]:
        with self._connect() as connection:
            rows = connection.execute(
                self._job_select()
                + " ORDER BY j.created_at DESC, j.rowid DESC LIMIT ?",
                (MAX_HATCH_JOBS,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def get(self, job_id: str) -> HatchJob | None:
        if not _SAFE_COMPONENT.fullmatch(job_id):
            raise ValueError("invalid hatch job id")
        with self._connect() as connection:
            row = connection.execute(
                self._job_select() + " WHERE j.id = ?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row is not None else None

    def get_effect(self, job_id: str) -> HatchEffect | None:
        if not _SAFE_COMPONENT.fullmatch(job_id):
            raise ValueError("invalid hatch job id")
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM hatch_effects WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._row_to_effect(row) if row is not None else None

    @staticmethod
    def _row_to_effect(row: sqlite3.Row) -> HatchEffect:
        return HatchEffect(
            effect_id=row["effect_id"],
            job_id=row["job_id"],
            state=row["state"],
            attempt_count=row["attempt_count"],
            dispatch_token=row["dispatch_token"],
            dispatch_deadline_at=row["dispatch_deadline_at"],
            intended_asset=row["intended_asset"],
            asset_sha256=row["asset_sha256"],
            asset_bytes=row["asset_bytes"],
            last_error_code=row["last_error_code"],
        )

    def create(self, job: HatchJob) -> HatchJob:
        """Persist a non-billable legacy-style record as needing authorization."""

        now = _format_utc(self._now())
        safe_job = job.model_copy(
            update={
                "status": "needs_authorization",
                "step": "A bound one-call hatch authorization is required.",
                "jobs_complete": 0,
                "jobs_total": 1,
                "error": "Legacy boolean charge acknowledgement is not sufficient.",
                "spritesheet": None,
                "paid_generation_acknowledged": False,
                "updated_at": now,
            }
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM hatch_jobs"
                ).fetchone()[0]
                if count >= MAX_HATCH_JOBS:
                    raise HatchAuthorizationError("hatch registry capacity is full")
                self._insert_job(connection, safe_job)
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                raise ValueError("hatch job id already exists") from exc
            except BaseException:
                connection.rollback()
                raise
        return self.get(job.id) or safe_job

    def create_if_idle(self, _job: HatchJob) -> HatchJob:
        """Legacy boolean-only admission is intentionally fail-closed."""

        raise HatchAuthorizationError("bound hatch authorization is required")

    def note_pre_dispatch_block(
        self, job_id: str, *, step: str, error: str
    ) -> HatchJob:
        """Persist a bounded local block while leaving the one-call reserve intact."""

        safe_step = _bounded_text(step, name="step", maximum=1024)
        safe_error = _bounded_text(error, name="error", maximum=4096)
        now = _format_utc(self._now())
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE hatch_jobs
                SET step = ?, error = ?, updated_at = ?
                WHERE id = ? AND status IN ('queued', 'needs_authorization')
                """,
                (safe_step, safe_error, now, job_id),
            )
        return self._require_job(job_id)

    def create_or_replay(
        self, job: HatchJob, authorization: HatchAuthorization
    ) -> HatchJob:
        """Atomically create one authorized effect or replay its canonical job."""

        request_hash = hatch_request_hash(job)
        if request_hash != authorization.request_hash:
            raise HatchConflictError("authorization request does not match hatch request")
        expected_request = _generate_request_fingerprint(
            job, authorization.provider_fingerprint
        )
        if expected_request != authorization.request_fingerprint:
            raise HatchConflictError("authorization generate request does not match")
        now = _format_utc(self._now())
        canonical_job = job.model_copy(
            update={
                "status": "queued",
                "step": "Authorized base candidate is reserved.",
                "jobs_complete": 0,
                "jobs_total": 1,
                "error": None,
                "spritesheet": None,
                "image_backend": authorization.provider,
                "image_model": authorization.model_id,
                "paid_generation_acknowledged": True,
                "updated_at": now,
            }
        )
        effect_id = _stable_id(
            "effect_",
            "pex.hatch.effect.v1",
            [
                authorization.principal,
                authorization.idempotency_key,
                authorization.request_hash,
                authorization.provider_fingerprint,
                authorization.request_fingerprint,
                "base_candidate",
            ],
        )
        intended_asset = f"{canonical_job.id}/decoded/base.png"

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                replay = connection.execute(
                    """
                    SELECT job_id, authorization_id, request_hash,
                           provider_fingerprint, request_fingerprint, max_calls,
                           expires_at, acknowledge_possible_duplicate,
                           duplicate_risk_job_id, duplicate_risk_effect_id
                    FROM hatch_authorizations
                    WHERE principal = ? AND idempotency_key = ?
                    """,
                    (authorization.principal, authorization.idempotency_key),
                ).fetchone()
                if replay is not None:
                    expected = (
                        authorization.request_hash,
                        authorization.provider_fingerprint,
                        authorization.request_fingerprint,
                        authorization.max_calls,
                        int(authorization.acknowledge_possible_duplicate),
                        authorization.duplicate_risk_job_id,
                        authorization.duplicate_risk_effect_id,
                    )
                    actual = (
                        replay["request_hash"],
                        replay["provider_fingerprint"],
                        replay["request_fingerprint"],
                        replay["max_calls"],
                        replay["acknowledge_possible_duplicate"],
                        replay["duplicate_risk_job_id"],
                        replay["duplicate_risk_effect_id"],
                    )
                    if actual != expected:
                        raise HatchConflictError(
                            "hatch idempotency key was reused with different authorization"
                        )
                    canonical_id = replay["job_id"]
                    connection.commit()
                    result = self.get(canonical_id)
                    if result is None:
                        raise RuntimeError("canonical hatch job disappeared")
                    return result

                issued = _parse_utc(authorization.issued_at)
                expires = _parse_utc(authorization.expires_at)
                server_now = self._now()
                if issued > server_now + timedelta(
                    seconds=MAX_AUTHORIZATION_CLOCK_SKEW_SECONDS
                ):
                    raise HatchAuthorizationError(
                        "hatch authorization is not yet valid"
                    )
                if expires <= server_now:
                    raise HatchAuthorizationError("hatch authorization has expired")

                prior_uncertain = connection.execute(
                    """
                    SELECT a.job_id, e.effect_id
                    FROM hatch_authorizations AS a
                    JOIN hatch_effects AS e ON e.job_id = a.job_id
                    WHERE a.principal = ? AND a.request_hash = ?
                      AND e.state = 'delivery_uncertain'
                    ORDER BY e.updated_at DESC, e.rowid DESC
                    LIMIT 1
                    """,
                    (authorization.principal, authorization.request_hash),
                ).fetchone()
                if prior_uncertain is not None:
                    exact_ack = (
                        authorization.acknowledge_possible_duplicate
                        and authorization.duplicate_risk_job_id
                        == prior_uncertain["job_id"]
                        and authorization.duplicate_risk_effect_id
                        == prior_uncertain["effect_id"]
                    )
                    if not exact_ack:
                        raise HatchAuthorizationError(
                            "a new attempt must acknowledge and bind the exact uncertain effect"
                        )
                elif authorization.acknowledge_possible_duplicate:
                    raise HatchConflictError(
                        "duplicate-risk acknowledgement does not match an uncertain effect"
                    )

                if connection.execute(
                    "SELECT 1 FROM hatch_jobs WHERE id = ?", (canonical_job.id,)
                ).fetchone():
                    raise HatchConflictError("hatch job id already exists")
                count = connection.execute(
                    "SELECT COUNT(*) FROM hatch_jobs"
                ).fetchone()[0]
                if count >= MAX_HATCH_JOBS:
                    raise HatchAuthorizationError("hatch registry capacity is full")

                self._insert_job(connection, canonical_job)
                connection.execute(
                    """
                    INSERT INTO hatch_authorizations(
                        authorization_id, job_id, principal, idempotency_key,
                        request_hash, provider, endpoint, model_id,
                        credential_present, credential_scope,
                        provider_fingerprint, request_fingerprint, max_calls,
                        issued_at, expires_at, acknowledge_possible_duplicate,
                        duplicate_risk_job_id, duplicate_risk_effect_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        authorization.authorization_id,
                        canonical_job.id,
                        authorization.principal,
                        authorization.idempotency_key,
                        authorization.request_hash,
                        authorization.provider,
                        authorization.endpoint,
                        authorization.model_id,
                        int(authorization.credential_present),
                        authorization.credential_scope,
                        authorization.provider_fingerprint,
                        authorization.request_fingerprint,
                        authorization.max_calls,
                        authorization.issued_at,
                        authorization.expires_at,
                        int(authorization.acknowledge_possible_duplicate),
                        authorization.duplicate_risk_job_id,
                        authorization.duplicate_risk_effect_id,
                        now,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO hatch_effects(
                        effect_id, job_id, effect_key, state,
                        provider_fingerprint, request_fingerprint,
                        attempt_count, intended_asset, created_at, updated_at
                    ) VALUES (?, ?, 'base_candidate', 'reserved', ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        effect_id,
                        canonical_job.id,
                        authorization.provider_fingerprint,
                        authorization.request_fingerprint,
                        intended_asset,
                        now,
                        now,
                    ),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        result = self.get(canonical_job.id)
        if result is None:
            raise RuntimeError("created hatch job disappeared")
        return result

    def claim_for_dispatch(
        self, job_id: str, config: Mapping[str, Any]
    ) -> DispatchClaim:
        binding = _safe_provider_binding(config)
        provider_fingerprint = _provider_fingerprint(binding)
        now_dt = self._now()
        now = _format_utc(now_dt)
        dispatch_window = max(
            MIN_DISPATCH_WINDOW_SECONDS,
            float(binding["timeout_seconds"]) + DISPATCH_GRACE_SECONDS,
        )
        deadline = _format_utc(now_dt + timedelta(seconds=dispatch_window))
        dispatch_token = secrets.token_hex(32)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT e.*, a.principal, a.request_hash,
                           a.issued_at, a.expires_at,
                           a.acknowledge_possible_duplicate,
                           a.duplicate_risk_job_id,
                           a.duplicate_risk_effect_id,
                           a.provider_fingerprint AS auth_provider,
                           a.request_fingerprint AS auth_request
                    FROM hatch_effects AS e
                    JOIN hatch_authorizations AS a ON a.job_id = e.job_id
                    WHERE e.job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
                if row is None:
                    connection.commit()
                    job = self.get(job_id)
                    if job is None:
                        raise KeyError(job_id)
                    return DispatchClaim(
                        claimed=False,
                        reason="not_reserved",
                        job=job,
                        effect=None,
                    )
                effect = self._row_to_effect(row)
                if effect.state in _TERMINAL_EFFECT_STATES:
                    connection.commit()
                    return DispatchClaim(
                        claimed=False,
                        reason="already_terminal",
                        job=self._require_job(job_id),
                        effect=effect,
                    )
                if effect.state == "dispatching":
                    connection.commit()
                    return DispatchClaim(
                        claimed=False,
                        reason="already_dispatching",
                        job=self._require_job(job_id),
                        effect=effect,
                    )
                if effect.state != "reserved" or effect.attempt_count != 0:
                    connection.commit()
                    return DispatchClaim(
                        claimed=False,
                        reason="not_reserved",
                        job=self._require_job(job_id),
                        effect=effect,
                    )
                prior_uncertain = connection.execute(
                    """
                    SELECT other.job_id, other.effect_id
                    FROM hatch_authorizations AS prior
                    JOIN hatch_effects AS other ON other.job_id = prior.job_id
                    WHERE prior.principal = ? AND prior.request_hash = ?
                      AND other.state = 'delivery_uncertain'
                      AND other.effect_id != ?
                    ORDER BY other.updated_at DESC, other.rowid DESC
                    LIMIT 1
                    """,
                    (row["principal"], row["request_hash"], effect.effect_id),
                ).fetchone()
                if prior_uncertain is not None:
                    exact_duplicate_ack = (
                        bool(row["acknowledge_possible_duplicate"])
                        and row["duplicate_risk_job_id"]
                        == prior_uncertain["job_id"]
                        and row["duplicate_risk_effect_id"]
                        == prior_uncertain["effect_id"]
                    )
                    if not exact_duplicate_ack:
                        self._skip_reserved(
                            connection,
                            job_id,
                            code="unacknowledged_duplicate_risk",
                            now=now,
                            step=(
                                "A prior attempt became delivery-uncertain before "
                                "this dispatch."
                            ),
                        )
                        connection.commit()
                        return DispatchClaim(
                            claimed=False,
                            reason="not_reserved",
                            job=self._require_job(job_id),
                            effect=self.get_effect(job_id),
                        )
                authorization_not_yet_valid = _parse_utc(
                    row["issued_at"]
                ) > now_dt + timedelta(seconds=MAX_AUTHORIZATION_CLOCK_SKEW_SECONDS)
                authorization_expired = _parse_utc(row["expires_at"]) <= now_dt
                if authorization_not_yet_valid or authorization_expired:
                    code = (
                        "authorization_not_yet_valid"
                        if authorization_not_yet_valid
                        else "authorization_expired"
                    )
                    self._skip_reserved(
                        connection,
                        job_id,
                        code=code,
                        now=now,
                        step="Hatch authorization was not valid at dispatch time.",
                    )
                    connection.commit()
                    return DispatchClaim(
                        claimed=False,
                        reason="authorization_expired",
                        job=self._require_job(job_id),
                        effect=self.get_effect(job_id),
                    )
                expected_request = _generate_request_fingerprint(
                    self._require_job(job_id), provider_fingerprint
                )
                if (
                    provider_fingerprint != row["auth_provider"]
                    or expected_request != row["auth_request"]
                ):
                    connection.execute(
                        """
                        UPDATE hatch_jobs
                        SET step = ?, error = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            "Configured provider does not match the bound authorization.",
                            "Provider or generate-request fingerprint mismatch; no call was made.",
                            now,
                            job_id,
                        ),
                    )
                    connection.commit()
                    return DispatchClaim(
                        claimed=False,
                        reason="provider_mismatch",
                        job=self._require_job(job_id),
                        effect=self.get_effect(job_id),
                    )
                global_dispatch = connection.execute(
                    """
                    SELECT effect_id FROM hatch_effects
                    WHERE state = 'dispatching' AND effect_id != ? LIMIT 1
                    """,
                    (effect.effect_id,),
                ).fetchone()
                if global_dispatch is not None:
                    connection.execute(
                        """
                        UPDATE hatch_jobs
                        SET step = ?, updated_at = ? WHERE id = ?
                        """,
                        (
                            "Waiting for the current billable hatch dispatch to finish.",
                            now,
                            job_id,
                        ),
                    )
                    connection.commit()
                    return DispatchClaim(
                        claimed=False,
                        reason="global_dispatch_busy",
                        job=self._require_job(job_id),
                        effect=effect,
                    )
                cursor = connection.execute(
                    """
                    UPDATE hatch_effects
                    SET state = 'dispatching', attempt_count = 1,
                        owner_boot_id = ?, owner_pid = ?, dispatch_token = ?,
                        dispatch_started_at = ?, dispatch_deadline_at = ?,
                        updated_at = ?
                    WHERE effect_id = ? AND state = 'reserved' AND attempt_count = 0
                    """,
                    (
                        self._boot_id,
                        self._pid,
                        dispatch_token,
                        now,
                        deadline,
                        now,
                        effect.effect_id,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.rollback()
                    return DispatchClaim(
                        claimed=False,
                        reason="already_dispatching",
                        job=self._require_job(job_id),
                        effect=self.get_effect(job_id),
                    )
                connection.execute(
                    """
                    UPDATE hatch_jobs
                    SET status = 'running', step = ?, error = NULL,
                        image_backend = ?, image_model = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        "Imagining one unverified base candidate.",
                        binding["provider"],
                        binding["model_id"],
                        now,
                        job_id,
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
                return DispatchClaim(
                    claimed=False,
                    reason="global_dispatch_busy",
                    job=self._require_job(job_id),
                    effect=self.get_effect(job_id),
                )
            except BaseException:
                connection.rollback()
                raise
        claimed_effect = self.get_effect(job_id)
        return DispatchClaim(
            claimed=True,
            reason="claimed",
            job=self._require_job(job_id),
            effect=claimed_effect,
        )

    @staticmethod
    def _skip_reserved(
        connection: sqlite3.Connection,
        job_id: str,
        *,
        code: str,
        now: str,
        step: str,
    ) -> None:
        connection.execute(
            """
            UPDATE hatch_effects
            SET state = 'skipped', last_error_code = ?, updated_at = ?
            WHERE job_id = ? AND state = 'reserved' AND attempt_count = 0
            """,
            (code, now, job_id),
        )
        connection.execute(
            """
            UPDATE hatch_jobs
            SET status = 'needs_authorization', step = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (step, code.replace("_", " "), now, job_id),
        )

    def finalize_delivered(
        self,
        job_id: str,
        *,
        dispatch_token: str,
    ) -> HatchJob:
        now = _format_utc(self._now())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT e.*, a.request_hash
                    FROM hatch_effects AS e
                    JOIN hatch_authorizations AS a ON a.job_id = e.job_id
                    WHERE e.job_id = ?
                    """,
                    (job_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(job_id)
                if row["dispatch_token"] != dispatch_token:
                    raise HatchConflictError("hatch dispatch token does not match")
                if row["state"] in _TERMINAL_EFFECT_STATES:
                    connection.commit()
                    return self._require_job(job_id)
                if row["state"] != "dispatching" or row["attempt_count"] != 1:
                    raise HatchConflictError("hatch effect is not dispatching")
                receipt = self._validated_local_candidate(row)
                if receipt is None:
                    raise HatchConflictError(
                        "candidate asset and receipt failed exact provenance validation"
                    )
                asset_sha256, asset_bytes = receipt
                cursor = connection.execute(
                    """
                    UPDATE hatch_effects
                    SET state = 'delivered', asset_sha256 = ?, asset_bytes = ?,
                        last_error_code = NULL, updated_at = ?
                    WHERE job_id = ? AND state = 'dispatching'
                      AND dispatch_token = ? AND attempt_count = 1
                    """,
                    (asset_sha256, asset_bytes, now, job_id, dispatch_token),
                )
                if cursor.rowcount != 1:
                    raise HatchConflictError("hatch delivery finalizer lost its CAS")
                connection.execute(
                    """
                    UPDATE hatch_jobs
                    SET status = 'awaiting_assembly_qa', jobs_complete = 1,
                        step = ?, error = NULL, spritesheet = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        "Base candidate ready; grounded pose generation, assembly, "
                        "and independent QA remain required.",
                        now,
                        job_id,
                    ),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return self._require_job(job_id)

    def finalize_uncertain(
        self, job_id: str, *, dispatch_token: str, error_code: str
    ) -> HatchJob:
        safe_code = _bounded_text(error_code, name="error code", maximum=256)
        now = _format_utc(self._now())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT state, attempt_count, dispatch_token FROM hatch_effects "
                    "WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
                if row is None:
                    raise KeyError(job_id)
                if row["dispatch_token"] != dispatch_token:
                    raise HatchConflictError("hatch dispatch token does not match")
                if row["state"] in _TERMINAL_EFFECT_STATES:
                    connection.commit()
                    return self._require_job(job_id)
                if row["state"] != "dispatching" or row["attempt_count"] != 1:
                    raise HatchConflictError("hatch effect is not dispatching")
                cursor = connection.execute(
                    """
                    UPDATE hatch_effects
                    SET state = 'delivery_uncertain', last_error_code = ?, updated_at = ?
                    WHERE job_id = ? AND state = 'dispatching'
                      AND dispatch_token = ? AND attempt_count = 1
                    """,
                    (safe_code, now, job_id, dispatch_token),
                )
                if cursor.rowcount != 1:
                    raise HatchConflictError("hatch uncertainty finalizer lost its CAS")
                connection.execute(
                    """
                    UPDATE hatch_jobs
                    SET status = 'delivery_uncertain', step = ?, error = ?,
                        jobs_complete = 0, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        "Provider delivery is uncertain; this effect will not be replayed.",
                        "A new attempt requires explicit acknowledgement of "
                        "possible duplicate charges.",
                        now,
                        job_id,
                    ),
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return self._require_job(job_id)

    def cancel(self, job_id: str) -> HatchJob:
        """Cancel before dispatch, or conservatively mark an in-flight call uncertain."""

        now = _format_utc(self._now())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT state FROM hatch_effects WHERE job_id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    connection.commit()
                    return self._require_job(job_id)
                if row["state"] == "reserved":
                    connection.execute(
                        """
                        UPDATE hatch_effects
                        SET state = 'skipped', last_error_code = 'cancelled_before_dispatch',
                            updated_at = ? WHERE job_id = ? AND state = 'reserved'
                        """,
                        (now, job_id),
                    )
                    connection.execute(
                        """
                        UPDATE hatch_jobs
                        SET status = 'interrupted', step = ?, error = NULL, updated_at = ?
                        WHERE id = ?
                        """,
                        ("Hatch cancelled before provider dispatch.", now, job_id),
                    )
                elif row["state"] == "dispatching":
                    connection.execute(
                        """
                        UPDATE hatch_effects
                        SET state = 'delivery_uncertain',
                            last_error_code = 'cancelled_after_dispatch',
                            updated_at = ? WHERE job_id = ? AND state = 'dispatching'
                        """,
                        (now, job_id),
                    )
                    connection.execute(
                        """
                        UPDATE hatch_jobs
                        SET status = 'delivery_uncertain', step = ?, error = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            "Cancellation occurred after dispatch; provider delivery is uncertain.",
                            "This effect will not be replayed automatically.",
                            now,
                            job_id,
                        ),
                    )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return self._require_job(job_id)

    def recover_expired_dispatches(self) -> int:
        """Recover only after the durable provider deadline; never make it retryable."""

        now = _format_utc(self._now())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute(
                    """
                    SELECT job_id FROM hatch_effects
                    WHERE state = 'dispatching' AND dispatch_deadline_at IS NOT NULL
                      AND dispatch_deadline_at <= ?
                    """,
                    (now,),
                ).fetchall()
                count = 0
                for row in rows:
                    if self._reconcile_candidate_in_transaction(
                        connection, row["job_id"], now=now
                    ):
                        count += 1
                        continue
                    cursor = connection.execute(
                        """
                        UPDATE hatch_effects
                        SET state = 'delivery_uncertain',
                            last_error_code = 'dispatch_deadline_expired', updated_at = ?
                        WHERE job_id = ? AND state = 'dispatching'
                          AND dispatch_deadline_at <= ?
                        """,
                        (now, row["job_id"], now),
                    )
                    if cursor.rowcount == 1:
                        connection.execute(
                            """
                            UPDATE hatch_jobs
                            SET status = 'delivery_uncertain', step = ?, error = ?,
                                jobs_complete = 0, updated_at = ? WHERE id = ?
                            """,
                            (
                                "Dispatch deadline expired without a reconciled base candidate.",
                                "This effect is not retryable; a new attempt needs exact "
                                "duplicate-risk acknowledgement.",
                                now,
                                row["job_id"],
                            ),
                        )
                        count += 1
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return count

    def reconcile_persisted_assets(self) -> int:
        """Recover complete local assets without waiting for a dispatch deadline."""

        now = _format_utc(self._now())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                rows = connection.execute(
                    """
                    SELECT job_id FROM hatch_effects
                    WHERE state IN ('dispatching', 'delivery_uncertain')
                    ORDER BY created_at, rowid
                    """
                ).fetchall()
                count = sum(
                    self._reconcile_candidate_in_transaction(
                        connection, row["job_id"], now=now
                    )
                    for row in rows
                )
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return count

    def reconcile_local_asset(self, job_id: str) -> HatchJob:
        """Reconcile an atomically persisted valid base candidate without provider I/O."""

        now = _format_utc(self._now())
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._reconcile_candidate_in_transaction(connection, job_id, now=now)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return self._require_job(job_id)

    def _reconcile_candidate_in_transaction(
        self, connection: sqlite3.Connection, job_id: str, *, now: str
    ) -> bool:
        row = connection.execute(
            """
            SELECT e.state, e.effect_id, e.job_id, e.attempt_count,
                   e.intended_asset, a.request_hash,
                   a.provider_fingerprint, a.request_fingerprint
            FROM hatch_effects AS e
            JOIN hatch_authorizations AS a ON a.job_id = e.job_id
            WHERE e.job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if (
            row is None
            or row["state"] not in {"dispatching", "delivery_uncertain"}
            or row["attempt_count"] != 1
        ):
            return False
        receipt = self._validated_local_candidate(row)
        if receipt is None:
            return False
        sha, size = receipt
        cursor = connection.execute(
            """
            UPDATE hatch_effects
            SET state = 'delivered', asset_sha256 = ?, asset_bytes = ?,
                last_error_code = NULL, updated_at = ?
            WHERE job_id = ? AND state IN ('dispatching', 'delivery_uncertain')
            """,
            (sha, size, now, job_id),
        )
        if cursor.rowcount != 1:
            return False
        connection.execute(
            """
            UPDATE hatch_jobs
            SET status = 'awaiting_assembly_qa', jobs_complete = 1,
                step = ?, error = NULL, spritesheet = NULL, updated_at = ?
            WHERE id = ?
            """,
            (
                "Persisted base candidate reconciled; grounded poses, assembly, and "
                "independent QA remain required.",
                now,
                job_id,
            ),
        )
        return True

    def _validated_local_candidate(self, row: sqlite3.Row) -> tuple[str, int] | None:
        relative_path = row["intended_asset"]
        try:
            relative = Path(relative_path)
            expected_relative = f"{row['job_id']}/decoded/base.png"
            if (
                relative_path != expected_relative
                or relative.is_absolute()
                or ".." in relative.parts
            ):
                return None
            candidate = _assert_contained_without_links(
                self.root, self.root / relative
            )
            reference = _assert_contained_without_links(
                self.root,
                self.root / row["job_id"] / "references" / "canonical-base.png",
            )
            receipt_path = _assert_contained_without_links(
                self.root, self.root / row["job_id"] / "candidate-receipt.json"
            )
            for path in (candidate, reference, receipt_path):
                if (
                    not path.exists()
                    or _is_link_or_junction(path)
                    or not path.is_file()
                ):
                    return None
            size = candidate.stat().st_size
            if not 1 <= size <= 25 * 1024 * 1024:
                return None
            raw = candidate.read_bytes()
            if len(raw) != size or reference.read_bytes() != raw:
                return None
            receipt_size = receipt_path.stat().st_size
            if not 1 <= receipt_size <= MAX_CANDIDATE_RECEIPT_BYTES:
                return None
            receipt_raw = receipt_path.read_bytes()
            if len(receipt_raw) != receipt_size:
                return None
            decoded = json.loads(
                receipt_raw.decode("utf-8"),
                parse_constant=_reject_json_constant,
                object_pairs_hook=_unique_json_object,
            )
            receipt = HatchCandidateReceipt.model_validate(decoded)
            from PIL import Image, UnidentifiedImageError

            try:
                with Image.open(candidate) as image:
                    if image.format != "PNG":
                        return None
                    if (
                        image.width > 4096
                        or image.height > 4096
                        or image.width * image.height > 20_000_000
                    ):
                        return None
                    image.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                return None
            sha = _sha256(raw)
            exact_receipt = (
                receipt.job_id == row["job_id"]
                and receipt.effect_id == row["effect_id"]
                and receipt.request_hash == row["request_hash"]
                and receipt.provider_fingerprint == row["provider_fingerprint"]
                and receipt.request_fingerprint == row["request_fingerprint"]
                and receipt.asset == relative_path
                and receipt.asset_sha256 == sha
                and receipt.asset_bytes == size
            )
            if not exact_receipt:
                return None
            return sha, size
        except (
            HatchAuthorizationError,
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ValueError,
        ):
            return None

    def _require_job(self, job_id: str) -> HatchJob:
        job = self.get(job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def legacy_import_audit(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT source_name, content_sha256, outcome, reason_code,
                       imported_job_id, observed_at
                FROM hatch_legacy_imports
                ORDER BY observed_at, source_name
                """
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = [
    "DISPATCH_GRACE_SECONDS",
    "HatchAuthorization",
    "HatchAuthorizationError",
    "HatchCandidateReceipt",
    "HatchConflictError",
    "HatchEffect",
    "HatchJob",
    "HatchRegistry",
    "JOBS_TOTAL",
    "authorize_hatch",
    "base_candidate_prompt",
    "hatch_request_hash",
    "prepare_hatch_artifact_dirs",
]
