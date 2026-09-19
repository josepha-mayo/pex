"""Linux creation identity for cleanup resources, stable across same-device rename."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path


class _Timestamp(ctypes.Structure):
    _fields_ = [
        ("seconds", ctypes.c_int64),
        ("nanoseconds", ctypes.c_uint32),
        ("reserved", ctypes.c_int32),
    ]


class _Statx(ctypes.Structure):
    # Linux UAPI statx has a fixed 256-byte layout. The unused tail includes
    # newer optional fields; keeping it reserved supports older libc versions.
    _fields_ = [
        ("mask", ctypes.c_uint32),
        ("block_size", ctypes.c_uint32),
        ("attributes", ctypes.c_uint64),
        ("links", ctypes.c_uint32),
        ("uid", ctypes.c_uint32),
        ("gid", ctypes.c_uint32),
        ("mode", ctypes.c_uint16),
        ("spare", ctypes.c_uint16),
        ("inode", ctypes.c_uint64),
        ("size", ctypes.c_uint64),
        ("blocks", ctypes.c_uint64),
        ("attributes_mask", ctypes.c_uint64),
        ("atime", _Timestamp),
        ("btime", _Timestamp),
        ("ctime", _Timestamp),
        ("mtime", _Timestamp),
        ("rdev_major", ctypes.c_uint32),
        ("rdev_minor", ctypes.c_uint32),
        ("dev_major", ctypes.c_uint32),
        ("dev_minor", ctypes.c_uint32),
        ("tail", ctypes.c_uint64 * 14),
    ]


def linux_birthtime_ns(path: Path, observed: os.stat_result) -> int:
    """Refuse cleanup if creation identity is unavailable or the entity changed.

    Device/inode alone can accept a replacement after Linux reuses an inode.
    ctime changes on rename, so it cannot identify a quarantined resource.
    See https://man7.org/linux/man-pages/man2/statx.2.html.
    """
    try:
        statx = ctypes.CDLL(None, use_errno=True).statx
    except (AttributeError, OSError) as exc:
        raise ValueError("cleanup requires filesystem creation identity (statx)") from exc
    statx.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(_Statx),
    ]
    statx.restype = ctypes.c_int
    result = _Statx()
    # AT_FDCWD, AT_SYMLINK_NOFOLLOW, STATX_TYPE | STATX_INO | STATX_BTIME.
    if statx(-100, os.fsencode(path), 0x100, 0x901, ctypes.byref(result)) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), os.fspath(path))
    if result.mask & 0x901 != 0x901:
        raise ValueError("cleanup requires filesystem creation identity (STATX_BTIME)")
    if (
        result.inode != observed.st_ino
        or (result.dev_major, result.dev_minor)
        != (os.major(observed.st_dev), os.minor(observed.st_dev))
        or (result.mode & 0o170000) != (observed.st_mode & 0o170000)
    ):
        raise ValueError("lifecycle resource changed while reading its identity")
    return result.btime.seconds * 1_000_000_000 + result.btime.nanoseconds
