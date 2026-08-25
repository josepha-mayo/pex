"""PEX starter pets.

Codex hatch-pets are v2 8x11 atlases (192x208 cells, spriteVersionNumber 2) with
rows: idle, running-right, running-left, waving, jumping, failed, waiting,
running (focused work), review, then 16 look directions.

PEX maps supervisor mood onto those same row names so a user can import a
Codex pet.json + spritesheet.webp, or use one of the ten built-in atlases.
We do not copy Codex built-in art.
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
    spritesheet: str | None = None
    sprite_version: int | None = 2
    source: str = "starter"  # starter | imported


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
        description="Default quiet supervisor orb. Watches, does not perform.",
        shape="orb",
        hue=160,
        body="#14b88a",
        accent="#9dffd8",
    ),
    PetDefinition(
        id="ledger",
        display_name="Ledger",
        description="Intent-ledger keeper. Calm, rectangular, remembers constraints.",
        shape="ledger",
        hue=210,
        body="#3d7ea6",
        accent="#b7e3ff",
    ),
    PetDefinition(
        id="mesh",
        display_name="Mesh",
        description="Context courier. Moves facts between harnesses, never dumps transcripts.",
        shape="mesh",
        hue=265,
        body="#7a5cff",
        accent="#d7ccff",
    ),
    PetDefinition(
        id="nudge",
        display_name="Nudge",
        description="Tiny corrective tap. Exists to say continue with evidence, then go quiet.",
        shape="nudge",
        hue=40,
        body="#e0a21b",
        accent="#ffe7a3",
    ),
    PetDefinition(
        id="drift",
        display_name="Drift",
        description="Trajectory watcher. Lights up only when the worker leaves the goal.",
        shape="pulse",
        hue=0,
        body="#e25b4c",
        accent="#ffc4bc",
    ),
    PetDefinition(
        id="quiet",
        display_name="Quiet",
        description="Attention broker. Almost invisible until a real decision exists.",
        shape="quiet",
        hue=200,
        body="#4b5a63",
        accent="#c5d0d6",
    ),
    PetDefinition(
        id="ember",
        display_name="Ember",
        description="Approval scout. Warm when a safe test is auto-allowed, still for danger.",
        shape="ember",
        hue=20,
        body="#d96a2b",
        accent="#ffd0b0",
    ),
    PetDefinition(
        id="spark",
        display_name="Spark",
        description="Verifier. Suspicious of 'done' until artifacts exist.",
        shape="spark",
        hue=55,
        body="#c9c22a",
        accent="#fff6a8",
    ),
    PetDefinition(
        id="bot",
        display_name="Bot",
        description="Small robot supervisor. Closest to a desktop companion, still not a chat UI.",
        shape="bot",
        hue=180,
        body="#2aa8b3",
        accent="#b6f3f7",
    ),
    PetDefinition(
        id="kit",
        display_name="Kit",
        description="Soft companion silhouette in the Codex hatch-pet spirit, original PEX art.",
        shape="kit",
        hue=230,
        body="#5a6dff",
        accent="#cfd4ff",
    ),
]


def starters_by_id() -> dict[str, PetDefinition]:
    return {pet.id: pet for pet in STARTERS}


def catalog(settings: PetSettings) -> list[PetDefinition]:
    items = list(STARTERS)
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
