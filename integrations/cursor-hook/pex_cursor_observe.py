"""Fail-open Cursor observer. Never waits on the bridge.

Cursor waits for this process to exit. Compact and drop a JSONL line as soon as
conversation_id is visible, then drain remaining stdin. Policy gates belong
in the opt-in control helper.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

MAX_PREFIX_BYTES = 65_536
MAX_DRAIN_BYTES = 4_194_304
MAX_LINE_BYTES = 16_384
_CONVERSATION = re.compile(rb'"conversation_id"\s*:\s*"([^"\\]{1,128})"')
_GENERATION = re.compile(rb'"generation_id"\s*:\s*"([^"\\]{1,128})"')
_FILE_PATH = re.compile(rb'"file_path"\s*:\s*"((?:\\.|[^"\\]){1,4096})"')
_COMMAND = re.compile(rb'"command"\s*:\s*"((?:\\.|[^"\\]){0,4096})"')
_CWD = re.compile(rb'"cwd"\s*:\s*"((?:\\.|[^"\\]){1,4096})"')
_WORKSPACE = re.compile(rb'"workspace"\s*:\s*"((?:\\.|[^"\\]){1,4096})"')
_WORKSPACE_ROOT = re.compile(
    rb'"workspace_roots"\s*:\s*\[\s*"((?:\\.|[^"\\]){1,4096})"'
)
_PERMISSION = {
    "preToolUse",
    "beforeShellExecution",
    "beforeMCPExecution",
    "beforeReadFile",
}
_KEEP = (
    "hook_event_name",
    "conversation_id",
    "generation_id",
    "composer_id",
    "session_id",
    "cwd",
    "workspace",
    "workspace_roots",
    "file_path",
    "command",
    "tool_name",
    "status",
    "model",
    "cursor_version",
)


def inbox_path(home: Path | None = None) -> Path:
    root = home or Path(os.environ.get("PEX_HOME") or (Path.home() / ".pex"))
    return root / "hooks" / "cursor.jsonl"


def fail_open_stdout(event: str) -> str:
    if event == "beforeSubmitPrompt":
        return '{"continue":true}'
    if event in _PERMISSION:
        return '{"permission":"allow"}'
    return "{}"


def compact_payload(payload: dict, event: str) -> dict:
    compact: dict = {}
    for key in _KEEP:
        if key not in payload:
            continue
        value = payload[key]
        if key == "workspace_roots":
            if isinstance(value, list):
                compact[key] = [str(item)[:4_096] for item in value[:8] if item]
            continue
        if isinstance(value, str) and value:
            compact[key] = value[:4_096]
    if not compact.get("hook_event_name"):
        compact["hook_event_name"] = event
    return compact


def extract_ids(raw: bytes, into: dict) -> None:
    if "conversation_id" not in into:
        match = _CONVERSATION.search(raw)
        if match:
            into["conversation_id"] = match.group(1).decode("ascii", "ignore")
    if "generation_id" not in into:
        match = _GENERATION.search(raw)
        if match:
            into["generation_id"] = match.group(1).decode("ascii", "ignore")
    if "file_path" not in into:
        match = _FILE_PATH.search(raw)
        if match:
            into["file_path"] = _json_string(match.group(1))
    if "command" not in into:
        match = _COMMAND.search(raw)
        if match:
            into["command"] = _json_string(match.group(1))
    if "cwd" not in into:
        match = _CWD.search(raw) or _WORKSPACE.search(raw)
        if match:
            into["cwd"] = _json_string(match.group(1))
    if "workspace_roots" not in into:
        match = _WORKSPACE_ROOT.search(raw)
        if match:
            into["workspace_roots"] = [_json_string(match.group(1))]


def _json_string(raw: bytes) -> str:
    try:
        return json.loads(b'"' + raw + b'"')[:4_096]
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return raw.decode("utf-8", "ignore")[:4_096]


def drop_payload(payload: dict, *, home: Path | None = None) -> None:
    path = inbox_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**payload, "observed_ns": time.time_ns()}
    line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    encoded = line.encode("utf-8")
    if len(encoded) > MAX_LINE_BYTES:
        return
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)


def _read_stream(stream, size: int):
    chunk = stream.read(size)
    if isinstance(chunk, str):
        return chunk.encode("utf-8")
    return chunk or b""


def observe_from_stream(stream, event: str, *, home: Path | None = None) -> dict:
    extracted: dict = {"hook_event_name": event}
    raw = _read_stream(stream, MAX_PREFIX_BYTES)
    extract_ids(raw, extracted)
    try:
        parsed = json.loads(raw.decode("utf-8") or "{}")
        payload = compact_payload(parsed, event) if isinstance(parsed, dict) else dict(extracted)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        payload = dict(extracted)
    for key, value in extracted.items():
        payload.setdefault(key, value)
    drained = 0
    while drained < MAX_DRAIN_BYTES:
        chunk = _read_stream(stream, min(MAX_PREFIX_BYTES, MAX_DRAIN_BYTES - drained))
        if not chunk:
            break
        drained += len(chunk)
        extract_ids(chunk, extracted)
    payload.update(extracted)
    drop_payload(payload, home=home)
    return payload


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv
    event = args[1] if len(args) > 1 else "unknown"
    stream = getattr(sys.stdin, "buffer", sys.stdin)
    try:
        observe_from_stream(stream, event)
    except OSError:
        pass
    sys.stdout.write(fail_open_stdout(event))


if __name__ == "__main__":
    main()
