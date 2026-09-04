"""Partial, controller-owned capture of sanitized Cursor hook receipts.

This journal records locally observed hook evidence.  It is deliberately not a
claim of vendor acceptance, authenticated authorship, or complete vendor logs.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CAPTURE_SCHEMA = "pex.cursor-observed-capture.v1"
RECEIPT_SCHEMA = "pex.cursor-hook-receipt.v1"
MAX_RECEIPT_BYTES = 1_048_576
MAX_RECEIPTS = 10_000
MAX_JOURNAL_BYTES = 64 * 1024 * 1024

_BINDING_FIELDS = {
    "run_id",
    "arm",
    "task",
    "workspace",
    "capture_nonce",
    "prompt_sha256",
}
_IDENTITY_FIELDS = ("conversation_id", "session_id", "composer_id")
_PROMPT_TEXT_KEYS = {
    "content",
    "message",
    "prompt",
    "prompt_text",
    "submitted_prompt",
    "text",
    "user_message",
    "user_prompt",
}


def _is_lower_hex(value: object, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and all(character in "0123456789abcdef" for character in value)
    )


def _bounded_text(value: object, *, limit: int = 256) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= limit
        and not any(ord(character) < 32 for character in value)
    )


def _only_string_keys(value: object) -> bool:
    pending = [value]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if id(item) in seen:
                continue
            seen.add(id(item))
            if any(not isinstance(key, str) for key in item):
                return False
            pending.extend(item.values())
        elif isinstance(item, list):
            if id(item) in seen:
                continue
            seen.add(id(item))
            pending.extend(item)
    return True


def _canonical_json(value: object) -> bytes:
    try:
        if not _only_string_keys(value):
            raise ValueError("JSON objects must use string keys")
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("value is not finite bounded JSON") from exc


def _utc_iso_from_ns(value: int) -> str:
    seconds, nanoseconds = divmod(value, 1_000_000_000)
    return datetime.fromtimestamp(seconds, UTC).replace(
        microsecond=nanoseconds // 1_000
    ).isoformat()


def _identity(receipt: dict[str, Any]) -> tuple[tuple[str, str], ...] | None:
    result: list[tuple[str, str]] = []
    for field in _IDENTITY_FIELDS:
        if field not in receipt:
            continue
        value = receipt[field]
        if not _bounded_text(value):
            return None
        result.append((field, value))
    return tuple(result) or None


def _contains_prompt_text(value: object) -> bool:
    pending = [value]
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if id(item) in seen:
                continue
            seen.add(id(item))
            if any(key.casefold() in _PROMPT_TEXT_KEYS for key in item):
                return True
            pending.extend(item.values())
        elif isinstance(item, list):
            if id(item) in seen:
                continue
            seen.add(id(item))
            pending.extend(item)
    return False


def _is_link_like(path: Path) -> bool:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise ValueError(f"cannot inspect Cursor capture path component: {exc}") from exc
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _reject_link_components(path: Path) -> None:
    current = path
    while True:
        if _is_link_like(current):
            raise ValueError("Cursor capture path cannot contain links or reparse points")
        parent = current.parent
        if parent == current:
            return
        current = parent


class CursorCapture:
    """Exclusive fsynced JSONL journal for partial Cursor hook evidence.

    ``record`` returns ``True`` only when it appends a new valid receipt.  An
    identical duplicate is a harmless ``False``; a conflicting duplicate
    invalidates timing evidence.  ``finish`` is idempotent.
    """

    def __init__(self, path: Path, *, binding: dict[str, Any]) -> None:
        raw_path = Path(os.path.abspath(os.fspath(path)))
        _reject_link_components(raw_path)
        self.binding = self._validate_binding(binding)
        self._descriptor: int | None = None
        self._bytes_written = 0
        self._journal_digest = hashlib.sha256()
        self._opened_identity: tuple[int, int] | None = None
        self._sequence = 0
        self._receipts: list[dict[str, Any]] = []
        self._receipt_bytes: dict[str, bytes] = {}
        self._reasons: list[str] = []
        self._invalidated = False
        self._finished: dict[str, Any] | None = None

        raw_path.parent.mkdir(parents=True, exist_ok=True)
        _reject_link_components(raw_path)
        self.path = raw_path.resolve(strict=False)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_APPEND
        flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        self._descriptor = os.open(self.path, flags, 0o600)
        try:
            _reject_link_components(raw_path)
            opened = os.fstat(self._descriptor)
            if not stat.S_ISREG(opened.st_mode):
                raise OSError("Cursor capture path is not a regular file")
            self._opened_identity = (opened.st_dev, opened.st_ino)
            wall_ns, monotonic_ns = self._controller_clock()
            self._append(
                {
                    "schema": CAPTURE_SCHEMA,
                    "sequence": self._sequence,
                    "record_type": "capture_header",
                    "source": "benchmark_controller",
                    "binding": self.binding,
                    "captured_at_ns": wall_ns,
                    "captured_at": _utc_iso_from_ns(wall_ns),
                    "captured_monotonic_ns": monotonic_ns,
                    "coverage": "partial",
                    "complete": False,
                }
            )
        except Exception:
            self._close_descriptor()
            raise

    @staticmethod
    def _validate_binding(binding: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(binding, dict) or set(binding) != _BINDING_FIELDS:
            raise ValueError("Cursor capture binding must contain exactly the six required fields")
        for field in ("run_id", "arm", "task"):
            if not _bounded_text(binding[field]):
                raise ValueError(f"Cursor capture binding {field} is invalid")
        if not _is_lower_hex(binding["capture_nonce"], 32):
            raise ValueError("Cursor capture nonce must be 32 lowercase hexadecimal characters")
        if not _is_lower_hex(binding["prompt_sha256"], 64):
            raise ValueError("Cursor capture prompt hash must be lowercase SHA-256")
        workspace = binding["workspace"]
        if not isinstance(workspace, str) or not Path(workspace).is_absolute():
            raise ValueError("Cursor capture workspace must be an absolute resolved path")
        resolved = str(Path(workspace).resolve(strict=False))
        if workspace != resolved:
            raise ValueError("Cursor capture workspace must already be resolved")
        return json.loads(_canonical_json(binding).decode("utf-8"))

    @staticmethod
    def _controller_clock() -> tuple[int, int]:
        return time.time_ns(), time.perf_counter_ns()

    def _reason(self, reason: str) -> None:
        cleaned = str(reason or "capture invalidated").strip()[:512]
        if cleaned and cleaned not in self._reasons and len(self._reasons) < 100:
            self._reasons.append(cleaned)

    def invalidate(self, reason: str) -> None:
        """Make derived timing unavailable while preserving the partial journal."""
        if self._finished is not None:
            return
        self._invalidated = True
        self._reason(reason)

    def _write_all(self, encoded: bytes) -> None:
        if self._descriptor is None:
            raise OSError("Cursor capture is closed")
        view = memoryview(encoded)
        while view:
            written = os.write(self._descriptor, view)
            if written <= 0:
                raise OSError("Cursor capture write made no progress")
            view = view[written:]
        os.fsync(self._descriptor)
        self._bytes_written += len(encoded)
        self._journal_digest.update(encoded)

    def _append(self, record: dict[str, Any], *, reserve_footer: bool = False) -> None:
        encoded = _canonical_json(record) + b"\n"
        limit = MAX_JOURNAL_BYTES - (MAX_RECEIPT_BYTES if reserve_footer else 0)
        if self._bytes_written + len(encoded) > limit:
            raise OSError("Cursor capture exceeds the aggregate journal bound")
        self._write_all(encoded)
        self._sequence += 1

    def _receipt_workspace_matches(self, receipt: dict[str, Any]) -> bool:
        expected = Path(self.binding["workspace"])
        candidates: list[str] = []
        for field in ("cwd", "workspace"):
            if field in receipt:
                value = receipt[field]
                if not isinstance(value, str):
                    return False
                candidates.append(value)
        if "workspace_roots" in receipt:
            roots = receipt["workspace_roots"]
            if not isinstance(roots, list) or not 1 <= len(roots) <= 64:
                return False
            if any(not isinstance(root, str) for root in roots):
                return False
            candidates.extend(roots)
        if not candidates:
            return False
        try:
            return all(
                Path(candidate).is_absolute()
                and Path(candidate).resolve(strict=False) == expected
                for candidate in candidates
            )
        except (OSError, ValueError):
            return False

    def _validated_receipt(self, receipt: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        if type(receipt) is not dict:
            raise ValueError("receipt is not an object")
        capture_binding = receipt.get("capture_binding")
        if (
            type(capture_binding) is not dict
            or set(capture_binding) != _BINDING_FIELDS
            or any(capture_binding.get(key) != value for key, value in self.binding.items())
        ):
            raise ValueError("receipt has a foreign capture binding")
        receipt_id = receipt.get("stop_id")
        if not _is_lower_hex(receipt_id, 32):
            raise ValueError("receipt UUID is invalid")
        if receipt.get("receipt_schema") != RECEIPT_SCHEMA:
            raise ValueError("receipt schema is invalid")
        for field in ("captured_at_ns", "captured_monotonic_ns"):
            value = receipt.get(field)
            if type(value) is not int or not 0 < value < 2**63:
                raise ValueError(f"receipt {field} is not a strict bounded integer")
        if _identity(receipt) is None:
            raise ValueError("receipt identity namespace set is invalid")
        if not self._receipt_workspace_matches(receipt):
            raise ValueError("receipt workspace does not match the resolved capture workspace")
        if not _bounded_text(receipt.get("kind"), limit=128):
            raise ValueError("receipt kind is invalid")
        if not _bounded_text(receipt.get("hook_event_name"), limit=128):
            raise ValueError("receipt hook event name is invalid")
        provided_hash = receipt.get("receipt_sha256")
        if not _is_lower_hex(provided_hash, 64):
            raise ValueError("receipt hash is invalid")
        without_hash = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
        if hashlib.sha256(_canonical_json(without_hash)).hexdigest() != provided_hash:
            raise ValueError("receipt canonical hash does not match its content")
        if receipt.get("kind") == "prompt_release" and _contains_prompt_text(receipt):
            raise ValueError("prompt-release receipt contains prompt text")
        encoded = _canonical_json(receipt)
        if len(encoded) > MAX_RECEIPT_BYTES:
            raise ValueError("receipt exceeds the one-megabyte bound")
        snapshot = json.loads(encoded.decode("utf-8"))
        return snapshot, encoded

    def record(self, receipt: dict[str, Any]) -> bool:
        """Validate and append one sanitized receipt; never trust benchmark fields."""
        if self._finished is not None or self._descriptor is None:
            return False
        receipt_id = receipt.get("stop_id") if type(receipt) is dict else None
        if isinstance(receipt_id, str) and receipt_id in self._receipt_bytes:
            try:
                snapshot, encoded = self._validated_receipt(receipt)
            except Exception:
                self.invalidate("conflicting duplicate Cursor receipt")
                return False
            if encoded == self._receipt_bytes[receipt_id]:
                return False
            del snapshot
            self.invalidate("conflicting duplicate Cursor receipt")
            return False
        try:
            snapshot, encoded = self._validated_receipt(receipt)
        except Exception as exc:
            supplied_binding = receipt.get("capture_binding") if type(receipt) is dict else None
            foreign = type(supplied_binding) is dict and (
                set(supplied_binding) != _BINDING_FIELDS
                or any(supplied_binding.get(key) != value for key, value in self.binding.items())
            )
            self._reason(str(exc))
            if not foreign:
                self._invalidated = True
            return False
        if len(self._receipts) >= MAX_RECEIPTS:
            self.invalidate("Cursor receipt count exceeds the capture bound")
            return False
        record = {
            "schema": CAPTURE_SCHEMA,
            "sequence": self._sequence,
            "record_type": "hook_receipt",
            "source": "cursor_hook",
            "binding": self.binding,
            "receipt": snapshot,
        }
        try:
            self._append(record, reserve_footer=True)
        except OSError as exc:
            self.invalidate(str(exc))
            return False
        self._receipts.append(snapshot)
        self._receipt_bytes[snapshot["stop_id"]] = encoded
        return True

    def _timing(self, terminal_stop_id: str | None) -> tuple[dict[str, Any], list[str]]:
        unavailable = {
            "task_started_at": None,
            "task_stopped_at": None,
            "task_execution_wall_seconds": None,
        }
        reasons: list[str] = []
        if self._invalidated:
            reasons.append("capture evidence was invalidated")
            return unavailable, reasons
        if not self._receipts:
            reasons.append("capture contains no valid hook receipts")
            return unavailable, reasons
        clocks = [receipt["captured_monotonic_ns"] for receipt in self._receipts]
        if len(clocks) != len(set(clocks)):
            reasons.append("receipt monotonic clocks do not establish a strict order")
            return unavailable, reasons
        ordered = sorted(
            self._receipts, key=lambda receipt: receipt["captured_monotonic_ns"]
        )
        if any(
            later["captured_at_ns"] < earlier["captured_at_ns"]
            for earlier, later in zip(ordered, ordered[1:], strict=False)
        ):
            reasons.append("receipt wall clocks reverse chronological order")
            return unavailable, reasons
        identities = {_identity(receipt) for receipt in ordered}
        if None in identities or len(identities) != 1:
            reasons.append("receipt identity changed during the capture")
            return unavailable, reasons
        prompt_releases = sorted(
            (receipt for receipt in ordered if receipt.get("kind") == "prompt_release"),
            key=lambda receipt: receipt["captured_monotonic_ns"],
        )
        if not prompt_releases:
            reasons.append("capture has no prompt-release receipt")
            return unavailable, reasons
        start = prompt_releases[0]
        start_index = ordered.index(start)
        if any(
            receipt.get("kind") != "hook_activity"
            or receipt.get("hook_event_name") != "sessionStart"
            for receipt in ordered[:start_index]
        ):
            reasons.append("worker activity precedes the benchmark prompt release")
            return unavailable, reasons
        if (
            start.get("hook_event_name") != "beforeSubmitPrompt"
            or start.get("submission_evidence") != "hook_stdout_flushed"
            or start.get("submitted_prompt_sha256") != self.binding["prompt_sha256"]
        ):
            reasons.append("earliest prompt release does not bind the benchmark task")
            return unavailable, reasons
        if not _is_lower_hex(terminal_stop_id, 32):
            reasons.append("terminal stop receipt was not supplied")
            return unavailable, reasons
        terminal = next(
            (receipt for receipt in self._receipts if receipt["stop_id"] == terminal_stop_id),
            None,
        )
        if (
            terminal is None
            or terminal.get("kind") != "stop"
            or terminal.get("hook_event_name") not in {"stop", "Stop"}
        ):
            reasons.append("terminal stop receipt is missing or invalid")
            return unavailable, reasons
        if terminal["captured_monotonic_ns"] != max(clocks):
            reasons.append("terminal stop is not the last relevant receipt")
            return unavailable, reasons
        if _identity(start) != _identity(terminal):
            reasons.append("terminal stop identity does not match task start")
            return unavailable, reasons
        start_clock = start["captured_monotonic_ns"]
        stop_clock = terminal["captured_monotonic_ns"]
        if stop_clock <= start_clock:
            reasons.append("terminal stop does not follow task start")
            return unavailable, reasons
        if terminal["captured_at_ns"] < start["captured_at_ns"]:
            reasons.append("terminal wall clock precedes task start")
            return unavailable, reasons
        elapsed = (stop_clock - start_clock) / 1_000_000_000
        if elapsed > 86_400:
            reasons.append("task execution exceeds the one-day timing bound")
            return unavailable, reasons
        return (
            {
                "task_started_at": _utc_iso_from_ns(start["captured_at_ns"]),
                "task_stopped_at": _utc_iso_from_ns(terminal["captured_at_ns"]),
                "task_execution_wall_seconds": elapsed,
            },
            reasons,
        )

    def _close_descriptor(self) -> None:
        if self._descriptor is None:
            return
        descriptor, self._descriptor = self._descriptor, None
        os.close(descriptor)

    def _verified_journal_sha256(self) -> str | None:
        """Hash the bounded open journal and bind it to the created path identity."""
        if self._descriptor is None or self._opened_identity is None:
            self.invalidate("capture hash unavailable: journal is closed")
            return None
        try:
            opened_before = os.fstat(self._descriptor)
            path_metadata = os.stat(self.path, follow_symlinks=False)
            if (
                not stat.S_ISREG(opened_before.st_mode)
                or (opened_before.st_dev, opened_before.st_ino) != self._opened_identity
                or (path_metadata.st_dev, path_metadata.st_ino) != self._opened_identity
                or opened_before.st_size != self._bytes_written
                or not 0 < opened_before.st_size <= MAX_JOURNAL_BYTES
            ):
                raise OSError("journal identity or byte count changed")
            digest = hashlib.sha256()
            os.lseek(self._descriptor, 0, os.SEEK_SET)
            read_bytes = 0
            while read_bytes < opened_before.st_size:
                chunk = os.read(
                    self._descriptor,
                    min(1024 * 1024, opened_before.st_size - read_bytes),
                )
                if not chunk:
                    raise OSError("journal ended before its recorded byte count")
                read_bytes += len(chunk)
                digest.update(chunk)
            opened_after = os.fstat(self._descriptor)
            path_after = os.stat(self.path, follow_symlinks=False)
            result = digest.hexdigest()
            if (
                read_bytes != self._bytes_written
                or opened_after.st_size != opened_before.st_size
                or (opened_after.st_dev, opened_after.st_ino) != self._opened_identity
                or (path_after.st_dev, path_after.st_ino) != self._opened_identity
                or result != self._journal_digest.hexdigest()
            ):
                raise OSError("journal changed during bounded hash verification")
            return result
        except (OSError, ValueError) as exc:
            self.invalidate(f"capture hash unavailable: {exc}")
            return None

    def finish(self, terminal_stop_id: str | None) -> dict[str, Any]:
        """Close the partial journal and return conservative derived evidence."""
        if self._finished is not None:
            return dict(self._finished)
        timing, timing_reasons = self._timing(terminal_stop_id)
        for reason in timing_reasons:
            self._reason(reason)
        wall_ns, monotonic_ns = self._controller_clock()
        footer = {
            "schema": CAPTURE_SCHEMA,
            "sequence": self._sequence,
            "record_type": "capture_footer",
            "source": "benchmark_controller",
            "binding": self.binding,
            "captured_at_ns": wall_ns,
            "captured_at": _utc_iso_from_ns(wall_ns),
            "captured_monotonic_ns": monotonic_ns,
            "coverage": "partial",
            "complete": False,
            "observed_receipt_count": len(self._receipts),
            "terminal_stop_id": terminal_stop_id,
            "reasons": list(self._reasons),
        }
        try:
            self._append(footer)
        except OSError as exc:
            self.invalidate(f"capture footer unavailable: {exc}")
            timing = {
                "task_started_at": None,
                "task_stopped_at": None,
                "task_execution_wall_seconds": None,
            }
        observed_hash = self._verified_journal_sha256()
        if observed_hash is None:
            timing = {
                "task_started_at": None,
                "task_stopped_at": None,
                "task_execution_wall_seconds": None,
            }
        try:
            self._close_descriptor()
        except OSError as exc:
            self.invalidate(f"capture close failed: {exc}")
            timing = {
                "task_started_at": None,
                "task_stopped_at": None,
                "task_execution_wall_seconds": None,
            }
        result = {
            "observed_capture_path": str(self.path),
            "observed_capture_sha256": observed_hash,
            "coverage": "partial",
            "raw_log_sha256": None,
            "human_action_coverage": "partial",
            "human_interventions": None,
            "human_interventions_observed": None,
            "terminal_stop_id": terminal_stop_id,
            "observed_receipt_count": len(self._receipts),
            "evidence_scope": "ordered_local_hook_receipts",
            "reasons": list(self._reasons),
            **timing,
        }
        self._finished = result
        return dict(result)
