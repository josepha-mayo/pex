"""Judge-safe recorded trajectories. Never presented as live control."""

from __future__ import annotations

import json
from pathlib import Path


def fixture_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "fixtures" / "demo"
        if candidate.is_dir():
            return candidate
    return Path.cwd() / "fixtures" / "demo"


def list_fixtures() -> list[dict]:
    items = []
    directory = fixture_dir()
    if not directory.is_dir():
        return items
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        items.append(
            {
                "id": data.get("id") or path.stem,
                "title": data.get("title") or path.stem,
                "replay": True,
                "not_live_control": True,
                "events": len(data.get("events") or []),
            }
        )
    return items


def load_fixture(fixture_id: str) -> dict:
    path = fixture_dir() / f"{fixture_id}.json"
    if not path.is_file():
        raise FileNotFoundError(fixture_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["replay"] = True
    data["not_live_control"] = True
    return data
