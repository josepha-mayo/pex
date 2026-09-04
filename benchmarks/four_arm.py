"""Four-arm PexBench driver.

Refuses to freeze the manifest until live Cursor and Codex arms exist for every
task. Never invents lift. Isolated temp workspaces only — do not turn/start on
the operator's live Codex threads unless --allow-live is set, and even then only
on a newly created thread whose cwd is the temp workspace.

Paired arms receive the same TASK.md. The only treatment difference is an
independent PEX supervisor attached after the worker has begun.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import platform
import secrets
import shutil
import stat
import sys
import time
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import boundary  # noqa: E402
import evaluator  # noqa: E402
import runner  # noqa: E402

PRESENTATION_ARMS = evaluator.PRESENTATION_ARMS
CURSOR_LIVE_REFUSAL = (
    "refusing live Cursor arm: do not spawn another Cursor window. "
    "This desktop session is already Cursor; observe it via ~/.cursor/hooks.json."
)
CURSOR_TREATMENT_REFUSAL = (
    "refusing Cursor+PEX presentation arm: a saved stop payload cannot prove that a PEX "
    "follow-up continued this same Cursor conversation. Use a synchronous hook controller "
    "that captures both the initial and follow-up stop events; do not score this arm yet."
)
CURSOR_REPLAY_REFUSAL = (
    "refusing a supplied Cursor stop payload as live evidence; wait on the canonical "
    "this-desktop hook drop instead"
)
_MAX_CONTROL_FILE_BYTES = 512_000
_MAX_RECORD_TEXT_CHARS = 4_000
_MAX_RECORDED_MESSAGES = 100
_MAX_RECORDED_JSON_BYTES = 256_000
_MAX_RAW_LOG_BYTES = 64 * 1024 * 1024
_MAX_RAW_LOG_RECORD_BYTES = 1024 * 1024
_MAX_RAW_LOG_RECORDS = 10_000


def _is_sha256(value: object) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _bounded_regular_file(path: Path, limit: int, *, allow_empty: bool = True) -> bool:
    try:
        size = path.stat().st_size
    except OSError:
        return False
    return (
        path.is_file()
        and not runner._is_link_like(path)
        and (allow_empty or size > 0)
        and size <= limit
    )


def _path_has_link_component(path: Path, root: Path) -> bool:
    """Reject a canonical artifact if any existing component below its root is linked."""
    candidate = path.absolute()
    boundary_root = root.absolute()
    try:
        candidate.relative_to(boundary_root)
    except ValueError:
        return True
    current = candidate
    while True:
        if runner._is_link_like(current):
            return True
        if current == boundary_root:
            return False
        parent = current.parent
        if parent == current:
            return True
        current = parent


def _write_text_fsync(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def _bounded_texts(values: object, *, label: str) -> list[str]:
    if (
        not isinstance(values, list)
        or len(values) > _MAX_RECORDED_MESSAGES
        or any(not isinstance(value, str) for value in values)
    ):
        raise RuntimeError(f"{label} exceeds the benchmark record count bound")
    result = list(values)
    if any(len(value) > _MAX_RECORD_TEXT_CHARS for value in result):
        raise RuntimeError(f"{label} exceeds the benchmark text bound")
    return result


def _bounded_json(value: Any, *, label: str) -> Any:
    try:
        encoded = json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not finite JSON") from exc
    if len(encoded) > _MAX_RECORDED_JSON_BYTES:
        raise RuntimeError(f"{label} exceeds the benchmark record size bound")
    return value


def _human_intervention_log(value: object) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) > 100:
        raise RuntimeError("human intervention log exceeds the benchmark bound")
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict) or not {"action", "timestamp"}.issubset(item):
            raise RuntimeError("human intervention log must contain exact action receipts")
        action = item.get("action")
        timestamp = item.get("timestamp")
        if (
            not isinstance(action, str)
            or not action.strip()
            or len(action) > 512
            or not isinstance(timestamp, str)
            or not timestamp.strip()
            or len(timestamp) > 64
        ):
            raise RuntimeError("human intervention receipt is invalid")
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise RuntimeError("human intervention timestamp is invalid") from exc
        if parsed.tzinfo is None:
            raise RuntimeError("human intervention timestamp must include a timezone")
        _bounded_json(item, label="human intervention receipt")
        normalized.append(dict(item))
    return normalized


def _load_control_json(path: Path) -> dict[str, Any]:
    if not _bounded_regular_file(path, _MAX_CONTROL_FILE_BYTES):
        raise ValueError("Cursor stop payload is missing or exceeds the control-file bound")
    try:
        with path.open("rb") as handle:
            raw = handle.read(_MAX_CONTROL_FILE_BYTES + 1)
        if len(raw) > _MAX_CONTROL_FILE_BYTES:
            raise ValueError("Cursor stop payload exceeds the control-file bound")
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {constant}")
            ),
            object_pairs_hook=runner._unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Cursor stop payload is not valid bounded UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Cursor stop payload must be a JSON object")
    return value


@cache
def _expected_task_evidence(task_id: str) -> tuple[str, str]:
    """Return the canonical public-prompt and fresh-seed fingerprints."""
    prompt_hash = boundary.sha256_text(evaluator.prompt_text(task_id))
    seed_hash, _ = _canonical_seed(task_id)
    return prompt_hash, seed_hash


def readiness() -> dict[str, Any]:
    from pex_bridge.adapters.codex_bin import resolve_codex_bin
    from pex_bridge.adapters.desktop import desktop_process_inventory, list_desktop_apps
    from pex_bridge.adapters.grok_build_bin import resolve_grok_build
    from pex_bridge.adapters.hermes_bin import resolve_hermes

    desktops = list_desktop_apps()
    inventory = desktop_process_inventory()
    coverage = arm_coverage()
    blockers = freeze_blockers(coverage)
    coherent = coherent_presentation_runs()
    hooks = Path.home() / ".cursor" / "hooks.json"
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "desktops": desktops,
        "desktop_inventory": inventory,
        "bins": {
            "codex": resolve_codex_bin(),
            "cursor_hooks": str(hooks) if hooks.is_file() else None,
            "cursor_hook_mode": _cursor_hook_mode(hooks),
            "grok_build": resolve_grok_build(),
            "hermes": resolve_hermes(),
        },
        "manifest_frozen": bool(runner.load_manifest().get("frozen")),
        "coverage": coverage,
        "coherent_runs": [item["run_id"] for item in coherent],
        "freeze_blockers": blockers,
        "can_freeze": not blockers,
        "note": (
            "Presentation arms are cursor, cursor_pex, codex, codex_pex. "
            "synthetic_pex smoke is infrastructure only. "
            "Live Cursor/Codex runs require --allow-live and isolated workspaces. "
            "Paired arms share one TASK.md; treatment is attached PEX, not a better prompt. "
            "desktop_inventory is diagnostic and is never a freeze blocker. "
            "Observe-only Cursor hooks are not same-session stop treatment."
        ),
    }


def arm_coverage() -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    if not runner.RESULTS.exists():
        return found
    for path in sorted(runner.RESULTS.glob("*.jsonl")):
        if "INVALID" in path.parts:
            continue
        rows, errors = _read_rows(path)
        if errors:
            continue
        for row in rows:
            arm = str(row.get("arm") or "")
            task = str(row.get("task") or "")
            key = f"{arm}:{task}"
            found[key] = {
                "arm": arm,
                "task": task,
                "success": row.get("success"),
                "live": bool(row.get("live")),
                "not_a_presentation_arm": bool(row.get("not_a_presentation_arm")),
                "pair_id": row.get("pair_id"),
                "prompt_sha256": row.get("prompt_sha256"),
                "seed_manifest_sha256": row.get("seed_manifest_sha256"),
                "final_workspace_sha256": row.get("final_workspace_sha256"),
                "worker_config_sha256": row.get("worker_config_sha256"),
                "worker_model": row.get("worker_model"),
                "harness_identity_sha256": row.get("harness_identity_sha256"),
                "benchmark_sha256": row.get("benchmark_sha256"),
                "transport_kind": row.get("transport_kind"),
                "pex_process_isolated": bool(
                    (row.get("pex") or {}).get("supervisor_process_isolated")
                ),
                "file": path.name,
            }
    return found


def _read_rows(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        return runner.read_result_records(path), []
    except (OSError, UnicodeError, ValueError) as exc:
        return [], [f"{path.name} is unreadable or invalid: {exc}"]


def _provenance_blockers(
    result_path: Path,
    row: dict[str, Any],
    arm: str,
    task: str,
) -> list[str]:
    """Recompute the durable seed and final-workspace evidence for one row."""
    blockers: list[str] = []
    expected_snapshot = (
        runner.RESULTS / "_scratch" / result_path.stem / arm / task
    ).absolute()
    snapshot_raw = str(row.get("snapshot") or "").strip()
    try:
        snapshot = Path(snapshot_raw).absolute() if snapshot_raw else None
    except (OSError, ValueError):
        snapshot = None
    if (
        snapshot != expected_snapshot
        or _path_has_link_component(expected_snapshot, runner.RESULTS)
        or not expected_snapshot.is_dir()
    ):
        blockers.append(f"{arm}/{task} lacks its canonical immutable workspace snapshot")
    else:
        try:
            snapshot_hash = boundary.workspace_manifest_sha256(expected_snapshot)
        except (OSError, ValueError, AssertionError) as exc:
            blockers.append(f"{arm}/{task} snapshot cannot be verified: {exc}")
        else:
            if snapshot_hash != row.get("final_workspace_sha256"):
                blockers.append(f"{arm}/{task} final workspace fingerprint does not match snapshot")

    proof = row.get("isolation_proof") or {}
    receipt_raw = str(proof.get("receipt_path") or "").strip()
    expected_receipt = (
        runner.RESULTS
        / "_scratch"
        / "_receipts"
        / f"{proof.get('workspace_name')}.json"
    ).absolute()
    try:
        receipt_path = Path(receipt_raw).absolute() if receipt_raw else None
    except (OSError, ValueError):
        receipt_path = None
    receipt: dict[str, Any] | None = None
    if (
        receipt_path is None
        or receipt_path != expected_receipt
        or _path_has_link_component(expected_receipt, runner.RESULTS)
        or not _bounded_regular_file(receipt_path, _MAX_CONTROL_FILE_BYTES)
    ):
        blockers.append(f"{arm}/{task} lacks its external pre-worker seed receipt")
    else:
        try:
            raw_receipt = receipt_path.read_bytes()
            if hashlib.sha256(raw_receipt).hexdigest() != proof.get("receipt_sha256"):
                blockers.append(f"{arm}/{task} seed receipt fingerprint mismatch")
            loaded = json.loads(
                raw_receipt.decode("utf-8"),
                parse_constant=lambda constant: (_ for _ in ()).throw(
                    ValueError(f"non-finite JSON number {constant}")
                ),
                object_pairs_hook=runner._unique_object,
            )
            if isinstance(loaded, dict):
                receipt = loaded
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            blockers.append(f"{arm}/{task} seed receipt is unreadable")
    if receipt is not None:
        expected_receipt = {
            "schema_version": 1,
            "run_id": result_path.stem,
            "arm": arm,
            "task": task,
            "workspace_name": proof.get("workspace_name"),
            "prepared_before_worker": True,
            "prompt_sha256": row.get("prompt_sha256"),
            "seed_manifest_sha256": row.get("seed_manifest_sha256"),
            "task_package_sha256": row.get("task_package_sha256"),
            "benchmark_sha256": row.get("benchmark_sha256"),
            "workspace": row.get("cwd"),
        }
        if any(receipt.get(key) != value for key, value in expected_receipt.items()):
            blockers.append(f"{arm}/{task} seed receipt does not bind this exact row")
        nonce = str(receipt.get("nonce") or "")
        if len(nonce) != 32 or any(character not in "0123456789abcdef" for character in nonce):
            blockers.append(f"{arm}/{task} seed receipt nonce is invalid")
        try:
            prepared_at = datetime.fromisoformat(
                str(receipt.get("prepared_at") or "").replace("Z", "+00:00")
            )
            started_at = datetime.fromisoformat(
                str(row.get("started_at") or "").replace("Z", "+00:00")
            )
            if (
                prepared_at.tzinfo is None
                or started_at.tzinfo is None
                or prepared_at > started_at
            ):
                raise ValueError
        except ValueError:
            blockers.append(f"{arm}/{task} seed receipt time is not pre-worker")
    return blockers


def _raw_log_blockers(
    result_path: Path,
    row: dict[str, Any],
    arm: str,
    task: str,
) -> list[str]:
    """Require a retained canonical raw harness log, not only a claimed hash."""
    expected_path = (
        runner.RESULTS
        / "_scratch"
        / "_raw"
        / result_path.stem
        / arm
        / f"{task}.jsonl"
    ).absolute()
    raw_path_text = str(row.get("raw_log_path") or "").strip()
    try:
        raw_path = Path(raw_path_text).absolute() if raw_path_text else None
    except (OSError, ValueError):
        raw_path = None
    if (
        raw_path != expected_path
        or _path_has_link_component(expected_path, runner.RESULTS)
        or not _bounded_regular_file(
            expected_path,
            _MAX_RAW_LOG_BYTES,
            allow_empty=False,
        )
    ):
        return [f"{arm}/{task} lacks its canonical immutable raw harness event log"]
    try:
        digest, content_blockers = _inspect_raw_log(expected_path, row, arm, task)
    except (OSError, ValueError) as exc:
        return [
            f"{arm}/{task} raw harness event log is invalid: "
            f"{type(exc).__name__}: {exc}"
        ]
    if digest != row.get("raw_log_sha256"):
        return [f"{arm}/{task} raw harness event log fingerprint mismatch"]
    return content_blockers


def _inspect_raw_log(
    path: Path,
    row: dict[str, Any],
    arm: str,
    task: str,
) -> tuple[str, list[str]]:
    """Hash and validate a controller envelope around complete raw vendor events."""
    try:
        run_started = datetime.fromisoformat(
            str(row.get("started_at") or "").replace("Z", "+00:00")
        )
        run_ended = datetime.fromisoformat(
            str(row.get("ended_at") or "").replace("Z", "+00:00")
        )
        if (
            run_started.tzinfo is None
            or run_ended.tzinfo is None
            or run_ended < run_started
        ):
            raise ValueError
    except ValueError as exc:
        raise ValueError("result timestamps cannot bind the raw log") from exc

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        descriptor_stat = os.fstat(descriptor)
        path_stat = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISREG(descriptor_stat.st_mode)
            or runner._is_link_like(path)
            or (descriptor_stat.st_dev, descriptor_stat.st_ino)
            != (path_stat.st_dev, path_stat.st_ino)
            or descriptor_stat.st_size > _MAX_RAW_LOG_BYTES
        ):
            raise ValueError("raw log is not a stable bounded regular file")

        digest = hashlib.sha256()
        record_count = 0
        vendor_count = 0
        footer_seen = False
        event_ids: set[str] = set()
        cursor_stop_ids: set[str] = set()
        codex_started_turns: set[str] = set()
        codex_completed_turns: set[str] = set()
        expected_source = "cursor_hook" if arm.startswith("cursor") else "codex_app_server"
        expected_identity = {
            "schema_version": 1,
            "run_id": row.get("run_id"),
            "arm": arm,
            "task": task,
            "thread_id": row.get("thread_id"),
        }

        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            while True:
                raw = handle.readline(_MAX_RAW_LOG_RECORD_BYTES + 1)
                if not raw:
                    break
                digest.update(raw)
                record_count += 1
                if record_count > _MAX_RAW_LOG_RECORDS:
                    raise ValueError("raw log exceeds the event-count bound")
                if len(raw) > _MAX_RAW_LOG_RECORD_BYTES:
                    raise ValueError(f"raw log event {record_count} exceeds the size bound")
                if raw.strip() == b"":
                    raise ValueError(f"raw log event {record_count} is blank")
                try:
                    event = json.loads(
                        raw.decode("utf-8"),
                        parse_constant=lambda constant: (_ for _ in ()).throw(
                            ValueError(f"non-finite JSON number {constant}")
                        ),
                        object_pairs_hook=runner._unique_object,
                    )
                except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
                    raise ValueError(f"raw log event {record_count} is invalid JSON") from exc
                if not isinstance(event, dict):
                    raise ValueError(f"raw log event {record_count} is not an object")
                if event.get("sequence") != record_count - 1:
                    raise ValueError("raw log event sequence is not contiguous from zero")
                if any(event.get(key) != value for key, value in expected_identity.items()):
                    raise ValueError("raw log event identity does not bind the result row")
                try:
                    timestamp = datetime.fromisoformat(
                        str(event.get("timestamp") or "").replace("Z", "+00:00")
                    )
                    if (
                        timestamp.tzinfo is None
                        or timestamp < run_started
                        or timestamp > run_ended
                    ):
                        raise ValueError
                except ValueError as exc:
                    raise ValueError("raw log event timestamp is outside the run") from exc

                record_type = event.get("record_type")
                if record_count == 1:
                    if (
                        record_type != "capture_header"
                        or event.get("source") != "benchmark_controller"
                        or event.get("event_kind") != "capture_started"
                        or event.get("harness_identity_sha256")
                        != row.get("harness_identity_sha256")
                        or event.get("transport_kind") != row.get("transport_kind")
                        or timestamp != run_started
                    ):
                        raise ValueError("raw log lacks its exact controller capture header")
                    continue
                if footer_seen:
                    raise ValueError("raw log contains data after its completion footer")
                if record_type == "capture_footer":
                    if (
                        vendor_count == 0
                        or event.get("source") != "benchmark_controller"
                        or event.get("event_kind") != "capture_completed"
                        or event.get("complete") is not True
                        or event.get("captured_event_count") != vendor_count
                        or timestamp != run_ended
                    ):
                        raise ValueError("raw log completion footer is inconsistent")
                    footer_seen = True
                    continue
                if record_type != "vendor_event" or event.get("source") != expected_source:
                    raise ValueError("raw log contains a non-vendor event before completion")
                event_id = event.get("event_id")
                event_kind = event.get("event_kind")
                payload = event.get("payload")
                if (
                    not isinstance(event_id, str)
                    or not 1 <= len(event_id) <= 256
                    or any(ord(character) < 32 for character in event_id)
                    or event_id in event_ids
                    or not isinstance(event_kind, str)
                    or not 1 <= len(event_kind) <= 128
                    or any(ord(character) < 32 for character in event_kind)
                    or not isinstance(payload, dict)
                ):
                    raise ValueError("raw vendor event identity or payload is invalid")
                event_ids.add(event_id)
                vendor_count += 1
                if arm.startswith("cursor") and event_kind.casefold() == "stop":
                    stop_id = payload.get("stop_id")
                    try:
                        payload_cwd = Path(str(payload.get("cwd") or "")).resolve()
                        result_cwd = Path(str(row.get("cwd") or "")).resolve()
                    except (OSError, ValueError) as exc:
                        raise ValueError("Cursor raw stop has invalid workspace identity") from exc
                    if (
                        not isinstance(stop_id, str)
                        or not stop_id
                        or len(stop_id) > 256
                        or payload.get("conversation_id") != row.get("thread_id")
                        or payload_cwd != result_cwd
                    ):
                        raise ValueError("Cursor raw stop does not bind the worker session")
                    cursor_stop_ids.add(stop_id)
                if arm.startswith("codex") and event_kind in {
                    "turn/started",
                    "turn/completed",
                }:
                    turn_id = payload.get("turn_id")
                    if (
                        not isinstance(turn_id, str)
                        or not turn_id
                        or len(turn_id) > 256
                        or payload.get("thread_id") != row.get("thread_id")
                    ):
                        raise ValueError("Codex raw turn does not bind the worker session")
                    target = (
                        codex_started_turns
                        if event_kind == "turn/started"
                        else codex_completed_turns
                    )
                    target.add(turn_id)

        final_stat = os.stat(path, follow_symlinks=False)
        if (
            runner._is_link_like(path)
            or (
                descriptor_stat.st_dev,
                descriptor_stat.st_ino,
                descriptor_stat.st_size,
                descriptor_stat.st_mtime_ns,
            )
            != (
                final_stat.st_dev,
                final_stat.st_ino,
                final_stat.st_size,
                final_stat.st_mtime_ns,
            )
        ):
            raise ValueError("raw log changed while it was verified")
    finally:
        os.close(descriptor)

    if not footer_seen:
        raise ValueError("raw log lacks a complete controller capture footer")
    blockers: list[str] = []
    if arm.startswith("cursor"):
        if not cursor_stop_ids:
            blockers.append(f"{arm}/{task} raw log contains no bound Cursor stop event")
        continuation = (row.get("transport_evidence") or {}).get(
            "same_session_continuation"
        ) or {}
        if arm == "cursor_pex" and not {
            continuation.get("initial_stop_id"),
            continuation.get("followup_stop_id"),
        }.issubset(cursor_stop_ids):
            blockers.append(
                f"{arm}/{task} raw log does not contain both same-session Cursor stops"
            )
    else:
        initial_turn = row.get("turn_id")
        expected_completed = 1 + int((row.get("pex") or {}).get("followups") or 0)
        if (
            not isinstance(initial_turn, str)
            or initial_turn not in codex_started_turns
            or initial_turn not in codex_completed_turns
            or len(codex_completed_turns) < expected_completed
        ):
            blockers.append(
                f"{arm}/{task} raw log lacks all bound Codex turn start/completion events"
            )
    return digest.hexdigest(), blockers


def _canonical_raw_log_path(run_id: str, arm: str, task: str) -> Path:
    return (
        runner.RESULTS
        / "_scratch"
        / "_raw"
        / runner.result_path(run_id).stem
        / arm
        / f"{task}.jsonl"
    ).absolute()


def _codex_turn_events_from_raw_capture(
    raw_capture: object,
    thread_id: str,
) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    if not isinstance(raw_capture, list):
        return events
    for message in raw_capture:
        if not isinstance(message, dict):
            continue
        method = message.get("method")
        if method not in {"turn/started", "turn/completed"}:
            continue
        params = message.get("params") if isinstance(message.get("params"), dict) else {}
        if str(params.get("threadId") or "") != thread_id:
            continue
        turn = params.get("turn") if isinstance(params.get("turn"), dict) else {}
        turn_id = str(turn.get("id") or "")
        if not turn_id or len(turn_id) > 256:
            continue
        events.append({"event_kind": str(method), "turn_id": turn_id})
    return events


def _try_write_codex_raw_log(
    *,
    run_id: str,
    arm: str,
    task: str,
    thread_id: str,
    turn_id: str,
    started_at: str,
    ended_at: str,
    harness_identity_sha256: str,
    transport_kind: str,
    followups: int,
    raw_capture: object,
) -> tuple[str | None, str | None]:
    """Write freeze-shaped jsonl only when vendor start+complete events bind the turn.

    Incomplete capture stays null. Do not synthesize turn/started from our RPC.
    """
    if not arm.startswith("codex"):
        return None, None
    events = _codex_turn_events_from_raw_capture(raw_capture, thread_id)
    started = {event["turn_id"] for event in events if event["event_kind"] == "turn/started"}
    completed = {event["turn_id"] for event in events if event["event_kind"] == "turn/completed"}
    expected_completed = 1 + max(0, int(followups or 0))
    if (
        not turn_id
        or turn_id not in started
        or turn_id not in completed
        or not started.issuperset(completed)
        or len(completed) < expected_completed
    ):
        return None, None
    path = _canonical_raw_log_path(run_id, arm, task)
    if path.exists():
        return None, None
    common = {
        "schema_version": 1,
        "run_id": run_id,
        "arm": arm,
        "task": task,
        "thread_id": thread_id,
    }
    records: list[dict[str, Any]] = [
        {
            **common,
            "sequence": 0,
            "record_type": "capture_header",
            "source": "benchmark_controller",
            "event_kind": "capture_started",
            "timestamp": started_at,
            "harness_identity_sha256": harness_identity_sha256,
            "transport_kind": transport_kind,
        }
    ]
    for event in events:
        event_id = f"{event['event_kind']}:{event['turn_id']}"
        if any(record.get("event_id") == event_id for record in records):
            continue
        records.append(
            {
                **common,
                "sequence": len(records),
                "record_type": "vendor_event",
                "source": "codex_app_server",
                "event_kind": event["event_kind"],
                "event_id": f"{event['event_kind']}:{event['turn_id']}",
                "timestamp": started_at
                if event["event_kind"] == "turn/started"
                else ended_at,
                "payload": {
                    "thread_id": thread_id,
                    "turn_id": event["turn_id"],
                },
            }
        )
    records.append(
        {
            **common,
            "sequence": len(records),
            "record_type": "capture_footer",
            "source": "benchmark_controller",
            "event_kind": "capture_completed",
            "timestamp": ended_at,
            "complete": True,
            "captured_event_count": len(records) - 1,
        }
    )
    body = "".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n" for record in records
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    if nofollow:
        flags |= nofollow
    descriptor = os.open(path, flags, 0o644)
    try:
        os.write(descriptor, body.encode("utf-8"))
    finally:
        os.close(descriptor)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return str(path), digest


def _execution_preflight_blockers() -> list[str]:
    """Block unsafe/invalid execution, not evidence that execution must create.

    Development runs may collect honest rows while the benchmark is not yet
    presentation-ready. Freeze/report checks remain strictly fail-closed in
    ``_report_readiness_blockers`` and ``_run_blockers``.
    """

    return [
        f"benchmark suite is invalid: {error}" for error in evaluator.validate_suite()
    ]


def _report_readiness_blockers() -> list[str]:
    """Return presentation/freeze blockers, including execution safety."""

    blockers = _execution_preflight_blockers()
    manifest = runner.load_manifest()
    suite = manifest.get("suite") if isinstance(manifest.get("suite"), dict) else {}
    if (
        suite.get("natural_task_source_status") != "satisfied"
        or suite.get("task_execution_boundary") != "isolated_untrusted_worker"
    ):
        blockers.append(
            "benchmark natural-task source and isolated untrusted execution/hidden-evaluator "
            "boundary are not satisfied"
        )
    integrity = (
        manifest.get("integrity") if isinstance(manifest.get("integrity"), dict) else {}
    )
    if integrity.get("raw_harness_event_log_status") != "satisfied":
        blockers.append("complete immutable raw harness event logs are not yet captured")
    if integrity.get("cursor_same_session_treatment_status") != "satisfied":
        blockers.append("Cursor+PEX synchronous same-session treatment is unavailable")
    if integrity.get("source_repo_commit_capture_status") != "satisfied":
        blockers.append("source repository commits are not yet captured and verified")
    cursor_network = str(
        (runner.protocol_config(manifest).get("network_policy") or {}).get("cursor") or ""
    )
    if "not_controller_verified" in cursor_network:
        blockers.append("Cursor network policy is declared but not controller-verified")
    return blockers


def _experiment_preflight_blockers() -> list[str]:
    """Backward-compatible name for callers that display the full NO-GO list."""

    return _report_readiness_blockers()


def _run_blockers(path: Path) -> list[str]:
    rows, blockers = _read_rows(path)
    blockers.extend(runner.verify_result_chain(path))
    blockers.extend(_report_readiness_blockers())
    by_key: dict[str, dict[str, Any]] = {}
    expected_manifest = runner.manifest_sha256()
    expected_evaluator = runner.evaluator_sha256()
    expected_packages = runner.task_package_sha256()
    expected_controller = runner.controller_sha256()
    expected_benchmark = runner.benchmark_sha256()
    expected_tasks = set(evaluator.task_ids())
    for row in rows:
        if row.get("record_type") == "abort":
            reason = str(row.get("abort_reason") or "unspecified")
            blockers.append(f"{path.stem} is an aborted run: {reason}")
            continue
        arm = str(row.get("arm") or "")
        task = str(row.get("task") or "")
        if arm not in PRESENTATION_ARMS:
            blockers.append(f"{path.stem} contains non-presentation arm {arm or '<missing>'}")
            continue
        if task not in expected_tasks:
            blockers.append(f"{path.stem} contains undeclared task {task or '<missing>'}")
            continue
        key = f"{arm}:{task}"
        if key in by_key:
            blockers.append(f"{path.stem} has duplicate {arm}/{task}")
            continue
        by_key[key] = row
        if row.get("run_id") != path.stem:
            blockers.append(f"{arm}/{task} run_id does not match {path.stem}")
        if row.get("manifest_sha256") != expected_manifest:
            blockers.append(f"{arm}/{task} manifest fingerprint is absent or stale")
        if row.get("evaluator_sha256") != expected_evaluator:
            blockers.append(f"{arm}/{task} evaluator fingerprint is absent or stale")
        if row.get("task_package_sha256") != expected_packages:
            blockers.append(f"{arm}/{task} task-package fingerprint is absent or stale")
        if row.get("controller_sha256") != expected_controller:
            blockers.append(f"{arm}/{task} controller fingerprint is absent or stale")
        if row.get("benchmark_sha256") != expected_benchmark:
            blockers.append(f"{arm}/{task} benchmark fingerprint is absent or stale")
        if not row.get("live") or row.get("not_a_presentation_arm"):
            blockers.append(f"{arm}/{task} is not a live presentation row")
        if type(row.get("success")) is not bool:
            blockers.append(f"{arm}/{task} lacks a binary evaluator result")
        if row.get("pair_id") != f"{path.stem}:{task}":
            blockers.append(f"{arm}/{task} pair_id is not bound to this run")
        try:
            protocol_fields = runner.protocol_record_fields(task, arm)
        except ValueError as exc:
            blockers.append(f"{arm}/{task} cannot bind the experiment protocol: {exc}")
            protocol_fields = {}
        for field, expected in protocol_fields.items():
            if row.get(field) != expected:
                blockers.append(f"{arm}/{task} has invalid protocol field {field}")
        if row.get("record_schema_version") != 2 or row.get("run_status") != "completed":
            blockers.append(f"{arm}/{task} is not a completed schema-v2 record")
        if row.get("attempt") != 1:
            blockers.append(f"{arm}/{task} violates the no-selective-rerun policy")
        if not str(row.get("harness_version") or "").strip() or str(
            row.get("harness_version")
        ).lower() == "unknown":
            blockers.append(f"{arm}/{task} lacks an exact harness version")
        if not isinstance(row.get("model_settings"), dict):
            blockers.append(f"{arm}/{task} lacks explicit model settings")
        if row.get("model_settings_sha256") != runner.json_sha256(
            row.get("model_settings") or {}
        ):
            blockers.append(f"{arm}/{task} has an invalid model settings fingerprint")
        settings = row.get("model_settings") or {}
        worker_model = str(row.get("worker_model") or "").strip()
        model_evidence = row.get("model_version_evidence") or {}
        environment = row.get("controller_environment") or {}
        if (
            not worker_model
            or settings.get("model") != worker_model
            or not isinstance(row.get("model_version_evidence"), dict)
            or model_evidence.get("requested_model_id") != worker_model
            or type(model_evidence.get("provider_revision_available")) is not bool
            or (
                model_evidence.get("provider_revision_available") is True
                and not str(model_evidence.get("provider_revision") or "").strip()
            )
            or (
                model_evidence.get("provider_revision_available") is False
                and model_evidence.get("provider_revision") is not None
            )
            or not isinstance(row.get("controller_environment"), dict)
            or not all(
                isinstance(environment.get(field), str)
                and bool(environment[field].strip())
                for field in ("platform", "python_version")
            )
            or row.get("controller_environment_sha256")
            != runner.json_sha256(environment)
        ):
            blockers.append(f"{arm}/{task} lacks exact runtime version evidence")
        if arm.startswith("codex"):
            sandbox = settings.get("sandbox_policy")
            if (
                settings.get("approval_policy") != "never"
                or not isinstance(sandbox, dict)
                or sandbox.get("type") != "workspaceWrite"
                or sandbox.get("networkAccess") is not False
                or sandbox.get("writableRoots") != ["<workspace>"]
            ):
                blockers.append(f"{arm}/{task} lacks exact Codex isolation settings")
        elif settings.get("network_policy") != row.get("network_policy"):
            blockers.append(f"{arm}/{task} does not bind the Cursor network policy")
        if row.get("repo_revision") != row.get("seed_manifest_sha256"):
            blockers.append(f"{arm}/{task} repo revision is not bound to its fresh seed")
        repo_commit = str(row.get("repo_commit") or "")
        if len(repo_commit) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in repo_commit
        ):
            blockers.append(f"{arm}/{task} lacks an exact source repo commit")
        for field in (
            "started_at",
            "ended_at",
            "execution_wall_seconds",
            "evaluation_wall_seconds",
            "wall_time_seconds",
            "worker_metrics",
            "pex_metrics",
            "combined_metrics",
            "measurement_availability",
            "human_active_seconds",
            "human_intervention_log",
            "human_intervention_requests",
            "cost_usd",
            "raw_log_sha256",
            "repo_commit",
            "pex_version",
            "fail_reason",
            "budget_exhausted",
        ):
            if field not in row:
                blockers.append(f"{arm}/{task} lacks run-record field {field}")
        if row.get("budget_exhausted") is not False or row.get("fail_reason") is not None:
            blockers.append(f"{arm}/{task} is not a clean completed run")
        for field in ("execution_wall_seconds", "evaluation_wall_seconds", "wall_time_seconds"):
            value = row.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or value < 0
            ):
                blockers.append(f"{arm}/{task} has invalid {field}")
        execution = row.get("execution_wall_seconds")
        cap = (row.get("budget") or {}).get("task_wall_seconds")
        if isinstance(execution, (int, float)) and not isinstance(execution, bool) and (
            not isinstance(cap, (int, float))
            or isinstance(cap, bool)
            or execution > cap
        ):
            blockers.append(f"{arm}/{task} exceeded its worker-plus-PEX budget")
        try:
            started_at = datetime.fromisoformat(
                str(row.get("started_at") or "").replace("Z", "+00:00")
            )
            ended_at = datetime.fromisoformat(
                str(row.get("ended_at") or "").replace("Z", "+00:00")
            )
            if started_at.tzinfo is None or ended_at.tzinfo is None or ended_at < started_at:
                raise ValueError
            wall = row.get("wall_time_seconds")
            if not isinstance(wall, (int, float)) or isinstance(wall, bool) or not math.isclose(
                (ended_at - started_at).total_seconds(),
                float(wall),
                abs_tol=1.0,
            ):
                raise ValueError
        except ValueError:
            blockers.append(f"{arm}/{task} has invalid run timestamps")
        worker_metrics = row.get("worker_metrics")
        pex_metrics = row.get("pex_metrics")
        combined_metrics = row.get("combined_metrics")
        availability = row.get("measurement_availability")
        if not all(
            isinstance(value, dict)
            for value in (worker_metrics, pex_metrics, combined_metrics, availability)
        ):
            blockers.append(f"{arm}/{task} lacks structured overhead metrics")
        else:
            blockers.extend(
                f"{arm}/{task} has invalid resource metrics: {error}"
                for error in runner.resource_metric_errors(row)
            )
            blockers.extend(
                f"{arm}/{task} has invalid PEX audit accounting: {error}"
                for error in runner.pex_audit_errors(row)
            )
            if availability.get("raw_log_hash") is not True:
                blockers.append(f"{arm}/{task} does not retain a raw harness event log")
            else:
                blockers.extend(_raw_log_blockers(path, row, arm, task))
        intervention_log = row.get("human_intervention_log")
        human_interventions = row.get("human_interventions")
        human_requests = row.get("human_intervention_requests")
        if (
            not isinstance(intervention_log, list)
            or not isinstance(human_interventions, int)
            or isinstance(human_interventions, bool)
            or human_interventions < 0
            or len(intervention_log) != human_interventions
            or not isinstance(human_requests, int)
            or isinstance(human_requests, bool)
            or human_requests < 0
            or any(
                not isinstance(item, dict)
                or not str(item.get("action") or "").strip()
                or not str(item.get("timestamp") or "").strip()
                for item in (intervention_log or [])
            )
        ):
            blockers.append(f"{arm}/{task} human interventions lack exact action evidence")
        else:
            try:
                run_started = datetime.fromisoformat(
                    str(row.get("started_at") or "").replace("Z", "+00:00")
                )
                run_ended = datetime.fromisoformat(
                    str(row.get("ended_at") or "").replace("Z", "+00:00")
                )
                action_times = [
                    datetime.fromisoformat(
                        str(item["timestamp"]).replace("Z", "+00:00")
                    )
                    for item in intervention_log
                ]
                if run_started.tzinfo is None or run_ended.tzinfo is None or any(
                    action_time.tzinfo is None
                    or action_time < run_started
                    or action_time > run_ended
                    for action_time in action_times
                ):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                blockers.append(
                    f"{arm}/{task} human intervention timestamps fall outside the run"
                )
        proof = row.get("isolation_proof") or {}
        expected_workspace_name = boundary.opaque_workspace_name(path.stem, arm, task)
        cwd = Path(str(row.get("cwd") or ""))
        if (
            row.get("isolated") is not True
            or proof.get("mode") != "fresh_seeded_workspace"
            or proof.get("prepared_before_worker") is not True
            or proof.get("workspace_name") != expected_workspace_name
            or not _is_sha256(proof.get("receipt_sha256"))
            or not str(proof.get("receipt_path") or "").strip()
            or not cwd.is_absolute()
            or cwd.name != expected_workspace_name
        ):
            blockers.append(f"{arm}/{task} lacks fresh-workspace isolation proof")
        for field in (
            "prompt_sha256",
            "seed_manifest_sha256",
            "final_workspace_sha256",
            "worker_config_sha256",
            "harness_identity_sha256",
        ):
            if not _is_sha256(row.get(field)):
                blockers.append(f"{arm}/{task} has invalid {field}")
        expected_prompt, expected_seed = _expected_task_evidence(task)
        if row.get("prompt_sha256") != expected_prompt:
            blockers.append(f"{arm}/{task} prompt fingerprint is not canonical")
        if row.get("seed_manifest_sha256") != expected_seed:
            blockers.append(f"{arm}/{task} seed fingerprint is not canonical")
        blockers.extend(_provenance_blockers(path, row, arm, task))
        evidence = row.get("transport_evidence") or {}
        thread_id = str(row.get("thread_id") or "").strip()
        if not thread_id or len(thread_id) > 256:
            blockers.append(f"{arm}/{task} lacks a bounded worker session id")
        if arm.startswith("codex") and (
            row.get("transport_kind") != "codex_stdio"
            or not isinstance(evidence.get("pid"), int)
            or int(evidence["pid"]) <= 0
        ):
            blockers.append(f"{arm}/{task} lacks live Codex stdio evidence")
        if arm.startswith("cursor") and (
            row.get("transport_kind") != "cursor_hooks"
            or evidence.get("process") != "Cursor.exe"
            or not evidence.get("conversation_id")
            or evidence.get("conversation_id") != thread_id
        ):
            blockers.append(f"{arm}/{task} lacks live Cursor hook evidence")
        if arm.endswith("_pex"):
            pex = row.get("pex") or {}
            if not pex.get("supervisor_process_isolated"):
                blockers.append(f"{arm}/{task} supervisor was not process-isolated")
            if not pex.get("used_llm") or not pex.get("audits"):
                blockers.append(f"{arm}/{task} lacks a real supervisor audit")
            if not _is_sha256(row.get("pex_config_sha256")):
                blockers.append(f"{arm}/{task} lacks a PEX configuration fingerprint")
            if arm == "cursor_pex":
                continuation = evidence.get("same_session_continuation") or {}
                followups = pex.get("followups")
                if (
                    continuation.get("confirmed") is not True
                    or continuation.get("conversation_id") != row.get("thread_id")
                    or not continuation.get("initial_stop_id")
                    or not continuation.get("followup_stop_id")
                    or continuation.get("initial_stop_id")
                    == continuation.get("followup_stop_id")
                    or not isinstance(followups, int)
                    or followups < 1
                ):
                    blockers.append(
                        f"{arm}/{task} lacks proven same-session Cursor continuation"
                    )
        elif row.get("pex") is not None:
            blockers.append(f"{arm}/{task} baseline unexpectedly contains PEX state")

    expected_order = [
        (str(item["arm"]), str(item["task"])) for item in runner.experiment_plan()
    ]
    actual_order = [
        (str(row.get("arm") or ""), str(row.get("task") or ""))
        for row in rows
        if row.get("record_type") != "abort"
    ]
    if actual_order != expected_order:
        blockers.append(f"{path.stem} rows do not follow the predeclared randomized order")

    missing: list[str] = []
    for arm in PRESENTATION_ARMS:
        for task in evaluator.task_ids():
            row = by_key.get(f"{arm}:{task}")
            if row is None:
                missing.append(f"no result for {arm}/{task}")
    for harness in ("cursor", "codex"):
        harness_rows = [
            row
            for row in by_key.values()
            if row.get("arm") in {harness, f"{harness}_pex"}
        ]
        for field in (
            "worker_model",
            "worker_config_sha256",
            "model_settings_sha256",
            "harness_identity_sha256",
            "harness_version",
            "controller_environment_sha256",
        ):
            values = {str(row.get(field) or "") for row in harness_rows}
            if len(values) != 1 or "" in values:
                missing.append(f"{harness} rows do not share one pinned {field}")
        for task in evaluator.task_ids():
            baseline = by_key.get(f"{harness}:{task}")
            treatment = by_key.get(f"{harness}_pex:{task}")
            if not baseline or not treatment:
                continue
            for field in (
                "pair_id",
                "prompt_sha256",
                "seed_manifest_sha256",
                "worker_config_sha256",
                "model_settings_sha256",
                "worker_model",
                "harness_identity_sha256",
                "harness_version",
                "benchmark_sha256",
                "controller_sha256",
                "evaluator_sha256",
                "manifest_sha256",
                "task_package_sha256",
            ):
                if not baseline.get(field) or baseline.get(field) != treatment.get(field):
                    missing.append(f"{harness}/{task} paired {field} mismatch")
            if not treatment.get("pex_process_isolated"):
                # Kept for compatibility with older records whose isolation bit
                # lived at the row root; the canonical check above uses row.pex.
                if not (treatment.get("pex") or {}).get("supervisor_process_isolated"):
                    missing.append(f"{harness}_pex/{task} supervisor was not process-isolated")
    pex_configs = {
        str(row.get("pex_config_sha256") or "")
        for row in by_key.values()
        if str(row.get("arm") or "").endswith("_pex")
    }
    if len(pex_configs) != 1 or "" in pex_configs:
        missing.append("treatment rows do not share one pinned PEX configuration")
    return blockers + missing


def coherent_presentation_runs() -> list[dict[str, Any]]:
    if not runner.RESULTS.exists():
        return []
    complete: list[dict[str, Any]] = []
    for path in sorted(runner.RESULTS.glob("*.jsonl")):
        blockers = _run_blockers(path)
        if not blockers:
            complete.append(
                {
                    "run_id": path.stem,
                    "path": path,
                    "sha256": boundary.sha256_file(
                        path,
                        max_bytes=runner._MAX_RESULT_BYTES,
                    ),
                    "benchmark_sha256": runner.benchmark_sha256(),
                }
            )
    return complete


def freeze_blockers(
    coverage: dict[str, dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> list[str]:
    """Require one coherent four-arm run; never merge coverage across files."""
    del coverage  # merged coverage is diagnostic only and can never justify a freeze
    if run_id:
        try:
            selected = runner.result_path(run_id)
        except ValueError as exc:
            return [str(exc)]
        if not selected.is_file():
            return [f"requested run {run_id!r} does not exist"]
        return _run_blockers(selected)
    coherent = coherent_presentation_runs()
    if len(coherent) == 1:
        return []
    if len(coherent) > 1:
        return ["multiple coherent runs exist; select one explicitly with --run-id"]
    paths = sorted(runner.RESULTS.glob("*.jsonl")) if runner.RESULTS.exists() else []
    if not paths:
        return _report_readiness_blockers() + [
            f"no result for {arm}/{task}"
            for arm in PRESENTATION_ARMS
            for task in evaluator.task_ids()
        ]
    closest = min(paths, key=lambda item: len(_run_blockers(item)))
    return [
        "no single immutable result file contains a coherent four-arm experiment",
        *(_run_blockers(closest)),
    ]


def try_freeze(run_id: str | None = None) -> dict[str, Any]:
    blockers = freeze_blockers(run_id=run_id)
    if blockers:
        return {
            "frozen": False,
            "wrote": False,
            "blockers": blockers,
            "note": (
                "Manifest stays unfrozen until every presentation arm has a live evaluator row."
            ),
        }
    coherent = coherent_presentation_runs()
    if run_id:
        selected = [item for item in coherent if item["run_id"] == run_id]
        if not selected:
            return {
                "frozen": False,
                "wrote": False,
                "blockers": [f"requested run {run_id!r} is not coherent"],
            }
        chosen = selected[0]
    elif len(coherent) == 1:
        chosen = coherent[0]
    else:
        return {
            "frozen": False,
            "wrote": False,
            "blockers": [
                "multiple coherent runs exist; select one explicitly with --run-id"
            ],
        }
    public_summary = runner.RESULTS / "frozen_summary.json"
    public_summary.parent.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(8)
    summary_tmp = public_summary.with_name(f".{public_summary.name}.{nonce}.tmp")
    manifest_tmp = runner.MANIFEST.with_name(f".{runner.MANIFEST.name}.{nonce}.tmp")
    try:
        with runner._exclusive_result_lock(runner.MANIFEST), runner._exclusive_result_lock(
            chosen["path"]
        ):
            manifest = runner.load_manifest()
            if manifest.get("frozen"):
                return {
                    "frozen": False,
                    "wrote": False,
                    "blockers": [
                        "manifest is already frozen; refusing to replace its provenance"
                    ],
                }
            locked_blockers = _run_blockers(chosen["path"])
            if locked_blockers:
                return {
                    "frozen": False,
                    "wrote": False,
                    "blockers": ["run changed before freeze commit", *locked_blockers],
                }
            before = boundary.sha256_file(
                chosen["path"],
                max_bytes=runner._MAX_RESULT_BYTES,
            )
            if before != chosen["sha256"]:
                return {
                    "frozen": False,
                    "wrote": False,
                    "blockers": ["raw result changed during freeze validation"],
                }
            summary = _public_summary(chosen)
            manifest["frozen"] = True
            manifest["frozen_at"] = datetime.now(UTC).isoformat()
            manifest["frozen_run_id"] = chosen["run_id"]
            manifest["frozen_result_sha256"] = chosen["sha256"]
            manifest["frozen_benchmark_sha256"] = chosen["benchmark_sha256"]
            manifest["frozen_task_count"] = len(evaluator.task_ids())
            _write_text_fsync(
                summary_tmp,
                json.dumps(summary, indent=2, allow_nan=False) + "\n",
            )
            _write_text_fsync(
                manifest_tmp,
                yaml.safe_dump(manifest, sort_keys=False),
            )
            if (
                boundary.sha256_file(
                    chosen["path"],
                    max_bytes=runner._MAX_RESULT_BYTES,
                )
                != chosen["sha256"]
            ):
                return {
                    "frozen": False,
                    "wrote": False,
                    "blockers": ["raw result changed before freeze commit"],
                }
            # Commit the authoritative manifest before publishing score-shaped output.
            # A crash can therefore leave a frozen manifest without a public summary,
            # which fails closed; it can never expose a frozen summary while the
            # manifest still says ``frozen: false``.
            os.replace(manifest_tmp, runner.MANIFEST)
            try:
                os.replace(summary_tmp, public_summary)
            except OSError as exc:
                return {
                    "frozen": True,
                    "wrote": False,
                    "blockers": [f"manifest froze but public summary commit failed: {exc}"],
                }
    except ValueError as exc:
        return {"frozen": False, "wrote": False, "blockers": [str(exc)]}
    finally:
        summary_tmp.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)
    return {
        "frozen": True,
        "wrote": True,
        "blockers": [],
        "run_id": chosen["run_id"],
        "result_sha256": chosen["sha256"],
        "benchmark_sha256": chosen["benchmark_sha256"],
        "public_summary": str(public_summary),
    }


def _public_summary(run: dict[str, Any]) -> dict[str, Any]:
    """Publish aggregate metrics only; worker logs and evaluator reasons stay private."""
    rows, errors = _read_rows(run["path"])
    if errors:
        raise RuntimeError("cannot summarize an invalid result file")
    created_at = max((str(row.get("ts") or "") for row in rows), default="")
    public_runs: list[dict[str, Any]] = []
    for arm in PRESENTATION_ARMS:
        arm_rows = [row for row in rows if row.get("arm") == arm]
        successes = sum(bool(row.get("success")) for row in arm_rows)
        human_interventions = sum(int(row.get("human_interventions") or 0) for row in arm_rows)
        audits = [
            audit
            for row in arm_rows
            for audit in ((row.get("pex") or {}).get("audits") or [])
            if isinstance(audit, dict)
        ]
        intervention_judgments = [
            (audit.get("result_afterward") or {}).get("helped")
            for audit in audits
            if audit.get("actual_action_sent")
            and isinstance(audit.get("result_afterward"), dict)
            and type((audit.get("result_afterward") or {}).get("helped")) is bool
        ]
        useful = sum(value is True for value in intervention_judgments)
        harmful = sum(value is False for value in intervention_judgments)
        # Count only actions the harness demonstrably delivered. A supervisor proposal
        # is not a handoff receipt and must never become public score-shaped evidence.
        handoffs = sum(audit.get("actual_action_sent") == "FRESH_HANDOFF" for audit in audits)
        harness = arm.removesuffix("_pex")
        pex_token_rows = [row.get("pex_metrics") or {} for row in arm_rows]
        pex_tokens_available = all(
            metrics.get("tokens_available") is True for metrics in pex_token_rows
        )
        supervisor_input_tokens = (
            sum(int(metrics.get("input_tokens") or 0) for metrics in pex_token_rows)
            if pex_tokens_available
            else None
        )
        supervisor_output_tokens = (
            sum(int(metrics.get("output_tokens") or 0) for metrics in pex_token_rows)
            if pex_tokens_available
            else None
        )
        public_runs.append(
            {
                "id": f"{run['run_id']}:{arm}",
                "name": arm.replace("_", " + ").title(),
                "status": "frozen",
                "arm": arm,
                "harness": harness,
                "created_at": created_at,
                "manifest_hash": runner.manifest_sha256(),
                "benchmark_hash": run["benchmark_sha256"],
                "frozen": True,
                "metrics": {
                    "task_success_rate": successes / len(arm_rows),
                    "human_interventions_per_success": (
                        human_interventions / successes if successes else None
                    ),
                    "useful_interventions": useful
                    if intervention_judgments or not arm.endswith("_pex")
                    else None,
                    "harmful_interventions": harmful
                    if intervention_judgments or not arm.endswith("_pex")
                    else None,
                    "context_handoffs": handoffs,
                    "pex_input_tokens": supervisor_input_tokens,
                    "pex_output_tokens": supervisor_output_tokens,
                    "tasks": len(arm_rows),
                },
            }
        )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id": run["run_id"],
        "manifest_sha256": runner.manifest_sha256(),
        "benchmark_sha256": run["benchmark_sha256"],
        "result_sha256": run["sha256"],
        "runs": public_runs,
        "note": "Aggregate frozen benchmark evidence; raw worker logs are intentionally excluded.",
    }


def run_synthetic(task_id: str, run_id: str = "synthetic_smoke") -> dict[str, Any]:
    with TemporaryDirectory(prefix="pexbench_") as tmp:
        workspace = Path(tmp) / task_id
        seed = evaluator.seed_workspace(task_id, workspace)
        extra = evaluator.complete_synthetic(task_id, workspace)
        extra.update(seed)
        result = evaluator.evaluate(task_id, workspace, extra)
        path = runner.RESULTS / f"{run_id}.jsonl"
        runner.write_synthetic_smoke(
            path,
            success=bool(result["success"]),
            human_interventions=0,
            task=task_id,
            extra={"reasons": result["reasons"]},
        )
        result["arm"] = "synthetic_pex"
        result["written"] = str(path)
        return result


def isolated_workspace(
    run_id: str,
    arm: str,
    task_id: str,
    workspace_root: Path | None = None,
) -> Path:
    """Host-visible isolated dir. Folder name is opaque so cwd does not leak the stressor."""
    base = Path(workspace_root) if workspace_root else (Path.home() / ".pex" / "pexbench")
    candidate = base / "workspaces" / boundary.opaque_workspace_name(run_id, arm, task_id)
    if _path_has_link_component(candidate, base):
        raise RuntimeError("refusing a linked benchmark workspace")
    path = candidate.resolve()
    path.mkdir(parents=True, exist_ok=True)
    if runner._is_link_like(path):
        raise RuntimeError("refusing a linked benchmark workspace")
    return path


def _seed_receipt_path(workspace: Path) -> Path:
    # Keep controller provenance outside the worker-visible workspace tree. The
    # receipt contains arm/task identity and must never be an adjacent handoff
    # artifact that a worker can discover with ``..`` traversal.
    return runner.RESULTS / "_scratch" / "_receipts" / f"{workspace.name}.json"


def prepare_isolated_workspace(
    run_id: str,
    arm: str,
    task_id: str,
    workspace_root: Path | None = None,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    """Create a fresh seed and an external receipt before any worker begins."""
    workspace = isolated_workspace(run_id, arm, task_id, workspace_root)
    receipt_path = _seed_receipt_path(workspace)
    if any(workspace.iterdir()) or receipt_path.exists():
        raise RuntimeError(
            "refusing to reuse a benchmark workspace or seed receipt; choose a new run id"
        )
    seed = evaluator.seed_workspace(task_id, workspace)
    prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
    boundary.assert_public_prompt(task_id, prompt)
    receipt = {
        "schema_version": 1,
        "run_id": run_id,
        "arm": arm,
        "task": task_id,
        "workspace": str(workspace.resolve()),
        "workspace_name": workspace.name,
        "prepared_at": datetime.now(UTC).isoformat(),
        "prepared_before_worker": True,
        "seed_manifest_sha256": boundary.workspace_manifest_sha256(workspace),
        "prompt_sha256": boundary.sha256_text(prompt),
        "task_package_sha256": runner.task_package_sha256(),
        "benchmark_sha256": runner.benchmark_sha256(),
        "nonce": secrets.token_hex(16),
    }
    if _path_has_link_component(receipt_path, runner.RESULTS):
        raise RuntimeError("refusing a linked benchmark receipt path")
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_text_fsync(
            receipt_path,
            json.dumps(
                receipt,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n",
        )
    except FileExistsError as exc:
        raise RuntimeError("benchmark seed receipt was created concurrently") from exc
    if arm in {"cursor", "cursor_pex"}:
        _write_cursor_isolated_control(run_id, arm, task_id, workspace, seed)
    return workspace, seed, receipt


def _cursor_private_control_dir(run_id: str, arm: str, task_id: str) -> Path:
    return runner.RESULTS / "_scratch" / "_private_control" / run_id / arm / task_id


def _isolated_hook_control_path(workspace: Path) -> Path:
    override = os.environ.get("PEX_CURSOR_ISOLATED_CONTROL")
    if override:
        return Path(override) / f"{workspace.name}.json"
    return runner.RESULTS / "_scratch" / "_control" / f"{workspace.name}.json"


def _write_cursor_isolated_control(
    run_id: str,
    arm: str,
    task_id: str,
    workspace: Path,
    seed: dict[str, Any],
) -> None:
    """Publish an out-of-band pointer the this-desktop stop hook can find."""
    control_dir = _cursor_private_control_dir(run_id, arm, task_id)
    if _path_has_link_component(control_dir, runner.RESULTS):
        raise RuntimeError("refusing a linked isolated Cursor control directory")
    control_dir.mkdir(parents=True, exist_ok=True)
    script = (ROOT / "cursor_isolated_stop.py").resolve()
    if not script.is_file() or runner._is_link_like(script):
        raise RuntimeError("isolated Cursor supervisor script is missing")
    timeout = min(
        float(runner.protocol_config()["budget"]["max_supervisor_decision_seconds"]),
        40.0,
    )
    public_test = str((seed.get("protected_sha256") or {}).get("test_public.py") or "")
    payload = {
        "schema_version": 1,
        "arm": arm,
        "workspace": str(workspace.resolve()),
        "control_dir": str(control_dir.resolve()),
        "python": sys.executable,
        "script": str(script),
        "isolated_supervisor": arm == "cursor_pex",
        "public_test_sha256": public_test or None,
        "decision_timeout": timeout,
    }
    path = _isolated_hook_control_path(workspace)
    if override := os.environ.get("PEX_CURSOR_ISOLATED_CONTROL"):
        if _path_has_link_component(path, Path(override)):
            raise RuntimeError("refusing a linked isolated Cursor hook control path")
    elif _path_has_link_component(path, runner.RESULTS):
        raise RuntimeError("refusing a linked isolated Cursor hook control path")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _write_text_fsync(
            path,
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        )
    except FileExistsError as exc:
        raise RuntimeError("isolated Cursor hook control was created concurrently") from exc


def _load_cursor_isolated_pex_meta(
    run_id: str,
    arm: str,
    task_id: str,
) -> dict[str, Any] | None:
    if arm != "cursor_pex":
        return None
    path = _cursor_private_control_dir(run_id, arm, task_id) / "pex_meta.json"
    if (
        _path_has_link_component(path, runner.RESULTS)
        or not _bounded_regular_file(path, _MAX_CONTROL_FILE_BYTES, allow_empty=False)
    ):
        return None
    try:
        meta = json.loads(
            path.read_bytes().decode("utf-8"),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError("non-finite JSON number")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return None
    if (
        not isinstance(meta, dict)
        or meta.get("supervisor_process_isolated") is not True
        or not isinstance(meta.get("audits"), list)
        or not isinstance(meta.get("followups"), int)
        or int(meta["followups"]) < 0
    ):
        return None
    return meta


def _load_seed_receipt(
    workspace: Path,
    run_id: str,
    arm: str,
    task_id: str,
) -> dict[str, Any]:
    path = _seed_receipt_path(workspace)
    if (
        _path_has_link_component(path, runner.RESULTS)
        or not _bounded_regular_file(path, _MAX_CONTROL_FILE_BYTES, allow_empty=False)
    ):
        raise RuntimeError(
            "refusing post-hoc benchmark stamping: workspace was not prepared before the worker"
        )
    try:
        receipt = json.loads(
            path.read_bytes().decode("utf-8"),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {constant}")
            ),
            object_pairs_hook=runner._unique_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError("invalid benchmark seed receipt") from exc
    if not isinstance(receipt, dict):
        raise RuntimeError("invalid benchmark seed receipt")
    expected = {
        "schema_version": 1,
        "run_id": run_id,
        "arm": arm,
        "task": task_id,
        "workspace": str(workspace.resolve()),
        "workspace_name": workspace.name,
        "prepared_before_worker": True,
        "task_package_sha256": runner.task_package_sha256(),
        "benchmark_sha256": runner.benchmark_sha256(),
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise RuntimeError("benchmark seed receipt does not match this run, arm, task, or suite")
    canonical_seed, _ = _canonical_seed(task_id)
    if receipt.get("seed_manifest_sha256") != canonical_seed:
        raise RuntimeError("benchmark seed receipt has a stale seed fingerprint")
    if receipt.get("prompt_sha256") != boundary.sha256_text(evaluator.prompt_text(task_id)):
        raise RuntimeError("benchmark seed receipt has a stale prompt fingerprint")
    nonce = str(receipt.get("nonce") or "")
    if len(nonce) != 32 or any(character not in "0123456789abcdef" for character in nonce):
        raise RuntimeError("benchmark seed receipt nonce is invalid")
    try:
        prepared_at = datetime.fromisoformat(
            str(receipt.get("prepared_at") or "").replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise RuntimeError("benchmark seed receipt time is invalid") from exc
    if prepared_at.tzinfo is None:
        raise RuntimeError("benchmark seed receipt time must include a timezone")
    return receipt


def _isolation_proof(workspace: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    receipt_path = _seed_receipt_path(workspace)
    if not _bounded_regular_file(receipt_path, _MAX_CONTROL_FILE_BYTES, allow_empty=False):
        raise RuntimeError("benchmark seed receipt changed or disappeared")
    return {
        "mode": "fresh_seeded_workspace",
        "prepared_before_worker": receipt.get("prepared_before_worker") is True,
        "prepared_at": receipt.get("prepared_at"),
        "workspace_name": workspace.name,
        "receipt_path": str(receipt_path.resolve()),
        "receipt_sha256": boundary.sha256_file(
            receipt_path,
            max_bytes=_MAX_CONTROL_FILE_BYTES,
        ),
    }


def cursor_hooks_path() -> Path:
    return Path.home() / ".cursor" / "hooks.json"


def _cursor_hook_mode(hooks: Path) -> str | None:
    if not hooks.is_file():
        return None
    try:
        data = json.loads(hooks.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "unreadable"
    groups = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(groups, dict):
        return "unknown"
    commands: list[str] = []
    fail_closed = False
    for rows in groups.values():
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            command = str(item.get("command") or "")
            if command:
                commands.append(command)
            if item.get("failClosed") is True:
                fail_closed = True
    joined = "\n".join(commands)
    if "pex_cursor_observe.py" in joined and not fail_closed:
        return "observe"
    if "pex_cursor_hook.py" in joined or "pex-cursor-hook" in joined:
        return "control" if fail_closed else "unknown"
    return "absent"


def _canonical_seed(task_id: str) -> tuple[str, dict[str, Any]]:
    """Hash the public stubs, not a workspace the worker already edited."""
    with TemporaryDirectory(
        prefix="pexbench_seed_", ignore_cleanup_errors=True
    ) as tmp:
        seeded = Path(tmp) / "seed"
        extra = evaluator.seed_workspace(task_id, seeded)
        return boundary.workspace_manifest_sha256(seeded), extra


def cursor_stop_drop_dir() -> Path:
    override = os.environ.get("PEX_CURSOR_STOP_DROP")
    if override:
        return Path(override)
    return Path(os.environ.get("PEX_HOME", Path.home() / ".pex")) / "pexbench" / "stops"


def _cursor_stop_cwd(payload: dict) -> Path | None:
    raw = payload.get("cwd") or payload.get("workspace") or ""
    if not raw and isinstance(payload.get("workspace_roots"), list) and payload["workspace_roots"]:
        raw = payload["workspace_roots"][0]
    if not raw:
        return None
    try:
        candidate = Path(str(raw))
        if not candidate.is_absolute():
            return None
        return candidate.resolve()
    except (OSError, ValueError):
        return None


def _cursor_conversation_id(payload: dict[str, Any]) -> str:
    return str(
        payload.get("conversation_id")
        or payload.get("session_id")
        or payload.get("composer_id")
        or ""
    ).strip()


def _cursor_stop_id(payload: dict[str, Any], path: Path | None = None) -> str:
    stop_id = str(payload.get("stop_id") or (path.stem if path is not None else "")).strip()
    return stop_id[:256]


async def wait_for_matching_cursor_stop(workspace: Path, timeout: float) -> dict[str, Any]:
    """Block until this Cursor.exe writes a stop drop whose cwd is the isolated workspace."""
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 3_600:
        raise ValueError("Cursor stop wait timeout must be finite and at most one hour")
    deadline = time.monotonic() + timeout
    seen: set[Path] = set()
    target = workspace.resolve()
    while time.monotonic() < deadline:
        drop = cursor_stop_drop_dir()
        if drop.is_dir():
            for path in drop.glob("*.json"):
                if path in seen:
                    continue
                try:
                    payload = _load_control_json(path)
                except ValueError:
                    continue
                seen.add(path)
                if payload.get("kind") == "followup_delivery":
                    continue
                if _cursor_stop_cwd(payload) == target:
                    payload.setdefault("stop_id", path.stem)
                    return payload
        await asyncio.sleep(0.25)
    raise RuntimeError(CURSOR_LIVE_REFUSAL)


async def wait_for_cursor_treatment_chain(
    workspace: Path, timeout: float
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Wait for initial stop + delivered follow-up + later stop in the same conversation."""
    if not math.isfinite(timeout) or timeout <= 0 or timeout > 3_600:
        raise ValueError("Cursor stop wait timeout must be finite and at most one hour")
    deadline = time.monotonic() + timeout
    seen: set[Path] = set()
    inbound: dict[str, dict[str, Any]] = {}
    deliveries: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    target = workspace.resolve()
    while time.monotonic() < deadline:
        drop = cursor_stop_drop_dir()
        if drop.is_dir():
            for path in drop.glob("*.json"):
                if path in seen:
                    continue
                try:
                    payload = _load_control_json(path)
                except ValueError:
                    continue
                seen.add(path)
                if _cursor_stop_cwd(payload) != target:
                    continue
                stop_id = _cursor_stop_id(payload, path)
                if not stop_id:
                    continue
                payload["stop_id"] = stop_id
                if payload.get("kind") == "followup_delivery":
                    followup = str(payload.get("pex_followup_message") or "").strip()
                    initial = str(payload.get("initial_stop_id") or "").strip()
                    if followup and not followup.startswith("PEX:") and initial:
                        deliveries[initial] = payload
                    continue
                if stop_id not in inbound:
                    order.append(stop_id)
                    inbound[stop_id] = payload
        by_conversation: dict[str, list[str]] = {}
        for stop_id in order:
            conversation = _cursor_conversation_id(inbound[stop_id])
            if conversation:
                by_conversation.setdefault(conversation, []).append(stop_id)
        for conversation, stop_ids in by_conversation.items():
            delivered = [stop_id for stop_id in stop_ids if stop_id in deliveries]
            if not delivered or len(stop_ids) < 2:
                continue
            initial_stop_id = delivered[0]
            later = next(
                (stop_id for stop_id in stop_ids if stop_id != initial_stop_id),
                "",
            )
            if not later:
                continue
            return (
                inbound[initial_stop_id],
                inbound[later],
                {
                    "confirmed": True,
                    "conversation_id": conversation,
                    "initial_stop_id": initial_stop_id,
                    "followup_stop_id": later,
                },
            )
        await asyncio.sleep(0.25)
    raise RuntimeError(CURSOR_TREATMENT_REFUSAL)


