"""Pinned native CLI component, not an admitted benchmark launcher.

Native CLI events are worker observations, NOT independently captured provider
traffic. This module does not create a sandbox or certify provider model identity.
See docs/native-opencode-benchmark.md before integrating it into a controller.
"""

import hashlib
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from benchmarks.async_budget import await_with_budget
from benchmarks.opencode_cli import (
    MAX_EVENTS,
    MAX_LINE_BYTES,
    MAX_OUTPUT_BYTES,
    CliTurn,
    _constant,
    _float,
    _object,
    completed_turn,
    run_turn,
)
from benchmarks.opencode_session import REPAIR_ACTIONS, SessionRun

VERSION = "1.19.3"
BINARY_SHA256 = "179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9"
MODEL = "opencode/deepseek-v4.1-flash-free"
PROVENANCE = "native_cli_worker_reported_not_provider_wire"
BASE_FIELDS = {"id", "sessionID", "messageID", "type"}


def _fields(value, required, optional=frozenset()):
    if not isinstance(value, dict) or not required <= value.keys() <= required | optional:
        raise ValueError("unknown or missing native event fields")


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("native accounting requires finite nonnegative numbers")


def _text(value):
    if not isinstance(value, str):
        raise ValueError("native event string required")


def _time(value, *, compacted=False):
    _fields(value, {"start", "end"}, {"compacted"} if compacted else set())
    for item in value.values():
        if type(item) is not int or item < 0:
            raise ValueError("native timestamps must be nonnegative integers")
    if value["end"] < value["start"]:
        raise ValueError("native time reversed")


@dataclass(frozen=True)
class NativeTurn:
    completion: CliTurn
    # Each step's original accounting, without inventing a total or normalizing
    # overlapping output/reasoning/cache counters into provider-wire semantics.
    steps: tuple[dict, ...]
    part_ids: tuple[str, ...] = ()
    provenance: str = PROVENANCE
    provider_model_verified: bool = False
    quality_measured: bool = False


