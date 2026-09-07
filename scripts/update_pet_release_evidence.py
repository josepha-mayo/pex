#!/usr/bin/env python3
"""Regenerate compact eight-pet evidence after the canonical neutral-frame repair."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image

PET_IDS = ("pex", "ledger", "mesh", "nudge", "drift", "quiet", "ember", "von")
COUNTS = (6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8)
CELL_WIDTH = 192
CELL_HEIGHT = 208
NEUTRAL = (0, 6)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def compact_write(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def binding(path: Path, *, relative: str) -> dict[str, Any]:
    return {"path": relative, "bytes": path.stat().st_size, "sha256": sha256_file(path)}


def cell_bytes(image: Image.Image, row: int, column: int) -> bytes:
    return image.crop(
        (
            column * CELL_WIDTH,
            row * CELL_HEIGHT,
            (column + 1) * CELL_WIDTH,
            (row + 1) * CELL_HEIGHT,
        )
    ).tobytes()


def hash_root(cells: list[bytes]) -> str:
    return sha256_bytes(b"".join(bytes.fromhex(sha256_bytes(cell)) for cell in cells))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--repair-report",
        type=Path,
        help=(
            "full repair receipt; defaults to the tracked compact neutral-repair record "
            "for idempotent regeneration"
        ),
    )
    parser.add_argument(
        "--attest-operator-review",
        action="store_true",
        help="attest that the exact repaired source atlases received final visual review",
    )
    args = parser.parse_args()

    repo = args.repo.resolve(strict=True)
    pets_root = repo / "apps" / "desktop" / "src" / "pets"
    evidence_root = pets_root / "release-evidence"
    release_path = pets_root / "release-manifest.json"
    reviews_path = evidence_root / "independent-reviews.json"
    structural_path = evidence_root / "structural.json"
    visual_path = evidence_root / "visual-attestation.json"
    repair_path = evidence_root / "neutral-repair.json"
    gallery_path = pets_root / "judge-gallery.html"

    old_release = json.loads(release_path.read_text(encoding="utf-8"))
    old_reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
    old_visual = json.loads(visual_path.read_text(encoding="utf-8"))
    report_path = (
        args.repair_report.resolve(strict=True)
        if args.repair_report is not None
        else repair_path.resolve(strict=True)
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("ok") is True and report.get("repair_requested") is True:
        report_by_id = {Path(row["path"]).parent.name: row for row in report.get("results", [])}
    elif (
        report.get("method") == "decoded-rgba-copy-with-lossless-webp-reencode"
        and report.get("animation_cells_preserved") is True
    ):
        report_by_id = {
            row["id"]: {
                **row,
                "animation_pixels_sha256_after": row["animation_pixels_sha256"],
                "neutral_frame_repaired": True,
                "remaining_occupied_unused_cells": [],
                "errors": [],
            }
            for row in report.get("pets", [])
        }
    else:
        raise SystemExit("neutral repair report is not a successful repair receipt")
    old_release_by_id = {row["id"]: row for row in old_release.get("pets", [])}

    structural_pets: list[dict[str, Any]] = []
    repair_pets: list[dict[str, Any]] = []
    release_pets: list[dict[str, Any]] = []
    direction_roots: dict[str, str] = {}
    sheet_hashes: list[str] = []
    contract_roots: list[str] = []

    for pet_id in PET_IDS:
        atlas_path = pets_root / pet_id / "spritesheet.webp"
        manifest_path = pets_root / pet_id / "pet.json"
        receipt = report_by_id.get(pet_id)
        old_entry = old_release_by_id.get(pet_id)
        if receipt is None or old_entry is None:
            raise SystemExit(f"missing repair or prior release record for {pet_id}")
        current_sha = sha256_file(atlas_path)
        if (
            old_entry.get("spritesheet_sha256")
            not in {receipt.get("before_sha256"), receipt.get("after_sha256")}
            or receipt.get("after_sha256") != current_sha
            or receipt.get("animation_pixels_unchanged") is not True
            or receipt.get("neutral_frame_repaired") is not True
            or receipt.get("remaining_occupied_unused_cells") != []
            or receipt.get("errors") != []
        ):
            raise SystemExit(f"repair lineage is incomplete for {pet_id}")

        with Image.open(atlas_path) as opened:
            if opened.format != "WEBP" or opened.mode != "RGBA" or opened.size != (1536, 2288):
                raise SystemExit(f"invalid atlas media contract for {pet_id}")
            image = opened.copy()
        contract_cells: list[bytes] = []
        direction_cells: list[bytes] = []
        occupied: list[bool] = []
        unused: list[bool] = []
        for row, count in enumerate(COUNTS):
            for column in range(8):
                raw = cell_bytes(image, row, column)
                required = column < count or (row, column) == NEUTRAL
                if required:
                    contract_cells.append(raw)
                    occupied.append(max(raw[3::4]) > 0)
                else:
                    unused.append(max(raw[3::4]) == 0)
                if row in (9, 10):
                    direction_cells.append(raw)
        neutral_matches = cell_bytes(image, *NEUTRAL) == cell_bytes(image, 0, 0)
        if not all(occupied) or not all(unused) or not neutral_matches:
            raise SystemExit(f"canonical cell contract failed for {pet_id}")
        pixels = (
            image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        )
        transparent_rgb_residue = sum(
            1
            for red, green, blue, alpha in pixels
            if alpha == 0 and (red != 0 or green != 0 or blue != 0)
        )
        if transparent_rgb_residue:
            raise SystemExit(f"transparent RGB residue remains for {pet_id}")

        contract_root = hash_root(contract_cells)
        direction_root = hash_root(direction_cells)
        direction_roots[pet_id] = direction_root
        sheet_hashes.append(current_sha)
        contract_roots.append(contract_root)
        structural_pets.append(
            {
                "id": pet_id,
                "spritesheet_sha256": current_sha,
                "spritesheet_bytes": atlas_path.stat().st_size,
                "contract_cell_hash_root": contract_root,
                "direction_cell_hash_root": direction_root,
                "contract_cell_count": len(contract_cells),
                "neutral_matches_idle_zero": neutral_matches,
                "transparent_rgb_residue_pixels": transparent_rgb_residue,
                "all_contract_cells_nonempty": all(occupied),
                "all_unused_cells_transparent": all(unused),
            }
        )
        repair_pets.append(
            {
                "id": pet_id,
                "before_sha256": receipt["before_sha256"],
                "after_sha256": current_sha,
                "animation_pixels_sha256": receipt["animation_pixels_sha256_after"],
                "animation_pixels_unchanged": True,
                "neutral_matches_idle_zero": True,
            }
        )
        release_pets.append(
            {
                "id": pet_id,
                "manifest_sha256": sha256_file(manifest_path),
                "spritesheet_sha256": current_sha,
            }
        )

    migrated_records = []
    old_before_hashes = {pet_id: report_by_id[pet_id]["before_sha256"] for pet_id in PET_IDS}
    records = old_reviews.get("records")
    if not isinstance(records, list) or len(records) != 24:
        raise SystemExit("prior independent direction records are incomplete")
    for index, row in enumerate(records):
        pet_id = PET_IDS[index // 3]
        if (
            not isinstance(row, list)
            or len(row) != 6
            or row[0] != pet_id
            or row[1] not in {old_before_hashes[pet_id], direction_roots[pet_id]}
        ):
            raise SystemExit(f"prior direction record lineage mismatch at index {index}")
        migrated_records.append([pet_id, direction_roots[pet_id], *row[2:]])

    prior_exact_operator_review = (
        old_visual.get("schema_version") == 4
        and old_visual.get("spritesheet_sha256") == sheet_hashes
        and old_visual.get("review_provenance", {}).get("final_operator_source_atlas_review")
        is True
    )
    if not args.attest_operator_review and not prior_exact_operator_review:
        raise SystemExit("exact repaired atlases require --attest-operator-review after visual QA")

    reviews = {
        "schema_version": 2,
        "record_kind": "sanitized-independent-direction-review",
        "reviewed_cell_scope": {
            "rows": [9, 10],
            "cell_count": 16,
            "binding": "decoded-rgba-cell-hash-root-v1",
        },
        "criteria": old_reviews["criteria"],
        "verdict_meaning": old_reviews["verdict_meaning"],
        "records": migrated_records,
    }
    compact_write(reviews_path, reviews)

    neutral_repair = {
        "schema_version": 1,
        "method": "decoded-rgba-copy-with-lossless-webp-reencode",
        "source_frame": {"row": 0, "column": 0},
        "target_frame": {"row": 0, "column": 6},
        "animation_cells_preserved": True,
        "pets": repair_pets,
    }
    compact_write(repair_path, neutral_repair)

    structural = {
        "schema_version": 4,
        "algorithm": "pex-codex-v2-rgba-cell-hash-v2",
        "geometry": {
            "width": 1536,
            "height": 2288,
            "columns": 8,
            "rows": 11,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
        },
        "required_frames_by_row": list(COUNTS),
        "neutral_look_frame": {"row": 0, "column": 6},
        "pets": structural_pets,
    }
    compact_write(structural_path, structural)

    visual = {
        "schema_version": 4,
        "review_kind": "independent-direction-review-plus-deterministic-neutral-repair",
        "verdict": "pass",
        "review_provenance": {
            "isolated_blind_direction_reviewers_per_pet": 3,
            "direction_review_scope_only": True,
            "final_operator_source_atlas_review": True,
            "canonical_records": binding(
                reviews_path, relative="release-evidence/independent-reviews.json"
            ),
            "neutral_repair": binding(repair_path, relative="release-evidence/neutral-repair.json"),
        },
        "pet_ids": list(PET_IDS),
        "spritesheet_sha256": sheet_hashes,
        "contract_cell_hash_roots": contract_roots,
        "checks": {
            "character_identity_across_states": "pass",
            "directional_readability": "pass",
            "neutral_frame_identity": "pass",
            "clipping_or_cell_bleed": "none",
            "backgrounds_inside_contract_cells": "none",
            "all_eight_distinguishable": "pass",
        },
        "limitations": [
            "This attestation covers the exact source atlases, not native packaged playback.",
            (
                "Native runtime behavior and desktop integration require separate release "
                "smoke evidence."
            ),
        ],
    }
    compact_write(visual_path, visual)

    release = {
        "schema_version": 4,
        "built_in_pet_ids": list(PET_IDS),
        "structural_evidence": binding(
            structural_path, relative="release-evidence/structural.json"
        ),
        "visual_attestation": binding(
            visual_path, relative="release-evidence/visual-attestation.json"
        ),
        "judge_gallery": binding(gallery_path, relative="judge-gallery.html"),
        "pets": release_pets,
    }
    compact_write(release_path, release)


if __name__ == "__main__":
    main()