def _snapshot_workspace(run_id: str, arm: str, task_id: str, workspace: Path) -> Path | None:
    dest = runner.RESULTS / "_scratch" / run_id / arm / task_id
    if _path_has_link_component(dest, runner.RESULTS):
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copytree(
            workspace,
            dest,
            ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"),
        )
    except (FileExistsError, OSError):
        return None
    return dest


def _codex_harness_version(server_info: object) -> str:
    if not isinstance(server_info, dict):
        return "unknown"
    candidates = [server_info.get("version")]
    for key in ("serverInfo", "server_info"):
        nested = server_info.get(key)
        if isinstance(nested, dict):
            candidates.append(nested.get("version"))
    version = next(
        (str(value).strip() for value in candidates if str(value or "").strip()),
        "unknown",
    )
    if len(version) > 256 or any(ord(character) < 32 for character in version):
        return "unknown"
    return version


def _cursor_benchmark_timing(payload: dict[str, Any]) -> tuple[str, str, float] | None:
    """Accept only explicit synchronous-controller timing, never infer from file times."""
    started = str(payload.get("benchmark_started_at") or "").strip()
    ended = str(payload.get("benchmark_ended_at") or "").strip()
    if not started or not ended:
        return None
    try:
        start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(ended.replace("Z", "+00:00"))
    except ValueError:
        return None
    elapsed = (end_dt - start_dt).total_seconds()
    if start_dt.tzinfo is None or end_dt.tzinfo is None or not 0 <= elapsed <= 86_400:
        return None
    return started, ended, elapsed