def parse_native_turn(raw: bytes, *, exit_code: int, expected_session=None) -> NativeTurn:
    """Strict subset of the official 1.19.3 CLI and session-v1 schemas.

    All terminal tool events and natural model stops are supported. Unknown event
    types/fields, missing usage, duplicates, partial steps and retries fail closed.
    OpenCode's counters can themselves contain upstream defaulted zeroes, so these
    counters are not evidence that the provider reported usage, even when nonzero.
    """
    if not raw or len(raw) > MAX_OUTPUT_BYTES or exit_code != 0:
        raise ValueError("native output missing, over limit or unsuccessful")
    steps, ids, messages = [], set(), set()
    active = None
    lines = raw.splitlines()
    if len(lines) > MAX_EVENTS:
        raise ValueError("too many native events")
    for line in lines:
        if not line or len(line) > MAX_LINE_BYTES:
            raise ValueError("native event line exceeds bound")
        event = json.loads(
            line, object_pairs_hook=_object, parse_constant=_constant, parse_float=_float
        )
        _fields(event, {"type", "timestamp", "sessionID", "part"})
        if type(event["timestamp"]) is not int or event["timestamp"] < 0:
            raise ValueError("invalid native event timestamp")
        kind, part = event["type"], event["part"]
        layouts = {
            "step_start": ({"snapshot"}, set(), "step-start"),
            "step_finish": ({"snapshot"}, {"reason", "cost", "tokens"}, "step-finish"),
            "text": ({"synthetic", "ignored", "metadata"}, {"text", "time"}, "text"),
            "reasoning": ({"metadata"}, {"text", "time"}, "reasoning"),
            "tool_use": ({"metadata"}, {"callID", "tool", "state"}, "tool"),
        }
        if not isinstance(kind, str) or kind not in layouts:
            raise ValueError("unsupported native event type")
        optional, required, part_type = layouts[kind]
        _fields(part, BASE_FIELDS | required, optional)
        if part["type"] != part_type:
            raise ValueError("native envelope/part type mismatch")
        for field, prefix in (("id", "prt"), ("sessionID", "ses"), ("messageID", "msg")):
            item = part[field]
            if not isinstance(item, str) or not item.startswith(prefix) or len(item) > 256:
                raise ValueError("invalid native identity")
        if part["id"] in ids:
            raise ValueError("duplicate native part")
        ids.add(part["id"])
        for field in ("snapshot",):
            if field in part:
                _text(part[field])
        if "metadata" in part and not isinstance(part["metadata"], dict):
            raise ValueError("invalid native metadata")
        if kind == "step_start":
            if active is not None or part["messageID"] in messages:
                raise ValueError("duplicate or nested native step")
            active = part["messageID"]
            messages.add(active)
        elif active != part["messageID"]:
            raise ValueError("native event outside its active step")
        if kind in {"text", "reasoning"}:
            _text(part["text"])
            _time(part["time"])
            for field in ("synthetic", "ignored"):
                if field in part and type(part[field]) is not bool:
                    raise ValueError("invalid native text flag")
        if kind == "tool_use":
            _text(part["callID"])
            _text(part["tool"])
            state = part["state"]
            if not isinstance(state, dict):
                raise ValueError("invalid native tool state")
            if state.get("status") == "completed":
                _fields(state, {"status", "input", "output", "title", "metadata", "time"})
                _text(state["output"])
                _text(state["title"])
            elif state.get("status") == "error":
                _fields(state, {"status", "input", "error", "time"}, {"metadata"})
                _text(state["error"])
            else:
                raise ValueError("native tool is not terminal")
            if not isinstance(state["input"], dict) or not isinstance(
                state.get("metadata", {}), dict
            ):
                raise ValueError("invalid native tool payload")
            _time(state["time"], compacted=state["status"] == "completed")
        if kind == "step_finish":
            if not isinstance(part["reason"], str) or part["reason"] not in {"stop", "tool-calls"}:
                raise ValueError("unsupported native finish reason")
            _number(part["cost"])
            tokens = part["tokens"]
            _fields(tokens, {"input", "output", "reasoning", "cache"}, {"total"})
            _fields(tokens["cache"], {"read", "write"})
            for value in [v for k, v in tokens.items() if k != "cache"] + list(
                tokens["cache"].values()
            ):
                _number(value)
            steps.append({"message_id": active, "cost": part["cost"], "tokens": tokens})
            active = None
            if part["reason"] == "stop" and line != lines[-1]:
                raise ValueError("native events after terminal stop")
    completion = completed_turn(raw, exit_code=exit_code, expected_session=expected_session)
    if active is not None or not steps:
        raise ValueError("native step incomplete")
    return NativeTurn(completion, tuple(steps), tuple(sorted(ids)))


def native_settings(*, version: str, model: str, steps: int) -> dict:
    """No custom provider, transport override, model fallback or paid small model."""
    if version != VERSION or model != MODEL:
        raise ValueError("unsupported native OpenCode version/model identity")
    if type(steps) is not int or not 1 <= steps <= 100:
        raise ValueError("native step budget must be bounded")
    return {
        "autoupdate": False,
        "share": "disabled",
        "model": model,
        "small_model": model,
        "enabled_providers": ["opencode"],
        "permission": {
            "*": "deny",
            "read": "allow",
            "glob": "allow",
            "grep": "allow",
            "edit": "allow",
            "bash": "allow",
            "external_directory": "deny",
        },
        "agent": {"build": {"steps": steps, "model": model}},
    }


