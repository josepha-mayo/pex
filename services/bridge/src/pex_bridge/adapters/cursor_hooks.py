"""Install PEX Cursor hooks for the desktop app (not the CLI)."""

from __future__ import annotations

import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads

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
# Observe mode never sits on the edit/shell/subagent critical path.
OBSERVE_EVENTS = [
    "sessionStart",
    "sessionEnd",
    "afterFileEdit",
    "afterShellExecution",
    "afterAgentResponse",
    "preCompact",
    "stop",
    "beforeSubmitPrompt",
    "subagentStart",
    "subagentStop",
]
FAIL_CLOSED_EVENTS = {
    "preToolUse",
    "beforeShellExecution",
}
HOOK_TIMEOUT_SECONDS = {
    "preToolUse": 9,
    "beforeShellExecution": 9,
    "beforeMCPExecution": 9,
    "beforeReadFile": 9,
    "beforeSubmitPrompt": 8,
    "stop": 45,
}
OBSERVE_HOOK_TIMEOUT_SECONDS = 3
DEFAULT_HOOK_TIMEOUT_SECONDS = 3
MAX_HOOKS_FILE_BYTES = 1_048_576
MAX_HOOK_EVENTS = 128
MAX_HOOKS_PER_EVENT = 256


def _checkout_hook(name: str) -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "integrations" / "cursor-hook" / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"PEX Cursor hook script {name} was not found in the source checkout")


def hook_script() -> Path:
    return _checkout_hook("pex_cursor_hook.py")


def observe_script() -> Path:
    return _checkout_hook("pex_cursor_observe.py")


def _frozen_hook_executable(mode: str) -> Path:
    bridge = Path(sys.executable).resolve()
    prefix = "pex-bridge-"
    helper_name = "pex-cursor-hook" if mode == "control" else "pex-cursor-observe"
    if bridge.name.startswith(prefix):
        candidate = bridge.with_name(f"{helper_name}-{bridge.name.removeprefix(prefix)}")
    else:
        candidate = bridge.with_name(f"{helper_name}{bridge.suffix}")
    if not candidate.is_file():
        raise FileNotFoundError(f"the packaged PEX Cursor {mode} helper is missing")
    return candidate


def hook_command(event: str, mode: str = "observe") -> str:
    selected = _normalized_mode(mode)
    if getattr(sys, "frozen", False):
        parts = [str(_frozen_hook_executable(selected)), event]
    elif selected == "control":
        parts = [sys.executable, str(hook_script()), event]
    else:
        # -S skips site.py so Windows cold-start can finish inside the timeout.
        parts = [sys.executable, "-S", str(observe_script()), event]
    return subprocess.list2cmdline(parts) if os.name == "nt" else shlex.join(parts)


def _atomic_json_write(path: Path, data: dict) -> None:
    encoded = strict_json_dumps(data, indent=2) + "\n"
    if len(encoded.encode("utf-8")) > MAX_HOOKS_FILE_BYTES:
        raise ValueError("Cursor hooks.json output exceeds the safety bound")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        if path.exists():
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _normalized_mode(mode: str | None) -> str:
    # Control hooks are a deliberate isolated-worktree operation. Ambient
    # process state must never silently upgrade the desktop's observer.
    selected = (mode or "observe").strip().lower()
    if selected not in {"observe", "control"}:
        raise ValueError("PEX Cursor hook mode must be observe or control")
    return selected


def install_user_hooks(cursor_dir: Path | None = None, mode: str | None = None) -> Path:
    selected = _normalized_mode(mode)
    cursor_dir = cursor_dir or (Path.home() / ".cursor")
    cursor_dir.mkdir(parents=True, exist_ok=True)
    hooks_path = cursor_dir / "hooks.json"
    data: dict = {"version": 1, "hooks": {}}
    if hooks_path.exists():
        if hooks_path.is_symlink() or hooks_path.stat().st_size > MAX_HOOKS_FILE_BYTES:
            raise ValueError("Cursor hooks.json is unsafe or exceeds the safety bound")
        try:
            with hooks_path.open("r", encoding="utf-8-sig") as handle:
                loaded = strict_json_loads(handle.read(MAX_HOOKS_FILE_BYTES + 1))
        except (OSError, ValueError) as exc:
            raise ValueError("Cursor hooks.json is unreadable; PEX did not modify it") from exc
        if not isinstance(loaded, dict) or not isinstance(loaded.get("hooks", {}), dict):
            raise ValueError("Cursor hooks.json has an unsupported shape; PEX did not modify it")
        data = loaded
        data.setdefault("hooks", {})
        if len(data["hooks"]) > MAX_HOOK_EVENTS:
            raise ValueError("Cursor hooks.json has too many event groups")
    events = HOOK_EVENTS if selected == "control" else OBSERVE_EVENTS
    for event in HOOK_EVENTS:
        entries = data["hooks"].setdefault(event, [])
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise ValueError(
                f"Cursor hooks.json event {event!r} is not a hook list; PEX did not modify it"
            )
        if len(entries) > MAX_HOOKS_PER_EVENT:
            raise ValueError(f"Cursor hooks.json event {event!r} exceeds the safety bound")
        entries[:] = [
            item
            for item in entries
            if not (
                isinstance(item.get("command"), str)
                and (
                    "pex_cursor_hook.py" in item["command"]
                    or "pex_cursor_observe.py" in item["command"]
                    or "pex-cursor-hook" in item["command"]
                    or "pex-cursor-observe" in item["command"]
                )
            )
        ]
        if not entries:
            data["hooks"].pop(event, None)
    for event in events:
        command = hook_command(event, selected)
        entries = data["hooks"].setdefault(event, [])
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise ValueError(
                f"Cursor hooks.json event {event!r} is not a hook list; PEX did not modify it"
            )
        item: dict = {"command": command}
        if selected == "observe":
            item["timeout"] = OBSERVE_HOOK_TIMEOUT_SECONDS
            if event in {"stop", "subagentStop"}:
                # Cursor defaults loop_limit to 5 and then silently disables the hook.
                item["loop_limit"] = None
        else:
            item["timeout"] = HOOK_TIMEOUT_SECONDS.get(event, DEFAULT_HOOK_TIMEOUT_SECONDS)
            if event in FAIL_CLOSED_EVENTS:
                item["failClosed"] = True
            if event == "preToolUse":
                # Cursor does not currently enforce `ask` for this generic hook.
                # Limit it to consequential tool classes. Write/StrReplace/Edit are
                # observed on afterFileEdit and must never wait on this hook.
                item["matcher"] = "Delete|Task"
            if event == "stop":
                item["loop_limit"] = 8
        entries.append(item)
    if hooks_path.exists():
        backup = hooks_path.with_name(f"{hooks_path.name}.pex-backup")
        temporary_backup = backup.with_name(f".{backup.name}.tmp")
        shutil.copy2(hooks_path, temporary_backup)
        temporary_backup.replace(backup)
    _atomic_json_write(hooks_path, data)
    return hooks_path
