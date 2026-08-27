"""In-app Codex-style hatch: 13 visual jobs via the user's PEX image provider."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pex_bridge.pets.imagegen import (
    HatchImageError,
    describe_hatch_backend,
    generate_png,
    hatch_image_config,
    probe_images_endpoint,
)

JOBS_TOTAL = 13
STRIP_PREFIX = (
    "OUTPUT SHAPE (mandatory): a SINGLE horizontal animation strip, one row of frames only, "
    "sitting side by side on a flat #00FF55 chroma-key field. Do NOT generate a spritesheet, "
    "contact sheet, atlas, grid, stacked rows, or 8x11 sheet. Height is one character tall. "
    "No text, labels, numbers, guide boxes, scenery, floor, shadows, speed lines, or detached effects. "
)
BASE_PREFIX = (
    "One centered full-body pet on a flat #00FF55 chroma-key background. "
    "No scenery, shadows, floor, text, labels, or detached effects. "
)

ROW_SPECS: list[tuple[str, int, str]] = [
    ("idle", 6, "calm breathing and blink loop, same planted pose"),
    ("running-right", 8, "body traveling screen-right through limb poses, not a grid"),
    ("running-left", 8, "body traveling screen-left; skip if mirrored from running-right"),
    ("waving", 4, "greeting through a limb pose only, no wave marks"),
    ("jumping", 5, "vertical jump through body height only, no shadows"),
    ("failed", 8, "slumped blocked reaction, attached tears only if any"),
    ("waiting", 6, "expectant asking pose, distinct from idle"),
    ("running", 6, "focused work/thinking, NOT foot-running or jogging"),
    ("review", 6, "inspecting finished work with a lean or head tilt"),
    ("look-cardinals", 4, "four poses left to right: look up, screen-right, down, screen-left"),
    ("look-row-9", 8, "eight look poses from up through down-right"),
    ("look-row-10", 8, "eight look poses from down through up-left"),
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")
    return slug or "pet"


class HatchJob(BaseModel):
    id: str
    pet_id: str
    display_name: str
    description: str
    style_preset: str = "plush"
    pet_notes: str = ""
    status: str = "queued"
    step: str = "Getting pet ready."
    jobs_complete: int = 0
    jobs_total: int = JOBS_TOTAL
    error: str | None = None
    spritesheet: str | None = None
    image_backend: str | None = None
    created_at: str = Field(default_factory=_utcnow)
    updated_at: str = Field(default_factory=_utcnow)

    def public(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class HatchRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: dict[str, HatchJob] = {}
        self._load()

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _load(self) -> None:
        for path in self.root.glob("*.json"):
            try:
                job = HatchJob.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            self._jobs[job.id] = job

    def _save(self, job: HatchJob) -> None:
        job.updated_at = _utcnow()
        self._path(job.id).write_text(job.model_dump_json(indent=2), encoding="utf-8")

    def list_jobs(self) -> list[HatchJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda item: item.created_at, reverse=True)

    def get(self, job_id: str) -> HatchJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def create(self, job: HatchJob) -> HatchJob:
        with self._lock:
            self._jobs[job.id] = job
            self._save(job)
        return job

    def update(self, job_id: str, **fields: Any) -> HatchJob:
        with self._lock:
            job = self._jobs[job_id]
            updated = job.model_copy(update=fields)
            self._jobs[job_id] = updated
            self._save(updated)
            return updated


def hatch_prompt(job: HatchJob, kind: str, frames: int, action: str) -> str:
    identity = job.pet_notes or job.description
    style = job.style_preset
    if kind == "base":
        return (
            f"{BASE_PREFIX}Style `{style}`. Identity: {identity} "
            f"Named {job.display_name}. Compact whole-body mascot readable at 192x208."
        )
    return (
        f"{STRIP_PREFIX}Exactly {frames} frames in one row. State `{kind}`: {action}. "
        f"Style `{style}`. Same identity as the base pet: {identity}"
    )


def write_generated(job_dir: Path, name: str, png: bytes) -> Path:
    decoded = job_dir / "decoded"
    decoded.mkdir(parents=True, exist_ok=True)
    dest = decoded / f"{name}.png"
    dest.write_bytes(png)
    if name == "base":
        refs = job_dir / "references"
        refs.mkdir(parents=True, exist_ok=True)
        (refs / "canonical-base.png").write_bytes(png)
    return dest


def run_hatch_job(registry: HatchRegistry, job_id: str) -> HatchJob:
    job = registry.get(job_id)
    if job is None:
        raise KeyError(job_id)
    cfg = hatch_image_config()
    probe = probe_images_endpoint(cfg)
    if not probe.get("has_image_endpoint"):
        return registry.update(
            job_id,
            status="failed",
            step="Hatch needs an image model.",
            error=probe.get("reason") or describe_hatch_backend().get("reason"),
            image_backend=probe.get("provider"),
        )
    registry.update(
        job_id,
        status="running",
        step="Imagining the main look.",
        image_backend=probe.get("provider"),
        error=None,
    )
    job_dir = registry.root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    complete = 0
    try:
        base_png = generate_png(hatch_prompt(job, "base", 1, "canonical identity"))
        write_generated(job_dir, "base", base_png)
        complete = 1
        registry.update(job_id, jobs_complete=complete, step="Picturing poses.")
        for kind, frames, action in ROW_SPECS:
            if kind == "running-left":
                # Deterministic mirror is applied after running-right extract in a later pass.
                # Generate a dedicated strip so a missing hatch-pet script still yields art.
                pass
            png = generate_png(
                hatch_prompt(job, kind, frames, action),
                size="1536x1024",
            )
            write_generated(job_dir, kind, png)
            complete += 1
            registry.update(job_id, jobs_complete=complete, step=f"Hatching {kind}.")
        (job_dir / "hatch-note.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "jobs_complete": complete,
                    "note": (
                        "Strips are saved. Assemble with hatch-pet scripts into an 8x11 "
                        "spritesheet.webp (spriteVersionNumber 2) before playback."
                    ),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return registry.update(
            job_id,
            status="complete",
            step="Hatching complete. Assembly/QA still required for v2 playback.",
            jobs_complete=complete,
        )
    except HatchImageError as exc:
        return registry.update(
            job_id,
            status="failed",
            step="Hatch stopped.",
            jobs_complete=complete,
            error=str(exc),
        )
