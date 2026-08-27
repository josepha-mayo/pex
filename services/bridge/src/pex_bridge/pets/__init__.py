"""PEX starter pets.

Codex hatch-pets are v2 8x11 atlases (192x208 cells, spriteVersionNumber 2) with
rows: idle, running-right, running-left, waving, jumping, failed, waiting,
running (focused work), review, then 16 look directions.

Seven distinct starters (owl, tortoise, moth, hedgehog, axolotl, armadillo,
clay robot). A hatched spritesheet.webp on disk replaces the procedural
fallback. Users can also hatch a new pet from Settings using the same
image-capable provider they configure for PEX. We do not copy Codex art.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

CODEX_CELL_W = 192
CODEX_CELL_H = 208
CODEX_COLS = 8
CODEX_ROWS_V2 = 11

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
    "approved": "jumping",
    "warning": "failed",
    "decision": "waiting",
    "degraded": "failed",
}


def _repo_pets_dir() -> Path:
    # services/bridge/src/pex_bridge/pets/__init__.py → repo root
    return Path(__file__).resolve().parents[5] / "apps" / "desktop" / "src" / "pets"


def resolve_spritesheet(pet_id: str) -> str | None:
    slug = pet_id.split(":", 1)[-1]
    candidates = [
        _repo_pets_dir() / slug / "spritesheet.webp",
        Path.home() / ".codex" / "pets" / slug / "spritesheet.webp",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


class PetDefinition(BaseModel):
    id: str
    display_name: str
    description: str
    kind: str = "codex_v2"
    hue: int = 160
    body: str = "#1de2a0"
    accent: str = "#9dffd8"
    eye: str = "#06251c"
    shape: str = "orb"
    species: str = "mascot"
    spritesheet: str | None = None
    sprite_version: int | None = 2
    source: str = "starter"  # starter | imported | hatched
    atlas_ready: bool = False


class ImportedPet(BaseModel):
    id: str
    display_name: str
    description: str = ""
    directory: str
    spritesheet: str
    sprite_version: int = 2


class PetSettings(BaseModel):
    selected_id: str = "pex"
    custom_name: str = ""
    hue_shift: int = 0
    scale: float = Field(default=1.0, ge=0.6, le=2.0)
    click_through: bool = False
    quiet: bool = True
    imported_codex_dir: str | None = None
    imports: list[ImportedPet] = Field(default_factory=list)


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
]


def starters_by_id() -> dict[str, PetDefinition]:
    return {pet.id: pet for pet in STARTERS}


def _with_sheet(pet: PetDefinition) -> PetDefinition:
    sheet = pet.spritesheet or resolve_spritesheet(pet.id)
    if not sheet:
        return pet
    return pet.model_copy(update={"spritesheet": sheet, "atlas_ready": True})


def catalog(settings: PetSettings) -> list[PetDefinition]:
    items = [_with_sheet(pet) for pet in STARTERS]
    for imported in settings.imports:
        items.append(
            PetDefinition(
                id=imported.id,
                display_name=imported.display_name,
                description=imported.description or "Imported Codex v2 pet.",
                kind="codex_v2",
                spritesheet=imported.spritesheet,
                sprite_version=imported.sprite_version,
                source="imported",
                shape="kit",
                atlas_ready=True,
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
    """Pick up a locally installed Codex v2 pet (Von, etc.) without copying art into git."""
    root = Path.home() / ".codex" / "pets"
    if not root.is_dir():
        return settings
    known_ids = {item.id for item in settings.imports}
    starter_ids = set(starters_by_id())
    for folder in sorted(root.iterdir()):
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
    manifest_path = root / "pet.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"no pet.json in {root}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = int(data.get("spriteVersionNumber") or data.get("sprite_version") or 0)
    if version != 2:
        raise ValueError(f"PEX imports Codex spriteVersionNumber 2 only, got {version}")
    sheet_name = data.get("spritesheetPath") or "spritesheet.webp"
    sheet = root / sheet_name
    if not sheet.is_file():
        raise FileNotFoundError(f"missing spritesheet {sheet}")
    pet_id = str(data.get("id") or root.name).strip()
    if not pet_id:
        raise ValueError("imported pet needs an id")
    return ImportedPet(
        id=f"import:{pet_id}",
        display_name=str(data.get("displayName") or data.get("name") or pet_id),
        description=str(data.get("description") or ""),
        directory=str(root),
        spritesheet=str(sheet),
        sprite_version=2,
    )
