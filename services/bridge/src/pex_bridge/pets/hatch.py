"""One-call, durable generation of unverified pet base-candidate art.

This module never generates animation rows and never produces a playable pet.
The hatch-pet workflow must ground every later row in the approved base, assemble
an 8x11 v2 atlas, and pass deterministic plus independent visual QA.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError

from pex_bridge.pets.hatch_store import (
    JOBS_TOTAL,
    HatchAuthorization,
    HatchAuthorizationError,
    HatchConflictError,
    HatchEffect,
    HatchJob,
    HatchRegistry,
    authorize_hatch,
    base_candidate_prompt,
    hatch_request_hash,
    prepare_hatch_artifact_dirs,
)
from pex_bridge.pets.imagegen import HatchImageError, generate_png, hatch_image_config

_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_TERMINAL_EFFECT_STATES = frozenset(
    {"delivered", "failed", "delivery_uncertain", "skipped"}
)


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "pet"


def hatch_prompt(job: HatchJob, kind: str, _frames: int, _action: str) -> str:
    """Return the only safe in-app prompt: one unverified base candidate."""

    if kind != "base":
        raise ValueError(
            "in-app hatch may generate only one base candidate; rows require hatch-pet"
        )
    return base_candidate_prompt(job)


def _atomic_write_bytes(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.name}.{secrets.token_hex(8)}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # Linking a complete temporary file into its final name is atomic and
        # fails if another actor preplanted that name after our path check.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(destination: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(destination, encoded)


def write_generated(
    job_dir: Path,
    name: str,
    image_bytes: bytes,
    *,
    root: Path | None = None,
) -> Path:
    """Validate and normalize provider output before atomically storing a PNG."""

    if not _SAFE_COMPONENT.fullmatch(name):
        raise HatchImageError("candidate image name is invalid")
    if not image_bytes or len(image_bytes) > 25 * 1024 * 1024:
        raise HatchImageError("image response was empty or exceeded the 25 MiB safety limit")
    artifact_root = root or job_dir.parent
    try:
        secured_job_dir = prepare_hatch_artifact_dirs(
            artifact_root, job_dir.name, require_empty=False
        )
    except HatchAuthorizationError as exc:
        raise HatchImageError("candidate artifact path is unsafe") from exc
    if secured_job_dir != Path(os.path.abspath(os.fspath(job_dir))):
        raise HatchImageError("candidate artifact path escaped its root")
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            if (
                source.width > 4096
                or source.height > 4096
                or source.width * source.height > 20_000_000
            ):
                raise HatchImageError(
                    "image dimensions exceeded the candidate-art safety limit"
                )
            source.verify()
        with Image.open(BytesIO(image_bytes)) as source:
            normalized = source.convert("RGBA")
            encoded = BytesIO()
            normalized.save(encoded, format="PNG")
            normalized.close()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HatchImageError("image provider returned invalid or unsafe image bytes") from exc

    normalized_png = encoded.getvalue()
    if len(normalized_png) > 25 * 1024 * 1024:
        raise HatchImageError("normalized candidate exceeded the 25 MiB safety limit")
    destination = job_dir / "decoded" / f"{name}.png"
    _atomic_write_bytes(destination, normalized_png)
    if name == "base":
        _atomic_write_bytes(
            job_dir / "references" / "canonical-base.png", normalized_png
        )
    return destination


def write_candidate_receipt(
    registry: HatchRegistry,
    job: HatchJob,
    effect: HatchEffect,
    asset: Path,
) -> Path:
    """Persist the strict, secret-free provenance required for reconciliation."""

    if not job.request_hash or not job.provider_fingerprint or not job.request_fingerprint:
        raise HatchImageError("hatch job is missing its exact request binding")
    try:
        job_dir = prepare_hatch_artifact_dirs(registry.root, job.id)
    except HatchAuthorizationError as exc:
        raise HatchImageError("candidate artifact path is unsafe") from exc
    expected_asset = job_dir / "decoded" / "base.png"
    if Path(os.path.abspath(os.fspath(asset))) != expected_asset:
        raise HatchImageError("candidate asset path does not match the reserved effect")
    payload = asset.read_bytes()
    relative_asset = asset.relative_to(registry.root).as_posix()
    receipt = job_dir / "candidate-receipt.json"
    _atomic_write_json(
        receipt,
        {
            "schema": "pex.hatch.base-candidate-receipt.v1",
            "job_id": job.id,
            "effect_id": effect.effect_id,
            "result_state": "base_candidate_persisted",
            "request_hash": job.request_hash,
            "provider_fingerprint": job.provider_fingerprint,
            "request_fingerprint": job.request_fingerprint,
            "asset": relative_asset,
            "asset_sha256": hashlib.sha256(payload).hexdigest(),
            "asset_bytes": len(payload),
            "playable_pet": False,
            "qa_status": "awaiting_grounded_assembly_and_independent_qa",
        },
    )
    return receipt


def _wait_for_canonical_terminal(
    registry: HatchRegistry, job_id: str, *, timeout_seconds: float = 5.0
) -> HatchJob:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        effect = registry.get_effect(job_id)
        job = registry.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if effect is None or effect.state in _TERMINAL_EFFECT_STATES:
            return job
        time.sleep(0.01)
    job = registry.get(job_id)
    if job is None:
        raise KeyError(job_id)
    return job


def run_hatch_job(
    registry: HatchRegistry,
    job_id: str,
    *,
    config: Mapping[str, Any] | None = None,
) -> HatchJob:
    """Dispatch at most one billable base generation through the durable ledger."""

    job = registry.get(job_id)
    if job is None:
        raise KeyError(job_id)
    effect = registry.get_effect(job_id)
    if effect is None or effect.state in _TERMINAL_EFFECT_STATES:
        return job
    if effect.state == "dispatching":
        return _wait_for_canonical_terminal(registry, job_id)

    cfg = config if config is not None else hatch_image_config()
    if cfg is None:
        return registry.note_pre_dispatch_block(
            job_id,
            step="Hatch needs an explicitly bound image provider.",
            error="No authorized image provider configuration is available; no call was made.",
        )

    try:
        job_dir = prepare_hatch_artifact_dirs(
            registry.root, job_id, require_empty=True
        )
    except HatchAuthorizationError:
        return registry.note_pre_dispatch_block(
            job_id,
            step="Hatch artifact path requires operator review.",
            error="Unsafe or pre-existing hatch artifacts blocked provider dispatch.",
        )

    claim = registry.claim_for_dispatch(job_id, cfg)
    if not claim.claimed:
        if claim.reason == "already_dispatching":
            return _wait_for_canonical_terminal(registry, job_id)
        return claim.job
    claimed_effect = claim.effect
    if claimed_effect is None or claimed_effect.dispatch_token is None:
        raise RuntimeError("hatch dispatch claim did not contain a durable token")

    try:
        # Exactly one potentially billable operation exists in this function.
        png = generate_png(base_candidate_prompt(claim.job), config=cfg)
        asset = write_generated(job_dir, "base", png, root=registry.root)
        write_candidate_receipt(registry, claim.job, claimed_effect, asset)
        return registry.finalize_delivered(
            job_id,
            dispatch_token=claimed_effect.dispatch_token,
        )
    except BaseException as exc:
        # Once dispatching, generic failures cannot prove that no billable request
        # reached the provider. Never make this effect retryable.
        error_code = f"post_dispatch_{type(exc).__name__.lower()}"
        try:
            result = registry.finalize_uncertain(
                job_id,
                dispatch_token=claimed_effect.dispatch_token,
                error_code=error_code,
            )
        except Exception:
            result = registry.get(job_id) or claim.job
        if not isinstance(exc, Exception):
            raise
        return result


__all__ = [
    "HatchAuthorization",
    "HatchAuthorizationError",
    "HatchConflictError",
    "HatchEffect",
    "HatchJob",
    "HatchRegistry",
    "JOBS_TOTAL",
    "authorize_hatch",
    "hatch_prompt",
    "hatch_request_hash",
    "run_hatch_job",
    "slugify",
    "write_generated",
    "write_candidate_receipt",
]
