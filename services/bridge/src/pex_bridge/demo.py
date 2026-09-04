"""Judge-safe recorded trajectories. Never presented as live control."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MAX_DEMO_FIXTURE_BYTES = 1_048_576
MAX_DEMO_EVENTS = 1000
_FIXTURE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


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
        try:
            data = load_fixture(path.stem)
        except (FileNotFoundError, ValueError, OSError):
            continue
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
    if not _FIXTURE_ID.fullmatch(fixture_id):
        raise ValueError("invalid demo fixture id")
    root = fixture_dir().resolve()
    try:
        path = (root / f"{fixture_id}.json").resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError(fixture_id) from exc
    if not path.is_file() or not path.is_relative_to(root):
        raise FileNotFoundError(fixture_id)
    if path.stat().st_size > MAX_DEMO_FIXTURE_BYTES:
        raise ValueError("demo fixture exceeds the 1 MiB safety bound")
    with path.open("rb") as handle:
        raw = handle.read(MAX_DEMO_FIXTURE_BYTES + 1)
    if len(raw) > MAX_DEMO_FIXTURE_BYTES:
        raise ValueError("demo fixture exceeds the 1 MiB safety bound")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("demo fixture must be valid UTF-8 JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("demo fixture must contain an object")
    events = data.get("events") or []
    if (
        not isinstance(events, list)
        or len(events) > MAX_DEMO_EVENTS
        or any(not isinstance(event, dict) for event in events)
    ):
        raise ValueError("demo fixture must contain at most 1000 event objects")
    if data.get("goal") is not None and not isinstance(data["goal"], dict):
        raise ValueError("demo fixture goal must be an object")
    data["replay"] = True
    data["not_live_control"] = True
    return data