def _pex_config_fingerprint(pex_meta: dict[str, Any] | None) -> str | None:
    if not pex_meta:
        return None
    return boundary.sha256_text(
        json.dumps(
            {
                "backend": pex_meta.get("backend") or {},
                "max_followups": int(
                    runner.protocol_config()["budget"]["max_pex_followups"]
                ),
                "supervisor_process": runner._bounded_file_sha256(
                    ROOT / "pex_supervisor_process.py",
                    runner._MAX_CONTROLLER_FILE_BYTES,
                    "benchmark PEX supervisor process",
                ),
                "cursor_isolated_stop": runner._bounded_file_sha256(
                    ROOT / "cursor_isolated_stop.py",
                    runner._MAX_CONTROLLER_FILE_BYTES,
                    "benchmark Cursor isolated stop process",
                ),
            },
            sort_keys=True,
            default=str,
        )
    )


def _runtime_record_fields(
    *,
    arm: str,
    task_id: str,
    seed_manifest_sha256: str,
    started_at: str,
    ended_at: str,
    worker_wall_seconds: float | None,
    pex_wall_seconds: float,
    evaluation_wall_seconds: float,
    total_wall_seconds: float,
    harness_version: str,
    model_settings: dict[str, Any],
    model_version_evidence: dict[str, Any] | None,
    pex_meta: dict[str, Any] | None,
    pex_config_sha256: str | None,
    item_types: list[str] | None = None,
    captured_events: object = None,
    raw_log_sha256: str | None = None,
) -> dict[str, Any]:
    """Build one honest §58 record: unknown measurements stay explicitly null."""
    audits = [
        audit
        for audit in ((pex_meta or {}).get("audits") or [])
        if isinstance(audit, dict)
    ]
    pex_input = sum(int(audit.get("input_tokens") or 0) for audit in audits)
    pex_output = sum(int(audit.get("output_tokens") or 0) for audit in audits)
    pex_tokens_available = bool(audits) and any(
        int(audit.get("input_tokens") or 0) + int(audit.get("output_tokens") or 0) > 0
        for audit in audits
    )
    worker_tokens_available = False
    tool_calls_available = item_types is not None
    tool_calls = (
        sum(
            kind not in {"agentMessage", "reasoning", "plan"}
            for kind in (item_types or [])
        )
        if tool_calls_available
        else None
    )
    pex_enabled = arm.endswith("_pex")
    pex_interventions = sum(bool(audit.get("actual_action_sent")) for audit in audits)
    execution_wall_seconds = (
        None
        if worker_wall_seconds is None
        else round(worker_wall_seconds + pex_wall_seconds, 6)
    )
    captured_event_sha256 = (
        boundary.sha256_text(json.dumps(captured_events, sort_keys=True, default=str))
        if captured_events is not None
        else None
    )
    controller_environment = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }
    return {
        **runner.protocol_record_fields(task_id, arm),
        "harness_version": harness_version,
        "model_settings": model_settings,
        "model_settings_sha256": runner.json_sha256(model_settings),
        "model_version_evidence": model_version_evidence
        or {
            "requested_model_id": model_settings.get("model"),
            "provider_revision": None,
            "provider_revision_available": False,
        },
        "controller_environment": controller_environment,
        "controller_environment_sha256": runner.json_sha256(controller_environment),
        "pex_version": pex_config_sha256 if pex_enabled else None,
        "repo_commit": None,
        "repo_revision": seed_manifest_sha256,
        "started_at": started_at,
        "ended_at": ended_at,
        "execution_wall_seconds": execution_wall_seconds,
        "evaluation_wall_seconds": round(evaluation_wall_seconds, 6),
        "wall_time_seconds": round(total_wall_seconds, 6),
        "human_active_seconds": None,
        "cost_usd": None,
        "raw_log_sha256": raw_log_sha256,
        "captured_event_sha256": captured_event_sha256,
        "fail_reason": None,
        "budget_exhausted": False,
        "worker_metrics": {
            "wall_seconds": None
            if worker_wall_seconds is None
            else round(worker_wall_seconds, 6),
            "input_tokens": None,
            "output_tokens": None,
            "tool_calls": tool_calls,
        },
        "pex_metrics": {
            "enabled": pex_enabled,
            "wall_seconds": round(pex_wall_seconds, 6) if pex_enabled else 0.0,
            "input_tokens": 0
            if not pex_enabled
            else pex_input
            if pex_tokens_available
            else None,
            "output_tokens": 0
            if not pex_enabled
            else pex_output
            if pex_tokens_available
            else None,
            "interventions": pex_interventions,
            "followups": int((pex_meta or {}).get("followups") or 0),
            "decision_count": len(audits),
            "tokens_available": pex_tokens_available if pex_enabled else True,
        },
        "combined_metrics": {
            "wall_seconds": execution_wall_seconds,
            "input_tokens": None,
            "output_tokens": None,
            "tokens_available": worker_tokens_available
            and (pex_tokens_available if pex_enabled else True),
        },
        "measurement_availability": {
            "worker_tokens": worker_tokens_available,
            "pex_tokens": pex_tokens_available if pex_enabled else True,
            "tool_calls": tool_calls_available,
            "human_active_seconds": False,
            "cost_usd": False,
            "raw_log_hash": raw_log_sha256 is not None,
            "repo_commit": False,
        },
    }


