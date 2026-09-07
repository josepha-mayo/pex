"""Recompute neutral-slot repair lineage from immutable Git atlas blobs.

This proves a pixel-preserving transformation, not visual or human approval.
The historical commit must exist locally; no network or model calls are made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image

PET_IDS = ("pex", "ledger", "mesh", "nudge", "drift", "quiet", "ember", "von")
COUNTS = (6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8)
BASELINE_COMMIT = "638542c522e01adfa9705b4704701975dfe0237d"


def animation_digest(image: Image.Image) -> str:
    digest = hashlib.sha256()
    for row, count in enumerate(COUNTS):
        for column in range(count):
            digest.update(
                image.crop((column * 192, row * 208, (column + 1) * 192, (row + 1) * 208)).tobytes()
            )
    return digest.hexdigest()


def verify_pair(before: bytes, after: bytes) -> dict:
    """Reject changed animation pixels even when receipt assertions say pass."""
    images = []
    for data in (before, after):
        with Image.open(BytesIO(data)) as opened:
            if opened.format != "WEBP" or opened.mode != "RGBA" or opened.size != (1536, 2288):
                raise ValueError("invalid atlas media contract")
            images.append(opened.copy())
    old, current = images
    before_digest, after_digest = map(animation_digest, images)
    if before_digest != after_digest:
        raise ValueError("animation pixels changed")
    neutral_box = (6 * 192, 0, 7 * 192, 208)
    if old.crop(neutral_box).getchannel("A").getbbox() is not None:
        raise ValueError("historical neutral slot was not empty")
    neutral_matches = (
        current.crop(neutral_box).tobytes() == current.crop((0, 0, 192, 208)).tobytes()
    )
    if not neutral_matches:
        raise ValueError("neutral slot does not exactly match idle zero")
    # Prove the complete transformation, not only selected animation cells.
    old.paste(old.crop((0, 0, 192, 208)), neutral_box)
    if old.tobytes() != current.tobytes():
        raise ValueError("pixels outside the neutral copy changed")
    return {
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(),
        "animation_pixels_sha256_before": before_digest,
        "animation_pixels_sha256_after": after_digest,
        "animation_pixels_unchanged": before_digest == after_digest,
        "neutral_matches_idle_zero": neutral_matches,
    }


def verify_lineage(repo: Path, source_commit: str) -> dict:
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("neutral lineage requires a full immutable Git commit")
    if source_commit != BASELINE_COMMIT:
        raise ValueError("neutral lineage must use the canonical baseline commit")
    resolved = subprocess.check_output(
        ["git", "rev-parse", "--verify", f"{source_commit}^{{commit}}"],
        cwd=repo,
        text=True,
    ).strip()
    if resolved != source_commit:
        raise ValueError("source commit did not resolve exactly")
    pets = []
    for pet_id in PET_IDS:
        relative = f"apps/desktop/src/pets/{pet_id}/spritesheet.webp"
        before = subprocess.check_output(["git", "show", f"{source_commit}:{relative}"], cwd=repo)
        pets.append({"id": pet_id, **verify_pair(before, (repo / relative).read_bytes())})
    return {
        "schema_version": 2,
        "source_commit": source_commit,
        "method": "git-blob-decoded-rgba-neutral-copy-v1",
        "source_frame": {"row": 0, "column": 0},
        "target_frame": {"row": 0, "column": 6},
        "animation_cells_preserved": all(pet["animation_pixels_unchanged"] for pet in pets),
        "pets": pets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source-commit")
    parser.add_argument("--verify", type=Path, help="compare every field with a tracked receipt")
    args = parser.parse_args()
    expected = json.loads(args.verify.read_text(encoding="utf-8")) if args.verify else None
    result = verify_lineage(
        args.repo.resolve(strict=True), args.source_commit or (expected or {}).get("source_commit")
    )
    if expected is not None and result != expected:
        raise SystemExit("neutral repair receipt differs from independent Git/pixel recomputation")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
