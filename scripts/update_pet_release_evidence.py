#!/usr/bin/env python3
"""Regenerate the shipped two-pet evidence while retaining the eight-pet review archive."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from PIL import Image
from verify_pet_neutral_lineage import verify_lineage

SHIPPED_PET_IDS = ("pex", "von")
ARCHIVED_REVIEW_PET_IDS = ("pex", "ledger", "mesh", "nudge", "drift", "quiet", "ember", "von")
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
        "--source-commit",
        help="full Git commit containing the original atlases; later runs use the tracked receipt",
    )
    parser.add_argument(
        "--archive-source",
        type=Path,
        help="original audit release directory; import review bytes without attesting new reviews",
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
    archive_path = evidence_root / "review-archive.json"

    old_release = json.loads(release_path.read_text(encoding="utf-8"))
    old_reviews = json.loads(reviews_path.read_text(encoding="utf-8"))
    old_repair = json.loads(repair_path.read_text(encoding="utf-8"))
    report = verify_lineage(repo, args.source_commit or old_repair.get("source_commit"))
    report_by_id = {row["id"]: row for row in report["pets"]}
    old_release_by_id = {row["id"]: row for row in old_release.get("pets", [])}

    structural_pets: list[dict[str, Any]] = []
    release_pets: list[dict[str, Any]] = []
    direction_roots: dict[str, str] = {}
    sheet_hashes: list[str] = []
    contract_roots: list[str] = []

    for pet_id in ARCHIVED_REVIEW_PET_IDS:
        atlas_path = pets_root / pet_id / "spritesheet.webp"
        manifest_path = pets_root / pet_id / "pet.json"
        receipt = report_by_id.get(pet_id)
        old_entry = old_release_by_id.get(pet_id)
        if receipt is None:
            raise SystemExit(f"missing repair receipt for {pet_id}")
        current_sha = sha256_file(atlas_path)
        if (
            old_entry is not None
            and old_entry.get("spritesheet_sha256")
            not in {receipt.get("before_sha256"), receipt.get("after_sha256")}
        ) or (
            receipt.get("after_sha256") != current_sha
            or receipt.get("animation_pixels_unchanged") is not True
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
        structural_entry = (
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
        release_entry = (
            {
                "id": pet_id,
                "manifest_sha256": sha256_file(manifest_path),
                "spritesheet_sha256": current_sha,
            }
        )
        if pet_id in SHIPPED_PET_IDS:
            sheet_hashes.append(current_sha)
            contract_roots.append(contract_root)
            structural_pets.append(structural_entry)
            release_pets.append(release_entry)

    migrated_records = []
    old_before_hashes = {
        pet_id: report_by_id[pet_id]["before_sha256"] for pet_id in ARCHIVED_REVIEW_PET_IDS
    }
    records = old_reviews.get("records")
    if not isinstance(records, list) or len(records) != 24:
        raise SystemExit("prior independent direction records are incomplete")
    for index, row in enumerate(records):
        pet_id = ARCHIVED_REVIEW_PET_IDS[index // 3]
        if (
            not isinstance(row, list)
            or len(row) != 6
            or row[0] != pet_id
            or row[1] not in {old_before_hashes[pet_id], direction_roots[pet_id]}
        ):
            raise SystemExit(f"prior direction record lineage mismatch at index {index}")
        migrated_records.append([pet_id, direction_roots[pet_id], *row[2:]])

    if args.archive_source:

        def archived_file(path: Path, expected_sha: str | None = None) -> dict:
            data = path.read_bytes()
            sha = sha256_bytes(data)
            if expected_sha is not None and sha != expected_sha:
                raise ValueError(f"original review hash mismatch: {path.name}")
            return {"sha256": sha, "bytes": len(data), "content": data.decode("utf-8")}

        archived_pets = []
        for index, pet_id in enumerate(ARCHIVED_REVIEW_PET_IDS):
            original_binding = archived_file(args.archive_source / f"{pet_id}.json")
            original = json.loads(original_binding["content"])
            if original["shipped_sha256"] != report_by_id[pet_id]["before_sha256"]:
                raise ValueError(f"original source binding mismatch for {pet_id}")
            blind = []
            for worker in range(3):
                reference = original["blind_review"]["reviewers"][worker]
                record = migrated_records[index * 3 + worker]
                if reference["verdict_sha256"] != record[4]:
                    raise ValueError(f"original blind binding mismatch for {pet_id}")
                blind.append(
                    archived_file(
                        args.archive_source / "evidence" / f"{pet_id}-blind-{worker + 1}.json",
                        record[4],
                    )
                )
            validation = original["blind_review"]["validation"]
            final = original["final_visual"]["evidence"]
            archived_pets.append(
                {
                    "id": pet_id,
                    "source_binding": original_binding,
                    "blind_reviews": blind,
                    "blind_validation": archived_file(
                        args.archive_source / "evidence" / Path(validation["path"]).name,
                        validation["sha256"],
                    ),
                    "visual_review": archived_file(
                        args.archive_source / "evidence" / Path(final["path"]).name,
                        final["sha256"],
                    ),
                }
            )
        compact_write(archive_path, {"schema_version": 1, "pets": archived_pets})
    if not archive_path.is_file():
        raise SystemExit("inspectable original review archive is required")

    reviews = {
        "schema_version": 2,
        "record_kind": "archived-independent-direction-review-lineage",
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

    compact_write(repair_path, report)

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
        "review_kind": "historical-source-review-with-verified-neutral-copy",
        "review_provenance": {
            "canonical_records": binding(
                reviews_path, relative="release-evidence/independent-reviews.json"
            ),
            "neutral_repair": binding(repair_path, relative="release-evidence/neutral-repair.json"),
            "review_archive": binding(
                archive_path, relative="release-evidence/review-archive.json"
            ),
        },
        "pet_ids": list(SHIPPED_PET_IDS),
        "spritesheet_sha256": sheet_hashes,
        "contract_cell_hash_roots": contract_roots,
        "limitations": [
            "Historical reviews cover original static atlas frames, not current native playback.",
            "The old blank-neutral check is superseded by the independently verified neutral copy.",
            "No new human or independent visual approval is asserted by this generated record.",
            "Native runtime behavior and desktop integration require separate release "
            "smoke evidence.",
        ],
    }
    compact_write(visual_path, visual)

    release = {
        "schema_version": 4,
        "built_in_pet_ids": list(SHIPPED_PET_IDS),
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
