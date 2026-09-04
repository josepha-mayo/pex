"""Turn harness shell payloads into pytest process_state. No worker narration."""

from __future__ import annotations

import re
from typing import Any

from pex_protocol.verification import classify_pytest_invocation

FAILED_NODE = re.compile(r"FAILED\s+(\S+)")
SUMMARY_LINE = re.compile(
    r"^\s*=*\s*(?P<body>\d+\s+(?:passed|failed|errors?|skipped|xfailed|xpassed|"
    r"deselected|warnings?)(?:\s*,\s*\d+\s+(?:passed|failed|errors?|skipped|"
    r"xfailed|xpassed|deselected|warnings?))*)"
    r"(?:\s+in\s+\d+(?:\.\d+)?s)?\s*=*\s*$",
    re.I,
)
SUMMARY_PART = re.compile(
    r"(?P<count>\d+)\s+(?P<kind>passed|failed|errors?|skipped|xfailed|xpassed|"
    r"deselected|warnings?)",
    re.I,
)
COLLECTED_LINE = re.compile(r"^\s*=*\s*collected\s+(?P<count>\d+)\s+items?\b.*=*\s*$", re.I)


def _blob(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "output",
        "stdout",
        "stderr",
        "error",
        "result",
        "content",
        "aggregatedOutput",
        "aggregated",
    ):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    return "\n".join(parts)


def _exit_code(payload: dict[str, Any]) -> int | None:
    # Generic ``code`` and HTTP ``status_code`` fields are transport metadata,
    # not process exit status. Treating 200 as a shell failure fabricated a
    # contradiction even when pytest's own summary said the run passed.
    observed: set[int] = set()
    for key in ("exit_code", "exitCode", "process_exit_code", "processExitCode"):
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            observed.add(value)
            continue
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            observed.add(int(value.strip()))
            continue
        return None
    return next(iter(observed)) if len(observed) == 1 else None


def _terminal_summaries(text: str) -> tuple[dict[str, int] | None, int | None]:
    summaries: set[tuple[tuple[str, int], ...]] = set()
    collected: set[int] = set()
    aliases = {"error": "errors", "warning": "warnings"}
    for line in text.splitlines():
        summary = SUMMARY_LINE.fullmatch(line)
        if summary:
            counts: dict[str, int] = {}
            for part in SUMMARY_PART.finditer(summary.group("body")):
                kind = aliases.get(part.group("kind").casefold(), part.group("kind").casefold())
                counts[kind] = int(part.group("count"))
            summaries.add(tuple(sorted(counts.items())))
        collection = COLLECTED_LINE.fullmatch(line)
        if collection:
            collected.add(int(collection.group("count")))
    parsed = dict(next(iter(summaries))) if len(summaries) == 1 else None
    collected_count = next(iter(collected)) if len(collected) == 1 else None
    return parsed, collected_count


def parse_pytest_process_state(
    command: str | None, payload: dict[str, Any] | None
) -> dict[str, Any] | None:
    # Output, tool labels, and filenames are narration, not process provenance.
    # Only one direct, safely parsed pytest invocation may create pytest state.
    if classify_pytest_invocation(command) is None:
        return None
    payload = payload or {}
    text = _blob(payload)
    code = _exit_code(payload)
    failed = None
    match = FAILED_NODE.search(text)
    if match:
        failed = match.group(1)
    summary, collected_count = _terminal_summaries(text)
    ok: bool | None
    failed_count = (
        None
        if summary is None or not ({"failed", "errors"} & summary.keys())
        else summary.get("failed", 0) + summary.get("errors", 0)
    )
    passed_count = None if summary is None else summary.get("passed")
    if failed or (failed_count is not None and failed_count > 0):
        ok = False
    elif code is not None:
        ok = code == 0
    else:
        # A summary can arrive before the command's terminal notification. It
        # is useful count evidence, but it is not the process exit receipt
        # Recovery section 5 requires before PEX may support a pass claim.
        ok = None
    state: dict[str, Any] = {"ok": ok, "output": text[-4000:]}
    if code is not None:
        state["exit_code"] = code
    if passed_count is not None:
        state["passed"] = passed_count
    if failed_count is not None:
        state["failed_count"] = failed_count
    if collected_count is not None:
        state["collected"] = collected_count
    if summary is not None:
        for key in ("skipped", "xfailed", "xpassed", "deselected"):
            if key in summary:
                state[key] = summary[key]
    if failed:
        state["failed"] = failed
    return {"pytest": state}
