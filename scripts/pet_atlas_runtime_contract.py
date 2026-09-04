#!/usr/bin/env python3
"""Audit or repair Codex-v2 atlases against the frames the runtime addresses.

The current Codex and PEX renderers animate the standard-row frame counts
declared below and use all sixteen cells in rows 9-10 for pointer look. Cells
outside that contract must be transparent. Repair mode clears only those
unaddressed cells and proves that every runtime-addressed decoded pixel remains
identical before replacing the lossless WebP.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

COLUMNS = 8
ROWS = 11
CELL_WIDTH = 192
CELL_HEIGHT = 208
ATLAS_SIZE = (COLUMNS * CELL_WIDTH, ROWS * CELL_HEIGHT)
REQUIRED_FRAMES = (6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8)
ROW_NAMES = (
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
    "look-000-to-157.5",
    "look-180-to-337.5",
)
STANDARD_ROW_NAMES = ROW_NAMES[:9]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.name


def _cell_bounds(row: int, column: int) -> tuple[int, int, int, int]:
    return (
        column * CELL_WIDTH,
        row * CELL_HEIGHT,
        (column + 1) * CELL_WIDTH,
        (row + 1) * CELL_HEIGHT,
    )


def _runtime_pixels_sha256(image: Image.Image) -> str:
    digest = hashlib.sha256()
    for row, required_count in enumerate(REQUIRED_FRAMES):
        for column in range(required_count):
            digest.update(image.crop(_cell_bounds(row, column)).tobytes())
    return digest.hexdigest()


def _checker(size: tuple[int, int], square: int = 12) -> Image.Image:
    background = Image.new("RGB", size, "#ffffff")
    draw = ImageDraw.Draw(background)
    for y in range(0, size[1], square):
        for x in range(0, size[0], square):
            if (x // square + y // square) % 2:
                draw.rectangle((x, y, x + square - 1, y + square - 1), fill="#e8e8e8")
    return background


def write_runtime_contact_sheet(atlas_path: Path, output: Path, *, scale: float = 0.5) -> None:
    with Image.open(atlas_path) as opened:
        atlas = opened.convert("RGBA")
    cell_width = round(CELL_WIDTH * scale)
    cell_height = round(CELL_HEIGHT * scale)
    label_height = 24
    sheet = Image.new(
        "RGB",
        (COLUMNS * cell_width, ROWS * (cell_height + label_height)),
        "#f7f7f7",
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for row, required_count in enumerate(REQUIRED_FRAMES):
        y = row * (cell_height + label_height)
        draw.rectangle((0, y, sheet.width, y + label_height - 1), fill="#111111")
        draw.text(
            (6, y + 6),
            f"row {row}: {ROW_NAMES[row]} | {required_count} runtime frames",
            fill="#ffffff",
            font=font,
        )
        for column in range(COLUMNS):
            cell = atlas.crop(_cell_bounds(row, column)).resize(
                (cell_width, cell_height),
                Image.Resampling.LANCZOS,
            )
            background = _checker((cell_width, cell_height))
            background.paste(cell, (0, 0), cell)
            x = column * cell_width
            sheet.paste(background, (x, y + label_height))
            used = column < required_count
            draw.rectangle(
                (
                    x,
                    y + label_height,
                    x + cell_width - 1,
                    y + label_height + cell_height - 1,
                ),
                outline="#18a058" if used else "#6b7280",
                width=2,
            )
            draw.text(
                (x + 4, y + label_height + 4),
                f"{column}{'' if used else ' unused'}",
                fill="#111111",
                font=font,
            )
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, "PNG")


def write_standard_frames(atlas_path: Path, output_root: Path) -> dict[str, Any]:
    """Extract the exact runtime-addressed standard cells for motion QA.

    This is deliberately a decoded-atlas export, not a reconstruction step:
    each PNG is the unmodified RGBA pixel payload of one shipped cell.  The
    per-frame hashes make the preview lineage independently checkable.
    """

    with Image.open(atlas_path) as opened:
        atlas = opened.convert("RGBA")
    pet_root = output_root / atlas_path.parent.name
    rows: list[dict[str, Any]] = []
    standard_rows = zip(STANDARD_ROW_NAMES, REQUIRED_FRAMES[:9], strict=True)
    for row, (state, required_count) in enumerate(standard_rows):
        state_root = pet_root / state
        state_root.mkdir(parents=True, exist_ok=True)
        frames: list[dict[str, Any]] = []
        for column in range(required_count):
            frame = atlas.crop(_cell_bounds(row, column))
            frame_path = state_root / f"{column:02d}.png"
            frame.save(frame_path, "PNG")
            frames.append(
                {
                    "column": column,
                    "path": _display_path(frame_path.resolve()),
                    "rgba_sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
                    "png_sha256": _sha256(frame_path),
                }
            )
        rows.append(
            {
                "state": state,
                "row": row,
                "method": "atlas-cell-exact",
                "frames": frames,
            }
        )
    manifest = {
        "schema_version": 1,
        "source_atlas": _display_path(atlas_path),
        "source_atlas_sha256": _sha256(atlas_path),
        "cell_width": CELL_WIDTH,
        "cell_height": CELL_HEIGHT,
        "rows": rows,
    }
    manifest_path = pet_root / "frames-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {
        "root": _display_path(pet_root.resolve()),
        "manifest": _display_path(manifest_path.resolve()),
        "standard_frames": sum(REQUIRED_FRAMES[:9]),
    }


def _sealed_artifact(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"evidence artifact is not a regular file: {resolved}")
    return {
        "path": _display_path(resolved),
        "sha256": _sha256(resolved),
        "bytes": resolved.stat().st_size,
    }


def seal_current_evidence(
    evidence_root: Path,
    *,
    pet_id: str,
    atlas_path: Path,
) -> dict[str, Any]:
    """Hash-bind every retained current-asset QA artifact for one pet."""

    preview_root = evidence_root / "previews" / pet_id
    previews = [
        {
            "state": state,
            **_sealed_artifact(preview_root / f"{state}.gif"),
        }
        for state in STANDARD_ROW_NAMES
    ]
    frame_manifest_path = evidence_root / "frames" / pet_id / "frames-manifest.json"
    frame_manifest = json.loads(frame_manifest_path.read_text(encoding="utf-8"))
    atlas_sha256 = _sha256(atlas_path.resolve(strict=True))
    if frame_manifest.get("source_atlas_sha256") != atlas_sha256:
        raise ValueError(f"standard frame manifest is stale for {pet_id}")
    return {
        "schema_version": 1,
        "pet_id": pet_id,
        "source_atlas": _sealed_artifact(atlas_path),
        "standard_frame_manifest": _sealed_artifact(frame_manifest_path),
        "frame_review": _sealed_artifact(evidence_root / "frame-review" / f"{pet_id}.json"),
        "contact_sheet": _sealed_artifact(
            evidence_root / "contact-sheets" / f"{pet_id}-runtime-contract.png"
        ),
        "direction_sheet": _sealed_artifact(
            evidence_root / "direction-sheets" / f"{pet_id}.png"
        ),
        "continuity": _sealed_artifact(evidence_root / "continuity" / f"{pet_id}.json"),
        "independent_visual_qa": _sealed_artifact(evidence_root / "visual-qa.md"),
        "motion_previews": previews,
    }


def _inspect(image: Image.Image) -> tuple[list[dict[str, int]], list[str]]:
    occupied_unused: list[dict[str, int]] = []
    errors: list[str] = []
    alpha = image.getchannel("A")
    for row, required_count in enumerate(REQUIRED_FRAMES):
        for column in range(COLUMNS):
            cell = alpha.crop(_cell_bounds(row, column))
            visible_pixels = sum(cell.histogram()[1:])
            if column < required_count and visible_pixels == 0:
                errors.append(f"required frame row {row} column {column} is empty")
            elif column >= required_count and visible_pixels:
                occupied_unused.append(
                    {
                        "row": row,
                        "column": column,
                        "nontransparent_pixels": visible_pixels,
                    }
                )
    return occupied_unused, errors


def audit_or_repair(path: Path, *, repair: bool) -> dict[str, Any]:
    path = path.resolve(strict=True)
    before_sha256 = _sha256(path)
    with Image.open(path) as opened:
        source_format = opened.format
        source_mode = opened.mode
        frame_count = getattr(opened, "n_frames", 1)
        image = opened.convert("RGBA")
    errors: list[str] = []
    if source_format != "WEBP":
        errors.append(f"expected WEBP, got {source_format}")
    if image.size != ATLAS_SIZE:
        errors.append(f"expected {ATLAS_SIZE[0]}x{ATLAS_SIZE[1]}, got {image.width}x{image.height}")
    if frame_count != 1:
        errors.append(f"expected one static frame, got {frame_count}")
    if "A" not in source_mode:
        errors.append("source image does not preserve an alpha channel")
    if errors:
        return {
            "path": _display_path(path),
            "ok": False,
            "repaired": False,
            "before_sha256": before_sha256,
            "errors": errors,
        }

    occupied_unused, contract_errors = _inspect(image)
    runtime_pixels_before = _runtime_pixels_sha256(image)
    if contract_errors:
        return {
            "path": _display_path(path),
            "ok": False,
            "repaired": False,
            "before_sha256": before_sha256,
            "runtime_pixels_sha256": runtime_pixels_before,
            "occupied_unused_cells": occupied_unused,
            "errors": contract_errors,
        }

    repaired = bool(repair and occupied_unused)
    if repaired:
        clear = Image.new("RGBA", (CELL_WIDTH, CELL_HEIGHT), (0, 0, 0, 0))
        for cell in occupied_unused:
            image.paste(clear, _cell_bounds(cell["row"], cell["column"]))
        temporary = path.with_name(f".{path.name}.runtime-contract.tmp")
        try:
            image.save(temporary, "WEBP", lossless=True, method=6, exact=True)
            with Image.open(temporary) as reopened:
                repaired_image = reopened.convert("RGBA")
            runtime_pixels_after = _runtime_pixels_sha256(repaired_image)
            remaining_unused, repaired_errors = _inspect(repaired_image)
            if runtime_pixels_after != runtime_pixels_before:
                raise RuntimeError("repair changed runtime-addressed decoded pixels")
            if repaired_errors or remaining_unused:
                raise RuntimeError(
                    "repair did not produce the exact required/transparent cell contract"
                )
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    after_sha256 = _sha256(path)
    with Image.open(path) as final_opened:
        final_image = final_opened.convert("RGBA")
    remaining_unused, final_errors = _inspect(final_image)
    runtime_pixels_after = _runtime_pixels_sha256(final_image)
    return {
        "path": _display_path(path),
        "ok": not final_errors and not remaining_unused,
        "repaired": repaired,
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "runtime_pixels_sha256_before": runtime_pixels_before,
        "runtime_pixels_sha256_after": runtime_pixels_after,
        "runtime_pixels_unchanged": runtime_pixels_before == runtime_pixels_after,
        "cleared_unused_cells": occupied_unused if repaired else [],
        "remaining_occupied_unused_cells": remaining_unused,
        "errors": final_errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("atlases", nargs="+", type=Path)
    parser.add_argument("--repair-unused", action="store_true")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--contact-sheet-dir", type=Path)
    parser.add_argument("--standard-frames-dir", type=Path)
    parser.add_argument(
        "--seal-current-evidence-root",
        type=Path,
        help=(
            "Require and hash-bind current contact, direction, continuity, frame, "
            "and preview evidence."
        ),
    )
    args = parser.parse_args()

    results = []
    for atlas in args.atlases:
        result = audit_or_repair(atlas, repair=args.repair_unused)
        if args.contact_sheet_dir is not None and result["ok"]:
            output = args.contact_sheet_dir / f"{atlas.parent.name}-runtime-contract.png"
            write_runtime_contact_sheet(atlas.resolve(strict=True), output.resolve())
            result["contact_sheet"] = _display_path(output.resolve())
        if args.standard_frames_dir is not None and result["ok"]:
            result["standard_frames"] = write_standard_frames(
                atlas.resolve(strict=True),
                args.standard_frames_dir.resolve(),
            )
        if args.seal_current_evidence_root is not None and result["ok"]:
            evidence_root = args.seal_current_evidence_root.resolve(strict=True)
            result["current_evidence"] = seal_current_evidence(
                evidence_root,
                pet_id=atlas.parent.name,
                atlas_path=atlas.resolve(strict=True),
            )
        results.append(result)
    report = {
        "schema_version": 1,
        "contract": {
            "columns": COLUMNS,
            "rows": ROWS,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "required_frames_by_row": list(REQUIRED_FRAMES),
            "unused_cells_fully_transparent": True,
        },
        "repair_requested": args.repair_unused,
        "ok": all(item["ok"] for item in results),
        "results": results,
    }
    encoded = json.dumps(report, indent=2) + "\n"
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
