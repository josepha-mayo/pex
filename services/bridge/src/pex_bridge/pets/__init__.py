"""PEX starter pets.

Codex hatch-pets are v2 8x11 atlases (192x208 cells, spriteVersionNumber 2) with
rows: idle, running-right, running-left, waving, jumping, failed, waiting,
running (focused work), review, then 16 look directions.

Eight distinct starters (owl, tortoise, moth, hedgehog, axolotl, armadillo,
clay robot, and the user's original dark-navy cat Von). Production starters
resolve only from the bundled/repository asset tree; missing art stays
explicitly unavailable. Users can hatch or import separate custom pets from
Settings. Bundled starter art must be project-owned or user-owned.
"""

from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

CODEX_CELL_W = 192
CODEX_CELL_H = 208
CODEX_COLS = 8
CODEX_ROWS_V2 = 11
CODEX_ATLAS_W = CODEX_CELL_W * CODEX_COLS
CODEX_ATLAS_H = CODEX_CELL_H * CODEX_ROWS_V2
# Canonical Codex-v2 frames actually addressed by the desktop runtime. Every
# addressed frame must contain visible pixels and every unaddressed tail cell
# must be transparent. In particular, idle is six frames: pointer dead-zone
# rendering falls back to that loop and does not address row 0, column 6.
CODEX_REQUIRED_FRAMES = (6, 8, 8, 4, 5, 8, 6, 6, 6, 8, 8)
MAX_PET_MANIFEST_BYTES = 65_536
MAX_PET_SPRITESHEET_BYTES = 16 * 1024 * 1024
_PET_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_CATALOG_PET_ID = re.compile(r"^(?:import:)?[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result

CODEX_ROWS = [
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
    "look-9",
    "look-10",
]

PEX_TO_CODEX_ROW = {
    "idle": "idle",
    "observing": "review",
    "working": "running",
    "handoff": "waving",
    "drift": "running-right",
    "approved": "review",
    "warning": "failed",
    "decision": "waiting",
    "degraded": "failed",
}


def _repo_pets_dir() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(str(sys._MEIPASS)) / "pex_bridge" / "_bundled_pets"
    # services/bridge/src/pex_bridge/pets/__init__.py → repo root
    return Path(__file__).resolve().parents[5] / "apps" / "desktop" / "src" / "pets"


def resolve_spritesheet(pet_id: str) -> str | None:
    slug = pet_id.split(":", 1)[-1]
    if not _PET_ID.fullmatch(slug):
        return None
    path = _repo_pets_dir() / slug / "spritesheet.webp"
    try:
        stat = path.stat()
    except OSError:
        return None
    if _valid_v2_sheet(str(path), stat.st_size, stat.st_mtime_ns):
        return str(path)
    return None


def validate_codex_v2_atlas(image: Image.Image, *, subject: str = "spritesheet") -> None:
    """Validate geometry, alpha semantics, and every runtime-addressed cell."""

    if image.format != "WEBP":
        raise ValueError(f"{subject} must be a WebP image")
    if image.size != (CODEX_ATLAS_W, CODEX_ATLAS_H):
        raise ValueError(
            f"{subject} must be exactly {CODEX_ATLAS_W}x{CODEX_ATLAS_H} pixels"
        )
    if getattr(image, "n_frames", 1) != 1:
        raise ValueError(f"{subject} must be one static atlas image")
    if "A" not in image.getbands():
        raise ValueError(f"{subject} must preserve an alpha channel")

    # load() forces a complete decode; this is stronger than trusting headers
    # and lets the per-cell checks reject structurally blank atlases.
    image.load()
    alpha = image.getchannel("A")
    alpha_min, alpha_max = alpha.getextrema()
    if alpha_min == 255:
        raise ValueError(f"{subject} must contain transparent background pixels")
    if alpha_max == 0:
        raise ValueError(f"{subject} must contain visible pixels")
    for row, required_count in enumerate(CODEX_REQUIRED_FRAMES):
        for column in range(CODEX_COLS):
            bounds = (
                column * CODEX_CELL_W,
                row * CODEX_CELL_H,
                (column + 1) * CODEX_CELL_W,
                (row + 1) * CODEX_CELL_H,
            )
            visible = alpha.crop(bounds).getbbox() is not None
            if column < required_count and not visible:
                raise ValueError(
                    f"{subject} required frame {CODEX_ROWS[row]}[{column}] "
                    "must contain visible pixels"
                )
            if column >= required_count and visible:
                raise ValueError(
                    f"{subject} unused frame {CODEX_ROWS[row]}[{column}] "
                    "must be fully transparent"
                )


@lru_cache(maxsize=128)
def _valid_v2_sheet(path_value: str, size: int, modified_ns: int) -> bool:
    del modified_ns
    if size < 1 or size > MAX_PET_SPRITESHEET_BYTES:
        return False
    path = Path(path_value)
    try:
        if not path.is_file():
            return False
        with Image.open(path) as image:
            validate_codex_v2_atlas(image)
    except (ValueError, UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return False
    return True


class PetDefinition(BaseModel):
    id: str = Field(pattern=_CATALOG_PET_ID.pattern)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(max_length=4096)
    kind: str = Field(default="codex_v2", min_length=1, max_length=64)
    hue: int = Field(default=160, ge=-360, le=360)
    body: str = Field(default="#1de2a0", pattern=_HEX_COLOR.pattern)
    accent: str = Field(default="#9dffd8", pattern=_HEX_COLOR.pattern)
    eye: str = Field(default="#06251c", pattern=_HEX_COLOR.pattern)
    shape: str = Field(default="orb", min_length=1, max_length=64)
    species: str = Field(default="mascot", min_length=1, max_length=64)
    spritesheet: str | None = Field(default=None, max_length=4096)
    sprite_version: int | None = Field(default=2, ge=2, le=2)
    source: str = "starter"  # starter | imported | hatched
    atlas_ready: bool = False


class ImportedPet(BaseModel):
    id: str = Field(pattern=r"^import:[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=4096)
    directory: str = Field(max_length=4096)
    spritesheet: str = Field(max_length=4096)
    sprite_version: int = Field(default=2, ge=2, le=2)


class PetSettings(BaseModel):
    selected_id: str = Field(default="pex", min_length=1, max_length=128)
    custom_name: str = Field(default="", max_length=128)
    hue_shift: int = Field(default=0, ge=-360, le=360)
    scale: float = Field(default=1.0, ge=0.6, le=2.0)
    click_through: bool = False
    quiet: bool = True
    imported_codex_dir: str | None = Field(default=None, max_length=4096)
    imports: list[ImportedPet] = Field(default_factory=list, max_length=64)


STARTERS: list[PetDefinition] = [
    PetDefinition(
        id="pex",
        display_name="Pex",
        description="Quiet ink-navy plush owl. Watches workers, does not code.",
        shape="orb",
        species="owl",
        hue=160,
        body="#14b88a",
        accent="#9dffd8",
    ),
    PetDefinition(
        id="ledger",
        display_name="Ledger",
        description="Dusty teal plush tortoise with a tiny bound ledger. Remembers constraints.",
        shape="ledger",
        species="tortoise",
        hue=210,
        body="#3d7ea6",
        accent="#b7e3ff",
    ),
    PetDefinition(
        id="mesh",
        display_name="Mesh",
        description="Lavender plush moth courier with envelope-fold wing markings.",
        shape="mesh",
        species="moth",
        hue=265,
        body="#7a5cff",
        accent="#d7ccff",
    ),
    PetDefinition(
        id="nudge",
        display_name="Nudge",
        description="Amber plush hedgehog. A corrective tap, then quiet.",
        shape="nudge",
        species="hedgehog",
        hue=40,
        body="#e0a21b",
        accent="#ffe7a3",
    ),
    PetDefinition(
        id="drift",
        display_name="Drift",
        description="Coral plush axolotl. Lights up when a worker leaves the goal.",
        shape="pulse",
        species="axolotl",
        hue=0,
        body="#e25b4c",
        accent="#ffc4bc",
    ),
    PetDefinition(
        id="quiet",
        display_name="Quiet",
        description="Slate plush armadillo. Almost invisible until a real decision exists.",
        shape="quiet",
        species="armadillo",
        hue=200,
        body="#4b5a63",
        accent="#c5d0d6",
    ),
    PetDefinition(
        id="ember",
        display_name="Ember",
        description="Terracotta clay robot. Warm when a test is safe, still for danger.",
        shape="ember",
        species="robot",
        hue=20,
        body="#d96a2b",
        accent="#ffd0b0",
    ),
    PetDefinition(
        id="von",
        display_name="Von",
        description=(
            "Tiny dark-navy fluffy cat with moonlit accents and a laptop for focused work."
        ),
        shape="von",
        species="cat",
        hue=220,
        body="#101d3b",
        accent="#86b8ff",
    ),
]


def starters_by_id() -> dict[str, PetDefinition]:
    return {pet.id: pet for pet in STARTERS}


def _with_sheet(pet: PetDefinition) -> PetDefinition:
    sheet = pet.spritesheet or resolve_spritesheet(pet.id)
    if not sheet:
        return pet
    return pet.model_copy(update={"spritesheet": sheet, "atlas_ready": True})


def _validated_imported_sheet(imported: ImportedPet) -> str | None:
    try:
        root = Path(imported.directory).expanduser().resolve(strict=True)
        sheet = Path(imported.spritesheet).expanduser().resolve(strict=True)
        if not root.is_dir() or not sheet.is_file() or not sheet.is_relative_to(root):
            return None
        sheet_stat = sheet.stat()
    except (OSError, ValueError):
        return None
    if not _valid_v2_sheet(str(sheet), sheet_stat.st_size, sheet_stat.st_mtime_ns):
        return None
    return str(sheet)


def catalog(settings: PetSettings) -> list[PetDefinition]:
    items = [_with_sheet(pet) for pet in STARTERS]
    for imported in settings.imports:
        sheet = _validated_imported_sheet(imported)
        items.append(
            PetDefinition(
                id=imported.id,
                display_name=imported.display_name,
                description=imported.description or "Imported Codex v2 pet.",
                kind="codex_v2",
                spritesheet=sheet,
                sprite_version=imported.sprite_version,
                source="imported",
                shape="kit",
                atlas_ready=sheet is not None,
            )
        )
    return items


def catalog_by_id(settings: PetSettings) -> dict[str, PetDefinition]:
    return {pet.id: pet for pet in catalog(settings)}


def codex_row_index(pex_mood: str) -> int:
    row_name = PEX_TO_CODEX_ROW.get(pex_mood, "idle")
    try:
        return CODEX_ROWS.index(row_name)
    except ValueError:
        return 0


def maybe_import_codex_home(settings: PetSettings) -> PetSettings:
    """Pick up additional locally installed Codex v2 pets as custom imports."""
    root = Path.home() / ".codex" / "pets"
    if not root.is_dir():
        return settings
    known_ids = {item.id for item in settings.imports}
    starter_ids = set(starters_by_id())
    for folder in sorted(root.iterdir()):
        if len(settings.imports) >= 64:
            break
        if folder.name in starter_ids:
            continue
        if not (folder / "pet.json").is_file():
            continue
        try:
            imported = import_codex_pet(folder)
        except (FileNotFoundError, ValueError, OSError):
            continue
        if imported.id in known_ids:
            continue
        settings.imports.append(imported)
        known_ids.add(imported.id)
    return settings


def import_codex_pet(directory: str | Path) -> ImportedPet:
    """Read a Codex hatch-pet folder (pet.json + spritesheet.webp)."""
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"pet directory does not exist: {root}")
    try:
        manifest_path = (root / "pet.json").resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(f"no pet.json in {root}") from exc
    if not manifest_path.is_file() or not manifest_path.is_relative_to(root):
        raise FileNotFoundError(f"no pet.json in {root}")
    if manifest_path.stat().st_size > MAX_PET_MANIFEST_BYTES:
        raise ValueError("pet.json exceeds the 64 KiB safety bound")
    with manifest_path.open("rb") as handle:
        raw_manifest = handle.read(MAX_PET_MANIFEST_BYTES + 1)
    if len(raw_manifest) > MAX_PET_MANIFEST_BYTES:
        raise ValueError("pet.json exceeds the 64 KiB safety bound")
    try:
        data = json.loads(
            raw_manifest.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("pet.json must be valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("pet.json must contain an object")
    raw_version = data.get("spriteVersionNumber") or data.get("sprite_version") or 0
    if isinstance(raw_version, bool) or not isinstance(raw_version, (int, str)):
        raise ValueError("spriteVersionNumber must be the integer 2")
    try:
        version = int(raw_version)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("spriteVersionNumber must be the integer 2") from exc
    if isinstance(raw_version, str) and raw_version.strip() != "2":
        raise ValueError("spriteVersionNumber must be the integer 2")
    if version != 2:
        raise ValueError(f"PEX imports Codex spriteVersionNumber 2 only, got {version}")
    sheet_name = data.get("spritesheetPath") or "spritesheet.webp"
    if (
        not isinstance(sheet_name, str)
        or not sheet_name.strip()
        or len(sheet_name.encode("utf-8")) > 1024
        or any(ord(char) < 32 or ord(char) == 127 for char in sheet_name)
    ):
        raise ValueError("spritesheetPath must be a non-empty relative path")
    try:
        sheet = (root / sheet_name).resolve(strict=True)
    except (OSError, ValueError) as exc:
        raise FileNotFoundError(f"missing spritesheet {sheet_name}") from exc
    if not sheet.is_file():
        raise FileNotFoundError(f"missing spritesheet {sheet}")
    if not sheet.is_relative_to(root):
        raise ValueError("spritesheetPath must stay inside the pet directory")
    try:
        sheet_stat = sheet.stat()
    except OSError as exc:
        raise FileNotFoundError(f"missing spritesheet {sheet_name}") from exc
    size = sheet_stat.st_size
    if size < 1 or size > MAX_PET_SPRITESHEET_BYTES:
        raise ValueError("spritesheet.webp must be between 1 byte and 16 MiB")
    try:
        with Image.open(sheet) as image:
            validate_codex_v2_atlas(image)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("spritesheet is not a valid WebP image") from exc
    raw_id = data.get("id") or root.name
    if not isinstance(raw_id, str):
        raise ValueError("imported pet id must be text")
    pet_id = raw_id.strip()
    if not _PET_ID.fullmatch(pet_id):
        raise ValueError(
            "imported pet id must use 1-64 letters, numbers, dots, dashes, or underscores"
        )
    raw_display_name = data.get("displayName") or data.get("name") or pet_id
    raw_description = data.get("description") or ""
    if not isinstance(raw_display_name, str) or not isinstance(raw_description, str):
        raise ValueError("imported pet display name and description must be text")
    display_name = raw_display_name.strip()
    description = raw_description.strip()
    if (
        not display_name
        or len(display_name) > 128
        or "\r" in display_name
        or "\n" in display_name
        or "\x00" in display_name
    ):
        raise ValueError("imported pet display name must use 1-128 characters")
    if len(description) > 4096:
        raise ValueError("imported pet description must be at most 4096 characters")
    return ImportedPet(
        id=f"import:{pet_id}",
        display_name=display_name,
        description=description,
        directory=str(root),
        spritesheet=str(sheet),
        sprite_version=2,
    )
