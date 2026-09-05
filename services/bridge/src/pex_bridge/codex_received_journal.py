"""Local-only committed receive bytes, never a live event/replay authority.

The journal contains potentially sensitive vendor data, including malformed
messages and server request IDs. It has no model, telemetry or HTTP export path.
Its directory must be the existing private PEX data directory. SQLite commits
use FULL synchronization; this is not protection against malicious same-user
file modification, disk failure or bytes never returned by the connector.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sqlite3
import stat
from datetime import UTC, datetime
from pathlib import Path

from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads

MAX_CHUNK_BYTES = 65_536
MAX_JOURNAL_BYTES = 1_073_741_824
MAX_JOURNAL_RECORDS = 1_000_000
MAX_JOURNAL_ATTEMPTS = 10_000
MAX_PROVENANCE_BYTES = 32_768
_APPLICATION_ID = 0x50455852  # PEXR; never adopt a foreign/ambiguous existing database.

_SCHEMA = """
CREATE TABLE IF NOT EXISTS receive_attempts (
    inspection_id TEXT PRIMARY KEY,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS received_chunks (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    inspection_id TEXT NOT NULL REFERENCES receive_attempts(inspection_id),
    endpoint_identity TEXT NOT NULL,
    connection_generation INTEGER NOT NULL CHECK(connection_generation > 0),
    received_at TEXT NOT NULL,
    payload BLOB NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS received_chunks_attempt
    ON received_chunks(inspection_id, sequence);
CREATE TABLE IF NOT EXISTS receive_usage (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    payload_bytes INTEGER NOT NULL,
    records INTEGER NOT NULL,
    attempts INTEGER NOT NULL
);
INSERT OR IGNORE INTO receive_usage VALUES (1, 0, 0, 0);
CREATE TRIGGER IF NOT EXISTS receive_attempt_no_update BEFORE UPDATE ON receive_attempts
    BEGIN SELECT RAISE(ABORT, 'receive provenance is append-only'); END;
CREATE TRIGGER IF NOT EXISTS receive_attempt_no_delete BEFORE DELETE ON receive_attempts
    BEGIN SELECT RAISE(ABORT, 'receive provenance is append-only'); END;
CREATE TRIGGER IF NOT EXISTS received_chunk_no_update BEFORE UPDATE ON received_chunks
    BEGIN SELECT RAISE(ABORT, 'received bytes are append-only'); END;
CREATE TRIGGER IF NOT EXISTS received_chunk_no_delete BEFORE DELETE ON received_chunks
    BEGIN SELECT RAISE(ABORT, 'received bytes are append-only'); END;
"""


class CodexReceivedJournalError(RuntimeError):
    """Receive durability failed; the current attachment must not control work."""


def _regular_identity(path: Path) -> tuple[int, int]:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or (
        getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    ):
        raise CodexReceivedJournalError("receive journal must be a regular local file")
    return info.st_dev, info.st_ino


class CodexReceivedJournal:
    """One immutable inspection attempt in the shared local receive database.

    Construct off the event loop. No attachment, input or delivery authority is
    inferred from the caller's requested target. Every append settles its one disk
    operation before propagating cancellation; cancellation is never a retry signal.
    """

    def __init__(self, path: Path, *, inspection_id: str, provenance: dict) -> None:
        if not isinstance(inspection_id, str) or not re.fullmatch(r"[a-f0-9]{32}", inspection_id):
            raise ValueError("invalid receive inspection id")
        encoded = strict_json_dumps(provenance, sort_keys=True, separators=(",", ":"))
        if not isinstance(provenance, dict) or len(encoded.encode("utf-8")) > MAX_PROVENANCE_BYTES:
            raise ValueError("invalid receive provenance")
        # Freeze caller-owned structures; no later confirmation can relabel them.
        if not isinstance(strict_json_loads(encoded), dict):
            raise ValueError("invalid receive provenance")
        self.path = Path(path).absolute()
        self.inspection_id = inspection_id
        self._healthy = True
        self._lock = asyncio.Lock()
        self._endpoint: str | None = None
        self._last_generation = 0
        self._provenance_json = encoded
        # Create only this file, not a guessed directory. Do not follow a link or
        # silently replace/recreate a damaged journal. Windows inherits data-dir ACLs.
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            created = False
        else:
            os.close(fd)
            created = True
        self._identity = _regular_identity(self.path)
        try:
            connection = self._connect(creating=created)
            try:
                with connection:
                    if created:
                        connection.execute("PRAGMA journal_mode=WAL")
                        connection.executescript(_SCHEMA)
                        connection.execute(f"PRAGMA application_id={_APPLICATION_ID}")
                        connection.execute("PRAGMA user_version=1")
                    elif (
                        connection.execute("PRAGMA application_id").fetchone()[0]
                        != _APPLICATION_ID
                        or connection.execute("PRAGMA user_version").fetchone()[0] != 1
                    ):
                        raise CodexReceivedJournalError(
                            "receive journal format is unavailable; existing bytes were preserved"
                        )
                    connection.execute("BEGIN IMMEDIATE")
                    usage = connection.execute(
                        "SELECT attempts FROM receive_usage WHERE singleton=1"
                    ).fetchone()
                    if usage is None or usage[0] >= MAX_JOURNAL_ATTEMPTS:
                        raise CodexReceivedJournalError("receive journal attempt capacity reached")
                    connection.execute(
                        "INSERT INTO receive_attempts VALUES (?, ?, ?)",
                        (inspection_id, encoded, datetime.now(UTC).isoformat()),
                    )
                    connection.execute(
                        "UPDATE receive_usage SET attempts=attempts+1 WHERE singleton=1"
                    )
            finally:
                connection.close()
        except (sqlite3.Error, OSError) as exc:
            raise CodexReceivedJournalError("receive journal initialization failed") from exc

    @property
    def healthy(self) -> bool:
        return self._healthy

    def _connect(self, *, creating: bool = False) -> sqlite3.Connection:
        if _regular_identity(self.path) != self._identity:
            raise CodexReceivedJournalError("receive journal identity changed")
        if not creating:
            # Even opening/closing SQLite in rw mode can checkpoint an existing
            # WAL. Reject unknown main-file headers before SQLite touches any
            # sidecar. An interrupted initialization with markers only in WAL is
            # ambiguous and needs explicit recovery, never automatic adoption.
            with self.path.open("rb") as source:
                header = source.read(100)
                info = os.fstat(source.fileno())
            if (info.st_dev, info.st_ino) != self._identity:
                raise CodexReceivedJournalError("receive journal identity changed")
            if (
                len(header) != 100
                or header[:16] != b"SQLite format 3\x00"
                or int.from_bytes(header[60:64], "big") != 1
                or int.from_bytes(header[68:72], "big") != _APPLICATION_ID
            ):
                raise CodexReceivedJournalError(
                    "receive journal format is unavailable; existing bytes were preserved"
                )
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=1.0)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA synchronous=FULL")
            if _regular_identity(self.path) != self._identity:
                raise CodexReceivedJournalError("receive journal identity changed")
        except BaseException:
            connection.close()
            raise
        return connection

    def _append(self, endpoint: str, generation: int, data: bytes, received_at: str) -> None:
        connection = self._connect()
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT provenance_json FROM receive_attempts WHERE inspection_id=?",
                    (self.inspection_id,),
                ).fetchone()
                if row is None or row[0] != self._provenance_json:
                    raise CodexReceivedJournalError("receive attempt provenance changed")
                usage = connection.execute(
                    "SELECT payload_bytes, records FROM receive_usage WHERE singleton=1"
                ).fetchone()
                if (
                    usage is None
                    or usage[0] + len(data) > MAX_JOURNAL_BYTES
                    or usage[1] >= MAX_JOURNAL_RECORDS
                ):
                    raise CodexReceivedJournalError(
                        "receive journal capacity reached; no records were deleted"
                    )
                connection.execute(
                    "INSERT INTO received_chunks(inspection_id, endpoint_identity, "
                    "connection_generation, received_at, payload, payload_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        self.inspection_id,
                        endpoint,
                        generation,
                        received_at,
                        data,
                        hashlib.sha256(data).hexdigest(),
                    ),
                )
                connection.execute(
                    "UPDATE receive_usage SET payload_bytes=payload_bytes+?, "
                    "records=records+1 WHERE singleton=1",
                    (len(data),),
                )
        finally:
            connection.close()

    async def append(
        self, *, endpoint_identity: str, connection_generation: int, data: bytes
    ) -> None:
        if not self._healthy:
            raise CodexReceivedJournalError(
                "receive journal is unavailable; inspect again after recovery"
            )
        if (
            not isinstance(endpoint_identity, str)
            or not re.fullmatch(r"[a-f0-9]{64}", endpoint_identity)
            or type(connection_generation) is not int
            or not 0 < connection_generation < 2**63
            or type(data) is not bytes
            or not 0 < len(data) <= MAX_CHUNK_BYTES
        ):
            self._healthy = False
            raise CodexReceivedJournalError("invalid received byte record")
        received_at = datetime.now(UTC).isoformat()
        async with self._lock:
            if (
                not self._healthy
                or self._endpoint not in {None, endpoint_identity}
                or connection_generation < self._last_generation
            ):
                self._healthy = False
                raise CodexReceivedJournalError("receive journal connection provenance changed")
            self._endpoint = endpoint_identity
            self._last_generation = connection_generation
            operation = asyncio.create_task(
                asyncio.to_thread(
                    self._append, endpoint_identity, connection_generation, data, received_at
                )
            )
            cancelled: asyncio.CancelledError | None = None
            while not operation.done():
                try:
                    await asyncio.shield(operation)
                except asyncio.CancelledError as exc:
                    cancelled = exc
                except BaseException:
                    break
            failure = (
                operation.exception()
                if not operation.cancelled()
                else CodexReceivedJournalError("receive append was cancelled")
            )
            if cancelled is not None or failure is not None:
                self._healthy = False
                if cancelled is not None:
                    raise cancelled
                raise CodexReceivedJournalError(
                    "receive journal commit failed; no automatic retry"
                ) from failure