async def run_live_this_cursor(
    arm: str,
    task_id: str,
    run_id: str,
    *,
    stop_payload: dict[str, Any] | None = None,
    turn_timeout: float = 600,
    workspace_root: Path | None = None,
    worker_model: str | None = None,
    bridge_url: str | None = None,
    wait_cursor_stop: bool = False,
) -> dict[str, Any]:
    """This Cursor.exe via ~/.cursor/hooks.json. Never spawn another window."""
    if arm == "cursor_pex" and stop_payload is not None:
        # A saved payload is replay, not a same-conversation continuation.
        raise RuntimeError(CURSOR_TREATMENT_REFUSAL)
    if arm == "cursor_pex" and not wait_cursor_stop:
        raise RuntimeError(CURSOR_TREATMENT_REFUSAL)
    if stop_payload is not None:
        raise RuntimeError(CURSOR_REPLAY_REFUSAL)
    if not wait_cursor_stop:
        raise RuntimeError(CURSOR_LIVE_REFUSAL)
    if stop_payload is None and wait_cursor_stop:
        preflight = _execution_preflight_blockers()
        if preflight:
            raise RuntimeError(
                "benchmark execution preflight is NO-GO: " + "; ".join(preflight)
            )
        runner.assert_next_scheduled(run_id, task_id, arm)
    hooks = cursor_hooks_path()
    if not _bounded_regular_file(hooks, _MAX_CONTROL_FILE_BYTES, allow_empty=False):
        raise RuntimeError(
            "refusing live Cursor arm: ~/.cursor/hooks.json is not installed. "
            "Do not spawn another Cursor window."
        )
    from pex_bridge.adapters.cursor import CursorAdapter
    from pex_bridge.adapters.desktop import running_image_names

    workspace = isolated_workspace(run_id, arm, task_id, workspace_root)
    receipt_path = _seed_receipt_path(workspace)
    if receipt_path.is_file():
        receipt = _load_seed_receipt(workspace, run_id, arm, task_id)
        seed_manifest_sha256, seed = _canonical_seed(task_id)
        seed = {**seed, "task": task_id, "workspace": str(workspace)}
    elif stop_payload is None and wait_cursor_stop:
        workspace, seed, receipt = prepare_isolated_workspace(
            run_id, arm, task_id, workspace_root
        )
        seed_manifest_sha256 = str(receipt["seed_manifest_sha256"])
    else:
        raise RuntimeError(
            "refusing post-hoc Cursor row: prepare the isolated workspace before the worker"
        )
    prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
    boundary.assert_public_prompt(task_id, prompt)
    prompt_sha256 = boundary.sha256_text(prompt)
    continuation: dict[str, Any] | None = None
    if stop_payload is None:
        print(
            (
                f"waiting for this-desktop stop hook cwd={workspace} "
                "(never spawn another Cursor)"
                + (
                    "; Cursor+PEX needs delivered follow-up then a later same-conversation stop"
                    if arm == "cursor_pex"
                    else ""
                )
            ),
            file=sys.stderr,
        )
        if arm == "cursor_pex":
            _initial_stop, stop_payload, continuation = await wait_for_cursor_treatment_chain(
                workspace, turn_timeout
            )
            del _initial_stop
        else:
            stop_payload = await wait_for_matching_cursor_stop(workspace, turn_timeout)
    hooked_cwd = _cursor_stop_cwd(stop_payload)
    if hooked_cwd != workspace.resolve():
        raise RuntimeError(
            "refusing live Cursor arm: stop hook cwd does not match the isolated workspace. "
            "do not spawn another Cursor window."
        )
    hook_name = str(stop_payload.get("hook_event_name") or stop_payload.get("hook") or "")
    conversation_id = _cursor_conversation_id(stop_payload)
    if hook_name.lower() != "stop" or not conversation_id:
        raise RuntimeError(
            "refusing live Cursor row without a stop event and stable conversation id"
        )
    adapter = CursorAdapter(bridge_url=bridge_url)
    session = adapter.upsert_from_hook({**stop_payload, "cwd": str(workspace)})
    text = str(
        stop_payload.get("completion")
        or stop_payload.get("text")
        or stop_payload.get("message")
        or ""
    )
    if len(text) > _MAX_RECORD_TEXT_CHARS:
        raise RuntimeError("Cursor completion exceeds the benchmark text bound")
    adapter.isolated_agent_messages = [text] if text else []
    adapter.last_turn_id = None
    pex_meta = _load_cursor_isolated_pex_meta(run_id, arm, task_id)
    if evaluator.stressor_type(task_id) == "permission_interruption":
        joined = " ".join(adapter.isolated_agent_messages).lower()
        if any(token in joined for token in ("should i run", "can i run pytest", "run pytest?")):
            seed["human_prompts_for_pytest"] = 1
    running = "cursor.exe" in {name.lower() for name in running_image_names()}
    payload_model = str(stop_payload.get("model_id") or stop_payload.get("model") or "").strip()
    if len(payload_model) > 256:
        raise RuntimeError("Cursor worker model exceeds the benchmark text bound")
    if worker_model and payload_model and worker_model != payload_model:
        raise RuntimeError("Cursor worker model does not match the stop-hook model")
    worker = worker_model or payload_model
    cursor_version = str(stop_payload.get("cursor_version") or "unknown")
    if len(cursor_version) > 256:
        raise RuntimeError("Cursor version exceeds the benchmark text bound")
    timing = _cursor_benchmark_timing(stop_payload)
    human_intervention_log = _human_intervention_log(
        stop_payload.get("benchmark_human_intervention_log")
    )
    intervention_evidence_available = human_intervention_log is not None
    verified_live = (
        running
        and _bounded_regular_file(hooks, _MAX_CONTROL_FILE_BYTES, allow_empty=False)
        and bool(worker)
        and cursor_version.lower() != "unknown"
        and timing is not None
        and intervention_evidence_available
    )
    if verified_live:
        preflight = _execution_preflight_blockers()
        if preflight:
            raise RuntimeError(
                "benchmark execution preflight is NO-GO: " + "; ".join(preflight)
            )
        runner.assert_next_scheduled(run_id, task_id, arm)
    evaluation_started_at = datetime.now(UTC)
    evaluation_started_perf = time.perf_counter()
    result = evaluator.evaluate(task_id, workspace, seed)
    final_workspace_sha256 = boundary.workspace_manifest_sha256(workspace)
    snapshot = _snapshot_workspace(run_id, arm, task_id, workspace)
    if snapshot is None:
        raise RuntimeError(
            "refusing result because the immutable workspace snapshot was not written"
        )
    evaluation_wall_seconds = time.perf_counter() - evaluation_started_perf
    controller_ended_at = datetime.now(UTC)
    hooks_sha256 = boundary.sha256_file(hooks, max_bytes=_MAX_CONTROL_FILE_BYTES)
    pex_config_sha256 = _pex_config_fingerprint(pex_meta)
    if timing is None:
        started_at = evaluation_started_at.isoformat()
        ended_at = controller_ended_at.isoformat()
        worker_wall_seconds = None
    else:
        started_at, worker_ended_at, worker_wall_seconds = timing
        ended_at = controller_ended_at.isoformat()
        del worker_ended_at
    total_wall_seconds = (
        datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
        - datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    ).total_seconds()
    if total_wall_seconds < 0:
        raise RuntimeError("Cursor benchmark timestamps place completion before start")
    runtime_fields = _runtime_record_fields(
        arm=arm,
        task_id=task_id,
        seed_manifest_sha256=seed_manifest_sha256,
        started_at=started_at,
        ended_at=ended_at,
        worker_wall_seconds=worker_wall_seconds,
        pex_wall_seconds=float((pex_meta or {}).get("supervisor_wall_seconds") or 0.0),
        evaluation_wall_seconds=evaluation_wall_seconds,
        total_wall_seconds=total_wall_seconds,
        harness_version=cursor_version,
        model_settings={
            "model": worker,
            "reasoning_effort": stop_payload.get("reasoning_effort"),
            "network_policy": runner.protocol_config()["network_policy"]["cursor"],
        },
        model_version_evidence={
            "requested_model_id": worker,
            "provider_revision": stop_payload.get("model_version"),
            "provider_revision_available": bool(stop_payload.get("model_version")),
        },
        pex_meta=pex_meta,
        pex_config_sha256=pex_config_sha256,
        item_types=None,
        captured_events={
            "hook_event_name": hook_name,
            "conversation_id": conversation_id,
            "completion": text,
        },
    )
    record = {
        **runtime_fields,
        "arm": arm,
        "task": task_id,
        "success": bool(result["success"]),
        "live": verified_live,
        "not_a_presentation_arm": not verified_live,
        "isolated": True,
        "isolation_proof": _isolation_proof(workspace, receipt),
        "pair_id": f"{run_id}:{task_id}",
        "thread_id": session.vendor_session_id,
        "cwd": str(workspace),
        "prompt_sha256": prompt_sha256,
        "seed_manifest_sha256": seed_manifest_sha256,
        "final_workspace_sha256": final_workspace_sha256,
        "worker_config_sha256": boundary.worker_config_sha256(
            {"harness": "cursor", "model": worker, "cursor_version": cursor_version}
        ),
        "worker_model": worker,
        "harness_identity_sha256": runner.json_sha256(
            {
                "hooks_sha256": hooks_sha256,
                "cursor_version": cursor_version,
            }
        ),
        "transport_kind": "cursor_hooks",
        "transport_evidence": {
            "hooks_path": str(hooks),
            "process": "Cursor.exe" if running else None,
            "conversation_id": conversation_id,
            "cursor_version": cursor_version,
            "hooks_sha256": hooks_sha256,
            **(
                {"same_session_continuation": continuation}
                if continuation is not None
                else {}
            ),
        },
        "snapshot": str(snapshot) if snapshot else None,
        "workspace_files": sorted(p.name for p in workspace.iterdir() if p.is_file()),
        "human_interventions": len(human_intervention_log or []),
        "human_intervention_log": human_intervention_log or [],
        "human_intervention_requests": int(seed.get("human_prompts_for_pytest") or 0),
        "agent_messages": adapter.isolated_agent_messages,
        "pex": pex_meta,
        "pex_config_sha256": pex_config_sha256,
        "reasons": result["reasons"],
        "ts": datetime.now(UTC).isoformat(),
    }
    path = runner.append_immutable(run_id, record)
    result.update(record)
    result["written"] = str(path)
    return result


