"""Cursor stop-hook entry for one process-isolated PEX decision.

The this-desktop hook cannot import the hidden evaluator. It subprocesses this
file with the public workspace and an out-of-band control directory. Follow-up
text returns on stdout and is delivered by the Cursor stop hook itself.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pex_attach  # noqa: E402

MAX_CONTROL_BYTES = 512_000
MAX_PAYLOAD_BYTES = 1_048_576


def _reject_json_constant(constant: str) -> None:
    raise ValueError(f"non-finite JSON number {constant}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _bounded_json(path: Path | None, raw: bytes, *, label: str) -> dict:
    if path is not None:
        is_junction = getattr(path, "is_junction", None)
        if path.is_symlink() or bool(is_junction and is_junction()) or not path.is_file():
            raise ValueError(f"{label} must be a regular control file")
    if len(raw) > MAX_CONTROL_BYTES:
        raise ValueError(f"{label} exceeds the control-file limit")
    payload = json.loads(
        raw.decode("utf-8"),
        parse_constant=_reject_json_constant,
        object_pairs_hook=_unique_json_object,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"{label} is not an object")
    return payload


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: cursor_isolated_stop.py CONTROL.json < payload.json")
    control_path = Path(sys.argv[1])
    if not control_path.is_absolute():
        raise ValueError("isolated Cursor control path must be absolute")
    control = _bounded_json(control_path, control_path.read_bytes(), label="control")
    raw_payload = sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1)
    if len(raw_payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("stop payload exceeds the control-file limit")
    payload = _bounded_json(None, raw_payload, label="payload")
    result = asyncio.run(pex_attach.decide_isolated_cursor_stop(control, payload))
    stdout = result.get("hook_stdout") if isinstance(result, dict) else {}
    if not isinstance(stdout, dict):
        stdout = {}
    encoded = json.dumps(stdout, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    sys.stdout.write(encoded)


if __name__ == "__main__":
    main()
