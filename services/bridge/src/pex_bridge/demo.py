"""Judge-safe recorded trajectories. Never presented as live control."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path, PurePosixPath
from typing import Any

MAX_DEMO_FIXTURE_BYTES = 1_048_576
MAX_DEMO_EVENTS = 1000
MAX_DEMO_WORKSPACE_FILES = 64
MAX_DEMO_WORKSPACE_FILE_BYTES = 65_536
MAX_DEMO_WORKSPACE_BYTES = 262_144
MAX_DEMO_MUTATIONS = 32
_FIXTURE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_WORKSPACE_RELPATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_WINDOWS_DEVICE_NAMES = {
    "con", "nul", "aux", "prn",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value!r} is not allowed")


def _finite_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number {value!r} is not allowed")
    return parsed


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _validated_relpath(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not _WORKSPACE_RELPATH.fullmatch(value)
        or "\\" in value
        or ":" in value
        or "//" in value
    ):
        raise ValueError("demo workspace paths must be relative POSIX paths")
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("demo workspace paths must be relative POSIX paths")
    if any(part.split(".")[0].lower() in _WINDOWS_DEVICE_NAMES for part in parts):
        raise ValueError("demo workspace paths must not use reserved device names")
    return "/".join(parts)


def _validated_workspace_files(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or len(value) > MAX_DEMO_WORKSPACE_FILES:
        raise ValueError("demo workspace files must be a bounded object")
    files: dict[str, str] = {}
    total = 0
    for raw_path, content in value.items():
        relpath = _validated_relpath(raw_path)
        if not isinstance(content, str):
            raise ValueError("demo workspace file content must be text")
        size = len(content.encode("utf-8"))
        if size > MAX_DEMO_WORKSPACE_FILE_BYTES:
            raise ValueError("demo workspace file exceeds the 64 KiB bound")
        total += size
        if total > MAX_DEMO_WORKSPACE_BYTES:
            raise ValueError("demo workspace exceeds the 256 KiB bound")
        if relpath in files:
            raise ValueError("demo workspace paths must be unique after normalization")
        files[relpath] = content
    return files


def _validated_workspace(value: Any, *, event_count: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("demo workspace must be an object")
    if not set(value).issubset({"files", "mutations"}):
        raise ValueError("demo workspace keys must be files and mutations")
    files = _validated_workspace_files(value.get("files") or {})
    mutations_value = value.get("mutations") or []
    if not isinstance(mutations_value, list) or len(mutations_value) > MAX_DEMO_MUTATIONS:
        raise ValueError("demo workspace mutations must be a bounded list")
    mutations = []
    for item in mutations_value:
        if not isinstance(item, dict) or not set(item).issubset(
            {"after", "files", "delete"}
        ):
            raise ValueError("demo workspace mutation must be {after, files, delete}")
        after = item.get("after")
        if (
            not isinstance(after, int)
            or isinstance(after, bool)
            or not 0 <= after < event_count
        ):
            raise ValueError("demo workspace mutation index must be an event index")
        deletes = item.get("delete") or []
        if not isinstance(deletes, list) or len(deletes) > MAX_DEMO_WORKSPACE_FILES:
            raise ValueError("demo workspace mutation deletes must be a bounded list")
        mutations.append(
            {
                "after": after,
                "files": _validated_workspace_files(item.get("files") or {}),
                "delete": [_validated_relpath(path) for path in deletes],
            }
        )
    return {"files": files, "mutations": mutations}


def _workspace_target(base: Path, relpath: str) -> Path:
    target = base.joinpath(*relpath.split("/"))
    if len(str(target)) > 240:
        raise ValueError("demo workspace path exceeds the filesystem bound")
    return target


def materialize_workspace(root: Path, files: dict[str, str]) -> None:
    """Write validated fixture files under a replay workspace root."""

    base = root.resolve()
    for relpath, content in files.items():
        target = _workspace_target(base, relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def remove_workspace_files(root: Path, relpaths: list[str]) -> None:
    """Delete validated fixture paths under a replay workspace root.

    Deleting a path that was never materialized is a fixture bug, not a
    no-op — it fails loudly so a recorded trajectory cannot pretend a
    tampered file was removed when it never existed.
    """

    base = root.resolve()
    for relpath in relpaths:
        target = _workspace_target(base, relpath)
        if not target.resolve().is_relative_to(base):
            raise ValueError("demo workspace delete must stay under the root")
        target.unlink()
        for parent in target.parents:
            if parent == base or not parent.is_relative_to(base):
                break
            try:
                parent.rmdir()
            except OSError:
                break


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
        item = {
            "id": data.get("id") or path.stem,
            "title": data.get("title") or path.stem,
            "replay": True,
            "not_live_control": True,
            "events": len(data.get("events") or []),
        }
        summary = data.get("summary")
        if isinstance(summary, str) and summary.strip():
            item["summary"] = summary.strip()[:240]
        captured = data.get("captured_from_live_session")
        if isinstance(captured, str) and captured:
            item["captured_from_live_session"] = captured
        items.append(item)
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
    return _parse_fixture_bytes(raw)


def parse_inline_fixture(data: dict) -> dict:
    """Validate a judge-supplied fixture body through the exact same gate a
    fixture file passes: the body is re-serialized to bytes and run through
    the strict parser (unique keys, finite numbers, shape + bounds)."""
    try:
        raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("demo fixture must be JSON-serializable") from exc
    return _parse_fixture_bytes(raw)


def _parse_fixture_bytes(raw: bytes) -> dict:
    if len(raw) > MAX_DEMO_FIXTURE_BYTES:
        raise ValueError("demo fixture exceeds the 1 MiB safety bound")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
            parse_float=_finite_json_float,
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
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
    if data.get("workspace") is not None:
        data["workspace"] = _validated_workspace(
            data["workspace"], event_count=len(events)
        )
    data["replay"] = True
    data["not_live_control"] = True
    return data
