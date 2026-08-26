"""Install PEX Cursor hooks for the desktop app (not the CLI)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HOOK_EVENTS = [
    "sessionStart",
    "sessionEnd",
    "preToolUse",
    "postToolUse",
    "postToolUseFailure",
    "beforeShellExecution",
    "afterShellExecution",
    "beforeMCPExecution",
    "afterMCPExecution",
    "beforeReadFile",
    "afterFileEdit",
    "beforeSubmitPrompt",
    "preCompact",
    "stop",
    "afterAgentResponse",
    "afterAgentThought",
    "subagentStart",
    "subagentStop",
]


def hook_script() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "integrations" / "cursor-hook" / "pex_cursor_hook.py"
        if candidate.is_file():
            return candidate
    return Path.cwd() / "integrations" / "cursor-hook" / "pex_cursor_hook.py"


def install_user_hooks(cursor_dir: Path | None = None) -> Path:
    script = hook_script()
    python = sys.executable
    cursor_dir = cursor_dir or (Path.home() / ".cursor")
    cursor_dir.mkdir(parents=True, exist_ok=True)
    hooks_path = cursor_dir / "hooks.json"
    data: dict = {"version": 1, "hooks": {}}
    if hooks_path.exists():
        data = json.loads(hooks_path.read_text(encoding="utf-8"))
        data.setdefault("hooks", {})
    for event in HOOK_EVENTS:
        command = f'"{python}" "{script}" {event}'
        entries = data["hooks"].setdefault(event, [])
        entries[:] = [
            item
            for item in entries
            if str(script) not in str(item.get("command") or "")
        ]
        item: dict = {"command": command}
        if event == "stop":
            item["loop_limit"] = 8
        entries.append(item)
    hooks_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return hooks_path