async def run_native_session(
    *,
    executable: Path,
    workspace: Path,
    state_home: Path,
    log_directory: Path,
    prompt: str,
    deadline: float,
    version: str,
    model: str,
    steps: int,
    max_followups: int = 0,
    review: Callable[[tuple[NativeTurn, ...]], Awaitable[dict]] | None = None,
) -> tuple[SessionRun, tuple[NativeTurn, ...]]:
    """Worker-only component for a separately audited caller-owned boundary.

    No CLI entry point or controller admission is exposed: the current relay
    network namespace cannot run this native transport. Configuration is NOT
    isolation. The caller must isolate state/evaluator/controller files and own
    the entire process tree, including teardown. Review stays outside the worker
    through isolated IPC. Calling this directly on the host is not a benchmark.
    """
    settings = native_settings(version=version, model=model, steps=steps)
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("finite native deadline required")
    if type(max_followups) is not int or not 0 <= max_followups <= 10:
        raise ValueError("invalid native follow-up budget")
    if review is None and max_followups:
        raise ValueError("baseline cannot have follow-ups")
    paths = (executable, workspace, state_home, log_directory)
    if any(not p.is_absolute() or p.resolve() != p for p in paths):
        raise ValueError("native paths must be absolute and unlinked")
    if any(
        a == b or a.is_relative_to(b) or b.is_relative_to(a)
        for a, b in ((workspace, state_home), (workspace, log_directory))
    ):
        raise ValueError("native state/logs must be separate from task")
    if any(executable == p or executable.is_relative_to(p)
           for p in (workspace, state_home, log_directory)):
        raise ValueError("native binary must be outside task, state and logs")

    def verify_binary():
        if executable.resolve() != executable:
            raise ValueError("native binary path changed")
        with executable.open("rb") as handle:
            if hashlib.file_digest(handle, "sha256").hexdigest() != BINARY_SHA256:
                raise ValueError("native binary digest mismatch")

    verify_binary()

    def remaining():
        value = deadline - monotonic()
        if value <= 0:
            raise TimeoutError("native shared task deadline exhausted")
        return value

    remaining()
    state_home.mkdir(parents=True, exist_ok=False)
    log_directory.mkdir(parents=True, exist_ok=False)
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(state_home / "home"),
        "XDG_CONFIG_HOME": str(state_home / "config"),
        "XDG_DATA_HOME": str(state_home / "data"),
        "XDG_CACHE_HOME": str(state_home / "cache"),
        "XDG_STATE_HOME": str(state_home / "state"),
        "OPENCODE_CONFIG_CONTENT": json.dumps(settings, separators=(",", ":")),
    }
    turns, receipts, actions, outgoing = [], [], [], []
    vendor, next_prompt, limit_reached = None, prompt, False
    seen_messages, seen_parts = set(), set()
    while True:
        remaining()
        verify_binary()
        remaining()
        log = log_directory / f"turn-{len(turns)}.jsonl"
        turn = await run_turn(
            executable=executable,
            workspace=workspace,
            model=model,
            prompt=next_prompt,
            environment=environment,
            stdout_path=log,
            stderr_path=log.with_suffix(".stderr"),
            deadline=deadline,
            session_id=vendor,
        )
        verify_binary()
        raw = log.read_bytes()
        receipt = parse_native_turn(raw, exit_code=0, expected_session=vendor)
        if receipt.completion != turn:
            raise ValueError("native log changed after capture")
        current_messages = {step["message_id"] for step in receipt.steps}
        current_parts = set(receipt.part_ids)
        if seen_messages & current_messages or seen_parts & current_parts:
            raise ValueError("native follow-up replayed prior message or part identity")
        seen_messages.update(current_messages)
        seen_parts.update(current_parts)
        remaining()
        vendor = turn.session_id
        turns.append(turn)
        receipts.append(receipt)
        if review is None:
            break
        decision = await await_with_budget(lambda: review(tuple(receipts)), budget=remaining())
        remaining()
        if (
            not isinstance(decision, dict)
            or not isinstance(decision.get("type"), str)
            or decision["type"] not in REPAIR_ACTIONS | {"NOOP"}
        ):
            raise ValueError("unsupported native review action")
        action = decision["type"]
        actions.append(action)
        if action == "NOOP":
            break
        payload = decision.get("payload")
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > 20_000 or "\x00" in text:
            raise ValueError("native repair needs bounded public text")
        if len(outgoing) >= max_followups:
            limit_reached = True
            break
        next_prompt = text
        outgoing.append(text)
    remaining()
    return SessionRun(tuple(turns), tuple(actions), tuple(outgoing), limit_reached), tuple(receipts)


def admit_native_attempt(*args, **kwargs):
    """Deliberately fail closed; no host/network fallback from the relay boundary."""
    raise RuntimeError(
        "native benchmark admission unavailable: requires audited native egress isolation, "
        "provider-recognized access, real supervisor access and separate provenance protocol"
    )
