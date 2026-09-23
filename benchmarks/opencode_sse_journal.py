"""Bounded, exact application-level SSE capture for OpenCode diagnostics."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

MAX_SSE_BYTES = 64 * 1024 * 1024


class OpenCodeSseJournal:
    """Save the bytes consumed by the SSE decoder, without normalizing frames."""

    def __init__(self, path: Path) -> None:
        self.path = path.absolute()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        self._fd = os.open(self.path, flags, 0o600)
        self._closed = False
        self._failed = False
        self._bytes = 0
        self._chunks = 0
        self._digest = hashlib.sha256()
        self._identity = os.fstat(self._fd)

    def observe(self, path: str, payload: bytes) -> None:
        if self._closed or self._failed or path != "/global/event":
            self._failed = True
            raise RuntimeError("OpenCode SSE capture is unavailable or from an unexpected path")
        exact = bytes(payload)
        if not exact or self._bytes + len(exact) > MAX_SSE_BYTES:
            self._failed = True
            raise RuntimeError("OpenCode SSE capture exceeded its byte bound")
        try:
            view = memoryview(exact)
            while view:
                written = os.write(self._fd, view)
                if written <= 0:
                    raise OSError("OpenCode SSE capture write made no progress")
                view = view[written:]
        except Exception:
            self._failed = True
            raise
        self._digest.update(exact)
        self._bytes += len(exact)
        self._chunks += 1

    def finish(self, *, stream_count: int, capture_failed: bool, event_gap: bool) -> dict:
        if self._closed or self._failed or capture_failed or stream_count != 1 or event_gap:
            raise RuntimeError("OpenCode SSE capture is incomplete or had a stream gap")
        if not self._bytes:
            raise RuntimeError("OpenCode SSE capture has no traffic")
        os.fsync(self._fd)
        descriptor = os.fstat(self._fd)
        path_stat = os.stat(self.path, follow_symlinks=False)
        if (
            not stat.S_ISREG(descriptor.st_mode)
            or (descriptor.st_dev, descriptor.st_ino) != (path_stat.st_dev, path_stat.st_ino)
            or (descriptor.st_dev, descriptor.st_ino)
            != (self._identity.st_dev, self._identity.st_ino)
            or descriptor.st_size != self._bytes
        ):
            raise RuntimeError("OpenCode SSE capture path changed")
        os.lseek(self._fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        read_bytes = 0
        while read_bytes < self._bytes:
            chunk = os.read(self._fd, min(1024 * 1024, self._bytes - read_bytes))
            if not chunk:
                raise RuntimeError("OpenCode SSE capture was truncated")
            digest.update(chunk)
            read_bytes += len(chunk)
        if digest.hexdigest() != self._digest.hexdigest():
            raise RuntimeError("OpenCode SSE capture changed during verification")
        self.abort()
        return {
            "path": str(self.path),
            "sha256": digest.hexdigest(),
            "bytes": self._bytes,
            "chunks": self._chunks,
            "stream_count": stream_count,
            "scope": "post_content_decoding_sse_bytes",
        }

    def abort(self) -> None:
        if self._closed:
            return
        try:
            os.fsync(self._fd)
        finally:
            os.close(self._fd)
            self._closed = True
