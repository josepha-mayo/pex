"""Turn harness shell payloads into pytest process_state. No worker narration."""

from __future__ import annotations

import re
from typing import Any

FAILED_NODE = re.compile(r"FAILED\s+(\S+)")
SUMMARY_FAIL = re.compile(r"\b(\d+)\s+failed\b", re.I)
SUMMARY_PASS = re.compile(r"\b(\d+)\s+passed\b", re.I)


def _blob(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("output", "stdout", "stderr", "error", "result", "content"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def _exit_code(payload: dict[str, Any]) -> int | None:
    for key in ("exit_code", "exitCode", "status_code", "code"):
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return int(value.strip())
    outcome = str(payload.get("outcome") or payload.get("status") or "").lower()
    if outcome in {"success", "succeeded", "ok", "passed", "completed"}:
        return 0
    if outcome in {"failed", "failure", "error", "nonzero"}:
        return 1
    return None


def parse_pytest_process_state(command: str | None, payload: dict[str, Any] | None) -> dict[str, Any] | None:
    blob_cmd = (command or "").lower()
    payload = payload or {}
    if "pytest" not in blob_cmd and "pytest" not in _blob(payload).lower()[:400]:
        if "pytest" not in str(payload.get("tool_name") or "").lower():
            return None
    text = _blob(payload)
    code = _exit_code(payload)
    failed = None
    match = FAILED_NODE.search(text)
    if match:
        failed = match.group(1)
    fail_n = SUMMARY_FAIL.search(text)
    pass_n = SUMMARY_PASS.search(text)
    ok: bool | None
    if code is not None:
        ok = code == 0
    elif fail_n and int(fail_n.group(1)) > 0:
        ok = False
    elif "failed" in text.lower() and "passed" in text.lower() and fail_n:
        ok = False
    elif pass_n and not fail_n:
        ok = True
    else:
        ok = None
    state: dict[str, Any] = {"ok": ok, "output": text[-4000:]}
    if code is not None:
        state["exit_code"] = code
    if failed:
        state["failed"] = failed
    return {"pytest": state}
