from __future__ import annotations

import importlib.util
from pathlib import Path

from PIL import Image


def _load_runtime_contract_module():
    script = Path(__file__).parents[2] / "scripts" / "pet_atlas_runtime_contract.py"
    spec = importlib.util.spec_from_file_location("pet_atlas_runtime_contract", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_standard_frame_export_is_pixel_exact_and_hash_bound(tmp_path: Path) -> None:
    contract = _load_runtime_contract_module()
    pet_root = tmp_path / "pex"
    pet_root.mkdir()
    atlas_path = pet_root / "spritesheet.webp"
    atlas = Image.new("RGBA", contract.ATLAS_SIZE, (0, 0, 0, 0))
    for row, required_count in enumerate(contract.REQUIRED_FRAMES):
        for column in range(required_count):
            left, top, right, bottom = contract._cell_bounds(row, column)
            cell = Image.new(
                "RGBA",
                (right - left, bottom - top),
                ((row * 19) % 256, (column * 31) % 256, 127, 255),
            )
            atlas.paste(cell, (left, top))
    atlas.save(atlas_path, "WEBP", lossless=True, exact=True)

    evidence_root = tmp_path / "evidence"
    receipt = contract.write_standard_frames(atlas_path, evidence_root / "frames")

    assert receipt["standard_frames"] == sum(contract.REQUIRED_FRAMES[:9]) == 57
    manifest_path = evidence_root / "frames" / "pex" / "frames-manifest.json"
    assert manifest_path.is_file()
    with Image.open(atlas_path) as opened:
        decoded = opened.convert("RGBA")
    for row, required_count in enumerate(contract.REQUIRED_FRAMES[:9]):
        for column in range(required_count):
            exported_path = (
                evidence_root
                / "frames"
                / "pex"
                / contract.ROW_NAMES[row]
                / f"{column:02d}.png"
            )
            with Image.open(exported_path) as opened:
                exported = opened.convert("RGBA")
            assert exported.tobytes() == decoded.crop(
                contract._cell_bounds(row, column)
            ).tobytes()

    for state in contract.STANDARD_ROW_NAMES:
        preview = evidence_root / "previews" / "pex" / f"{state}.gif"
        preview.parent.mkdir(parents=True, exist_ok=True)
        preview.write_bytes(b"GIF89a-current-evidence")
    retained = (
        evidence_root / "frame-review" / "pex.json",
        evidence_root / "contact-sheets" / "pex-runtime-contract.png",
        evidence_root / "direction-sheets" / "pex.png",
        evidence_root / "continuity" / "pex.json",
        evidence_root / "visual-qa.md",
    )
    for artifact in retained:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"retained-current-evidence")

    seal = contract.seal_current_evidence(
        evidence_root,
        pet_id="pex",
        atlas_path=atlas_path,
    )

    assert seal["source_atlas"]["sha256"] == contract._sha256(atlas_path)
    assert [preview["state"] for preview in seal["motion_previews"]] == list(
        contract.STANDARD_ROW_NAMES
    )