async def run_live(
    arm: str,
    task_id: str,
    run_id: str,
    *,
    transport: Any = None,
    turn_timeout: float = 600,
    workspace_root: Path | None = None,
    worker_model: str | None = None,
    stop_payload: dict[str, Any] | None = None,
    bridge_url: str | None = None,
    wait_cursor_stop: bool = False,
) -> dict[str, Any]:
    """Isolated live run. Cursor never opens a second window. Codex only thread/start."""
    if arm in {"cursor", "cursor_pex"}:
        return await run_live_this_cursor(
            arm,
            task_id,
            run_id,
            stop_payload=stop_payload,
            turn_timeout=turn_timeout,
            workspace_root=workspace_root,
            worker_model=worker_model,
            bridge_url=bridge_url,
            wait_cursor_stop=wait_cursor_stop,
        )
    if arm not in {"codex", "codex_pex"}:
        raise RuntimeError(f"unknown presentation arm {arm}")
    from pex_bridge.adapters.codex import CodexAdapter, CodexStdioTransport
    from pex_bridge.adapters.codex_bin import resolve_codex_bin

    owned_transport = False
    if transport is None:
        binary = resolve_codex_bin()
        if not binary:
            raise RuntimeError("codex CLI not found; cannot run a live Codex arm")
        transport = CodexStdioTransport(binary)
        owned_transport = True
    if isinstance(transport, CodexStdioTransport) and not worker_model:
        raise RuntimeError("live Codex arms require an explicit --worker-model for parity")
    presentation_candidate = isinstance(transport, CodexStdioTransport)
    task_budget = float(runner.protocol_config()["budget"]["task_wall_seconds"])
    if presentation_candidate:
        preflight = _execution_preflight_blockers()
        if preflight:
            raise RuntimeError(
                "benchmark execution preflight is NO-GO: " + "; ".join(preflight)
            )
        runner.assert_next_scheduled(run_id, task_id, arm)
        if float(turn_timeout) != task_budget:
            raise RuntimeError(
                "live presentation turn timeout must equal the predeclared task budget"
            )
    adapter = CodexAdapter(transport)
    abort_started_at: str | None = None
    try:
        workspace, seed, receipt = prepare_isolated_workspace(
            run_id, arm, task_id, workspace_root
        )
        seed_manifest_sha256 = str(receipt["seed_manifest_sha256"])
        prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
        boundary.assert_public_prompt(task_id, prompt)
        prompt_sha256 = boundary.sha256_text(prompt)
        abort_started_at = datetime.now(UTC).isoformat()
        task_started_perf = time.perf_counter()
        worker_started_perf = task_started_perf
        session = await adapter.start_isolated_thread(str(workspace), name="isolated-job")
        started = await adapter.start_turn(
            session,
            prompt,
            extra_params={"model": worker_model} if worker_model else None,
        )
        turn_id = str((started.get("turn") or {}).get("id") or "")
        if not turn_id:
            raise RuntimeError("turn/start returned no turn id")
        sent = adapter.last_turn_params or {}
        worker_config_sha256 = boundary.worker_config_sha256(sent)
        if isinstance(sent.get("additionalContext"), dict) and sent["additionalContext"].get(
            "pex_handoff"
        ):
            raise RuntimeError(
                "refusing leaked additionalContext.pex_handoff on a presentation arm"
            )
        turn = await adapter.wait_for_turn_completion(
            session,
            turn_id,
            timeout=turn_timeout,
        )
        if str(turn.get("status") or "").casefold() != "completed" or turn.get("error"):
            raise RuntimeError("worker turn did not reach a clean natural completion")
        worker_wall_seconds = time.perf_counter() - worker_started_perf
        pex_meta: dict[str, Any] | None = None
        pex_wall_seconds = 0.0
        if arm == "codex_pex":
            from pex_attach import supervise_isolated_codex

            remaining = task_budget - worker_wall_seconds
            if remaining <= 0:
                raise TimeoutError("worker exhausted the shared worker-plus-PEX task budget")
            store_path = (
                runner.RESULTS
                / "_scratch"
                / "_private_control"
                / run_id
                / arm
                / task_id
                / "pex.sqlite"
            )
            if _path_has_link_component(store_path, runner.RESULTS):
                raise RuntimeError("refusing a linked PEX private-control path")
            pex_started_perf = time.perf_counter()
            pex_meta = await supervise_isolated_codex(
                adapter,
                session,
                workspace,
                prompt,
                store_path=store_path,
                max_followups=int(
                    runner.protocol_config()["budget"]["max_pex_followups"]
                ),
                turn_timeout=remaining,
                decision_timeout=float(
                    runner.protocol_config()["budget"]["max_supervisor_decision_seconds"]
                ),
                public_test_sha256=str(
                    (seed.get("protected_sha256") or {}).get("test_public.py") or ""
                )
                or None,
            )
            supervised_elapsed = time.perf_counter() - pex_started_perf
            worker_followup_wall = float(pex_meta.get("worker_followup_wall_seconds") or 0.0)
            pex_wall_seconds = float(pex_meta.get("supervisor_wall_seconds") or 0.0)
            if (
                not all(
                    math.isfinite(value) and value >= 0
                    for value in (worker_followup_wall, pex_wall_seconds)
                )
                or abs(worker_followup_wall + pex_wall_seconds - supervised_elapsed) > 0.25
            ):
                raise RuntimeError("PEX supervision timing partition is invalid")
            worker_wall_seconds += worker_followup_wall
            if not pex_meta.get("supervisor_process_isolated"):
                raise RuntimeError(
                    "refusing treatment result without an isolated supervisor process"
                )
            for message in pex_meta.get("outgoing_messages") or []:
                boundary.assert_public_intervention(str(message))
        if evaluator.stressor_type(task_id) == "permission_interruption":
            joined = " ".join(adapter.isolated_agent_messages).lower()
            if any(
                token in joined for token in ("should i run", "can i run pytest", "run pytest?")
            ):
                seed["human_prompts_for_pytest"] = 1
        execution_wall_seconds = worker_wall_seconds + pex_wall_seconds
        if presentation_candidate and execution_wall_seconds > task_budget:
            raise TimeoutError("worker plus PEX exceeded the predeclared task budget")
        evaluation_started_perf = time.perf_counter()
        result = evaluator.evaluate(task_id, workspace, seed)
        final_workspace_sha256 = boundary.workspace_manifest_sha256(workspace)
        snapshot = _snapshot_workspace(run_id, arm, task_id, workspace)
        if snapshot is None:
            raise RuntimeError(
                "refusing result because the immutable workspace snapshot was not written"
            )
        evaluation_wall_seconds = time.perf_counter() - evaluation_started_perf
        ended_at = datetime.now(UTC).isoformat()
        total_wall_seconds = time.perf_counter() - task_started_perf
        process = getattr(transport, "_proc", None)
        verified_live = (
            isinstance(transport, CodexStdioTransport)
            and process is not None
            and process.returncode is None
        )
        transport_kind = "codex_stdio" if verified_live else "test_double"
        transport_identity = _bounded_json(
            {
                "command": getattr(transport, "command", None),
                "server_info": getattr(transport, "init_result", None),
            },
            label="Codex transport identity",
        )
        command = transport_identity.get("command")
        server_info = transport_identity.get("server_info")
        if presentation_candidate and (
            not isinstance(command, list)
            or not 1 <= len(command) <= 64
            or any(
                not isinstance(argument, str)
                or not argument
                or len(argument) > 4_096
                or any(ord(character) < 32 for character in argument)
                for argument in command
            )
            or not isinstance(server_info, dict)
        ):
            raise RuntimeError("Codex transport identity is not bounded protocol evidence")
        harness_identity_sha256 = runner.json_sha256(transport_identity)
        pex_config_sha256 = _pex_config_fingerprint(pex_meta)
        sandbox_settings = sent.get("sandboxPolicy")
        if isinstance(sandbox_settings, dict):
            sandbox_settings = dict(sandbox_settings)
            if "writableRoots" in sandbox_settings:
                sandbox_settings["writableRoots"] = ["<workspace>"]
        model_settings = {
            "model": sent.get("model"),
            "reasoning_effort": sent.get("reasoningEffort")
            or sent.get("reasoning_effort"),
            "approval_policy": sent.get("approvalPolicy"),
            "sandbox_policy": sandbox_settings,
        }
        recorded_item_types = _bounded_texts(
            list(adapter.isolated_item_types), label="Codex item types"
        )
        recorded_agent_messages = _bounded_texts(
            list(adapter.isolated_agent_messages), label="Codex agent messages"
        )
        recorded_approvals = _bounded_json(
            adapter.isolated_approval_decisions,
            label="Codex approval decisions",
        )
        captured_events = _bounded_json(
            {
                "approval_decisions": recorded_approvals,
                "item_types": recorded_item_types,
                "agent_messages": recorded_agent_messages,
            },
            label="Codex captured event subset",
        )
        raw_log_path, raw_log_sha256 = _try_write_codex_raw_log(
            run_id=run_id,
            arm=arm,
            task=task_id,
            thread_id=session.vendor_session_id,
            turn_id=str(turn_id or ""),
            started_at=abort_started_at,
            ended_at=ended_at,
            harness_identity_sha256=harness_identity_sha256,
            transport_kind=transport_kind,
            followups=int((pex_meta or {}).get("followups") or 0),
            raw_capture=getattr(transport, "raw_capture", None),
        )
        runtime_fields = _runtime_record_fields(
            arm=arm,
            task_id=task_id,
            seed_manifest_sha256=seed_manifest_sha256,
            started_at=abort_started_at,
            ended_at=ended_at,
            worker_wall_seconds=worker_wall_seconds,
            pex_wall_seconds=pex_wall_seconds,
            evaluation_wall_seconds=evaluation_wall_seconds,
            total_wall_seconds=total_wall_seconds,
            harness_version=_codex_harness_version(getattr(transport, "init_result", None)),
            model_settings=model_settings,
            model_version_evidence={
                "requested_model_id": worker_model,
                "provider_revision": None,
                "provider_revision_available": False,
            },
            pex_meta=pex_meta,
            pex_config_sha256=pex_config_sha256,
            item_types=recorded_item_types,
            captured_events=captured_events,
            raw_log_sha256=raw_log_sha256,
        )
        record = {
            **runtime_fields,
            "raw_log_path": raw_log_path,
            "arm": arm,
            "task": task_id,
            "success": bool(result["success"]),
            "live": verified_live,
            "not_a_presentation_arm": not verified_live,
            "isolated": True,
            "isolation_proof": _isolation_proof(workspace, receipt),
            "pair_id": f"{run_id}:{task_id}",
            "thread_id": session.vendor_session_id,
            "turn_id": turn_id,
            "turn_status": turn.get("status"),
            "turn_error": turn.get("error"),
            "cwd": session.cwd,
            "prompt_sha256": prompt_sha256,
            "seed_manifest_sha256": seed_manifest_sha256,
            "final_workspace_sha256": final_workspace_sha256,
            "worker_config_sha256": worker_config_sha256,
            "worker_model": worker_model,
            "harness_identity_sha256": harness_identity_sha256,
            "transport_kind": transport_kind,
            "transport_evidence": {
                "command": command,
                "pid": getattr(process, "pid", None),
                "server_info": server_info,
            },
            "snapshot": str(snapshot) if snapshot else None,
            "workspace_files": sorted(p.name for p in workspace.iterdir() if p.is_file()),
            "human_interventions": 0,
            "human_intervention_log": [],
            "human_intervention_requests": int(seed.get("human_prompts_for_pytest") or 0),
            "approval_decisions": recorded_approvals,
            "item_types": recorded_item_types,
            "agent_messages": recorded_agent_messages,
            "pex": pex_meta,
            "pex_config_sha256": pex_config_sha256,
            "reasons": result["reasons"],
            "ts": datetime.now(UTC).isoformat(),
        }
        path = runner.append_immutable(run_id, record)
        result.update(record)
        result["written"] = str(path)
        return result
    except Exception as exc:
        if presentation_candidate and abort_started_at is not None:
            message = str(exc).lower()
            if isinstance(exc, TimeoutError):
                reason = "budget_exhaustion"
            elif any(
                marker in message
                for marker in ("refusing", "mismatch", "provenance", "fingerprint")
            ):
                reason = "provenance_failure"
            else:
                reason = "harness_disconnect"
            try:
                runner.append_abort(
                    run_id,
                    task=task_id,
                    arm=arm,
                    abort_reason=reason,
                    started_at=abort_started_at,
                    ended_at=datetime.now(UTC).isoformat(),
                    detail=type(exc).__name__,
                )
            except (OSError, ValueError) as abort_exc:
                exc.add_note(f"failed to append immutable abort record: {abort_exc}")
        raise
    finally:
        if owned_transport:
            await transport.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="PexBench four-arm driver")
    parser.add_argument(
        "command", choices=("readiness", "plan", "run", "freeze", "evaluate", "prepare")
    )
    parser.add_argument("--arm", default="synthetic_pex")
    parser.add_argument("--task", default="pexbench_001_premature_stop")
    parser.add_argument("--run-id", default="synthetic_smoke")
    parser.add_argument("--workspace", default=None)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--turn-timeout", type=float, default=600)
    parser.add_argument("--worker-model", default=None)
    parser.add_argument("--pex-bridge-url", default=None)
    parser.add_argument("--wait-cursor-stop", action="store_true")
    args = parser.parse_args()
    if args.command == "readiness":
        print(json.dumps(readiness(), indent=2))
        return
    if args.command == "plan":
        print(
            json.dumps(
                {
                    "manifest_frozen": bool(runner.load_manifest().get("frozen")),
                    "protocol_sha256": runner.protocol_sha256(),
                    "schedule_sha256": runner.experiment_plan_sha256(),
                    "execution_preflight_blockers": _execution_preflight_blockers(),
                    "report_readiness_blockers": _report_readiness_blockers(),
                    "schedule": runner.experiment_plan(),
                },
                indent=2,
            )
        )
        return
    if args.command == "freeze":
        selected_run = args.run_id if args.run_id != "synthetic_smoke" else None
        result = try_freeze(selected_run)
        print(json.dumps(result, indent=2))
        raise SystemExit(0 if result.get("frozen") else 2)
    if args.command == "evaluate":
        if not args.workspace:
            raise SystemExit("--workspace is required for evaluate")
        print(json.dumps(evaluator.evaluate(args.task, Path(args.workspace)), indent=2))
        return
    if args.command == "prepare":
        if args.arm not in {"cursor", "cursor_pex"}:
            raise SystemExit(
                "prepare currently supports this-desktop Cursor arms only"
            )
        if args.arm == "cursor_pex":
            note = (
                "Work only in this folder in THIS Cursor.exe. Never spawn another window. "
                "PEX must return a follow-up on the first stop; wait for the later stop "
                "in the same conversation, then run --allow-live --wait-cursor-stop."
            )
        else:
            note = (
                "Work only in this folder in THIS Cursor.exe. "
                "Never spawn another window. After stop: "
                "run --allow-live --wait-cursor-stop with the same run id"
            )
        preflight = _execution_preflight_blockers()
        if preflight:
            raise SystemExit(
                "benchmark execution preflight is NO-GO: " + "; ".join(preflight)
            )
        runner.assert_next_scheduled(args.run_id, args.task, args.arm)
        workspace, _, receipt = prepare_isolated_workspace(
            args.run_id,
            args.arm,
            args.task,
            Path(args.workspace) if args.workspace else None,
        )
        prompt = (workspace / "TASK.md").read_text(encoding="utf-8")
        boundary.assert_public_prompt(args.task, prompt)
        print(
            json.dumps(
                {
                    "arm": args.arm,
                    "task": args.task,
                    "run_id": args.run_id,
                    "workspace": str(workspace),
                    "seed_receipt": str(_seed_receipt_path(workspace)),
                    "seed_manifest_sha256": receipt["seed_manifest_sha256"],
                    "hooks": str(cursor_hooks_path()) if cursor_hooks_path().is_file() else None,
                    "stop_drop": str(cursor_stop_drop_dir()),
                    "note": note,
                },
                indent=2,
            )
        )
        return
    if args.arm == "synthetic_pex":
        print(json.dumps(run_synthetic(args.task, args.run_id), indent=2))
        return
    if args.arm in PRESENTATION_ARMS:
        if not args.allow_live:
            raise SystemExit("presentation arms require --allow-live")
        preflight = _execution_preflight_blockers()
        if preflight:
            raise SystemExit(
                "benchmark execution preflight is NO-GO: " + "; ".join(preflight)
            )
        print(
            json.dumps(
                asyncio.run(
                    run_live(
                        args.arm,
                        args.task,
                        args.run_id,
                        turn_timeout=args.turn_timeout,
                        workspace_root=Path(args.workspace) if args.workspace else None,
                        worker_model=args.worker_model,
                        stop_payload=None,
                        bridge_url=args.pex_bridge_url,
                        wait_cursor_stop=args.wait_cursor_stop,
                    )
                ),
                indent=2,
                default=str,
            )
        )
        return
    raise SystemExit(f"unknown arm {args.arm}")


if __name__ == "__main__":
    main()
