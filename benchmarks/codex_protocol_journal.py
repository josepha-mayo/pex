"""Controller-owned exact stdio journal for Codex benchmark runs."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

MAX_PROTOCOL_PAYLOAD_BYTES = 1024 * 1024
MAX_JOURNAL_RECORD_BYTES = 2 * 1024 * 1024
MAX_JOURNAL_RECORDS = 10_000
MAX_JOURNAL_BYTES = 64 * 1024 * 1024


class CodexProtocolJournal:
    """Append exact protocol lines to one exclusive, bounded JSONL artifact."""

    def __init__(
        self,
        path: Path,
        *,
        run_id: str,
        arm: str,
        task: str,
        started_at: str,
    ) -> None:
        self.path = path.absolute()
        self._common = {
            "schema_version": 2,
            "run_id": run_id,
            "arm": arm,
            "task": task,
        }
        self._sequence = 0
        self._protocol_lines = 0
        self._direction_counts = {"stdin": 0, "stdout": 0}
        self._bytes_written = 0
        self._journal_digest = hashlib.sha256()
        self._closed = False
        self._complete = False
        self._failed = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        self._descriptor = os.open(self.path, flags, 0o600)
        self._initial_stat = os.fstat(self._descriptor)
        try:
            path_stat = os.stat(self.path, follow_symlinks=False)
            if (
                not stat.S_ISREG(self._initial_stat.st_mode)
                or (self._initial_stat.st_dev, self._initial_stat.st_ino)
                != (path_stat.st_dev, path_stat.st_ino)
            ):
                raise RuntimeError("Codex protocol journal path identity is invalid")
            self._write_record(
                {
                    "record_type": "capture_header",
                    "source": "benchmark_controller",
                    "event_kind": "capture_started",
                    "timestamp": started_at,
                    "capture_scope": "exact_codex_stdio_jsonl",
                    "payload_encoding": "base64",
                    "transport_kind": "codex_stdio",
                }
            )
        except Exception:
            self._close_descriptor()
            raise

    def _write_all(self, data: bytes) -> None:
        view = memoryview(data)
        while view:
            written = os.write(self._descriptor, view)
            if written <= 0:
                raise OSError("Codex protocol journal write made no progress")
            view = view[written:]

    def _write_record(self, fields: dict[str, object]) -> None:
        if self._closed or self._failed:
            raise RuntimeError("Codex protocol journal is not writable")
        if self._sequence >= MAX_JOURNAL_RECORDS:
            self._failed = True
            raise RuntimeError("Codex protocol journal exceeds the record-count bound")
        record = {**self._common, "sequence": self._sequence, **fields}
        try:
            encoded = (
                json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            self._failed = True
            raise RuntimeError("Codex protocol journal record is not canonical JSON") from exc
        if len(encoded) > MAX_JOURNAL_RECORD_BYTES:
            self._failed = True
            raise RuntimeError("Codex protocol journal record exceeds the size bound")
        if self._bytes_written + len(encoded) > MAX_JOURNAL_BYTES:
            self._failed = True
            raise RuntimeError("Codex protocol journal exceeds the total-size bound")
        try:
            self._write_all(encoded)
        except Exception:
            self._failed = True
            raise
        self._journal_digest.update(encoded)
        self._bytes_written += len(encoded)
        self._sequence += 1

    def observe(self, direction: Literal["stdin", "stdout"], payload: bytes) -> None:
        """Record one exact line synchronously in transport observation order."""
        if direction not in self._direction_counts:
            self._failed = True
            raise ValueError("Codex protocol direction is invalid")
        exact = bytes(payload)
        if not exact or len(exact) > MAX_PROTOCOL_PAYLOAD_BYTES or not exact.endswith(b"\n"):
            self._failed = True
            raise RuntimeError("Codex protocol payload violates the exact-line safety bound")
        self._write_record(
            {
                "record_type": "protocol_line",
                "source": "codex_app_server",
                "timestamp": datetime.now(UTC).isoformat(),
                "direction": direction,
                "payload_base64": base64.b64encode(exact).decode("ascii"),
                "payload_bytes": len(exact),
                "payload_sha256": hashlib.sha256(exact).hexdigest(),
            }
        )
        self._protocol_lines += 1
        self._direction_counts[direction] += 1

    def finish(
        self,
        *,
        ended_at: str,
        thread_id: str,
        initial_turn_id: str,
        expected_turn_count: int,
        harness_identity_sha256: str,
    ) -> tuple[str, str]:
        """Seal a complete capture and return its canonical path and digest."""
        if self._failed:
            raise RuntimeError("Codex protocol journal failed before completion")
        if (
            not thread_id
            or len(thread_id) > 256
            or not initial_turn_id
            or len(initial_turn_id) > 256
            or isinstance(expected_turn_count, bool)
            or not 1 <= expected_turn_count <= 100
            or len(harness_identity_sha256) != 64
            or any(character not in "0123456789abcdef" for character in harness_identity_sha256)
            or self._protocol_lines == 0
            or self._direction_counts["stdin"] == 0
            or self._direction_counts["stdout"] == 0
        ):
            self._failed = True
            raise RuntimeError("Codex protocol journal cannot seal incomplete identity or traffic")
        self._write_record(
            {
                "record_type": "capture_footer",
                "source": "benchmark_controller",
                "event_kind": "capture_completed",
                "timestamp": ended_at,
                "complete": True,
                "captured_protocol_line_count": self._protocol_lines,
                "stdin_line_count": self._direction_counts["stdin"],
                "stdout_line_count": self._direction_counts["stdout"],
                "thread_id": thread_id,
                "initial_turn_id": initial_turn_id,
                "expected_turn_count": expected_turn_count,
                "harness_identity_sha256": harness_identity_sha256,
                "transport_kind": "codex_stdio",
            }
        )
        os.fsync(self._descriptor)
        descriptor_stat = os.fstat(self._descriptor)
        path_stat = os.stat(self.path, follow_symlinks=False)
        if (
            not stat.S_ISREG(descriptor_stat.st_mode)
            or (descriptor_stat.st_dev, descriptor_stat.st_ino)
            != (path_stat.st_dev, path_stat.st_ino)
            or descriptor_stat.st_size != self._bytes_written
            or descriptor_stat.st_size > MAX_JOURNAL_BYTES
        ):
            self._failed = True
            raise RuntimeError("Codex protocol journal path identity changed during capture")
        digest = hashlib.sha256()
        os.lseek(self._descriptor, 0, os.SEEK_SET)
        read_bytes = 0
        while read_bytes < descriptor_stat.st_size:
            chunk = os.read(
                self._descriptor,
                min(1024 * 1024, descriptor_stat.st_size - read_bytes),
            )
            if not chunk:
                self._failed = True
                raise RuntimeError("Codex protocol journal ended before its byte count")
            read_bytes += len(chunk)
            digest.update(chunk)
        final_stat = os.fstat(self._descriptor)
        final_path_stat = os.stat(self.path, follow_symlinks=False)
        if (
            read_bytes != self._bytes_written
            or final_stat.st_size != descriptor_stat.st_size
            or (final_stat.st_dev, final_stat.st_ino)
            != (descriptor_stat.st_dev, descriptor_stat.st_ino)
            or (final_path_stat.st_dev, final_path_stat.st_ino)
            != (descriptor_stat.st_dev, descriptor_stat.st_ino)
            or digest.hexdigest() != self._journal_digest.hexdigest()
        ):
            self._failed = True
            raise RuntimeError("Codex protocol journal changed during hash verification")
        self._complete = True
        self._close_descriptor()
        return str(self.path), digest.hexdigest()

    def abort(self) -> None:
        """Durably retain an incomplete capture without claiming completeness."""
        if self._closed:
            return
        try:
            os.fsync(self._descriptor)
        finally:
            self._close_descriptor()

    def _close_descriptor(self) -> None:
        if not self._closed:
            os.close(self._descriptor)
            self._closed = True

    @property
    def complete(self) -> bool:
        return self._complete
