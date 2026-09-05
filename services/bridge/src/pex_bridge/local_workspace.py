"""Server-observed local directory identity, not a filesystem lock.

The samples below detect replacement or alias retargeting observed during the
check. They cannot prevent a later rename, inode reuse, mount change or race,
and do not prove which cwd handle an already-running worker retains. Callers
must separately bind local-machine origin and revalidate at authority boundaries.

Python 3.12 documents nonzero st_ino as identity within st_dev, including Windows
file indexes (up to 128 bits): https://docs.python.org/3.12/library/os.html#os.stat_result
No content, timestamp or caller-supplied proof-provider mapping is used.
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from pex_protocol.project_identity import PathPlatform, PhysicalIdentityProof

MAX_LOCAL_PATH_CHARS = 4096
MAX_CANONICAL_PATH_CHARS = 8192
_os_stat = os.stat


@dataclass(frozen=True, slots=True)
class LocalDirectoryIdentity:
    cwd: str
    platform: PathPlatform
    physical: PhysicalIdentityProof


def _host_platform() -> PathPlatform:
    if os.name == "nt":
        return PathPlatform.WINDOWS
    if os.name == "posix":
        return PathPlatform.POSIX
    raise ValueError("local directory identity is unsupported on this platform")


def _absolute_path(path: str) -> Path:
    if (
        not isinstance(path, str)
        or not path
        or len(path) > MAX_LOCAL_PATH_CHARS
        or "\x00" in path
        or "\r" in path
        or "\n" in path
    ):
        raise ValueError("local directory path is invalid")
    result = Path(path)
    if not result.is_absolute():
        raise ValueError("local directory path must be absolute")
    return result


def _resolved_directory(path: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_absolute() or len(str(resolved)) > MAX_CANONICAL_PATH_CHARS:
        raise ValueError("resolved local directory path is invalid")
    return resolved


def _directory_proof(
    path: Path, platform: PathPlatform, *, follow_symlinks: bool,
) -> PhysicalIdentityProof:
    observed = _os_stat(path, follow_symlinks=follow_symlinks)
    mode = getattr(observed, "st_mode", None)
    if type(mode) is not int or not stat.S_ISDIR(mode):
        raise ValueError("local workspace is not a real directory")
    if not follow_symlinks and platform == PathPlatform.WINDOWS:
        attributes = getattr(observed, "st_file_attributes", 0)
        if type(attributes) is not int or attributes < 0 or (
            attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise ValueError("resolved local directory has an unsupported reparse point")
    device, inode = getattr(observed, "st_dev", None), getattr(observed, "st_ino", None)
    # Zero/absent identities are deliberately unsupported. Do not substitute
    # timestamps, directory contents or lexical names when the OS has no ID.
    if any(type(value) is not int or not 0 < value < 2**128 for value in (device, inode)):
        raise ValueError("local filesystem does not provide supported directory identity")
    return PhysicalIdentityProof(
        provider=f"pex-os-stat-{platform.value}-v1",
        volume_id=str(device),
        object_id=str(inode),
    )


def measure_local_directory(path: str) -> LocalDirectoryIdentity:
    """Measure a stable sampled target through original and resolved paths.

    Normal symlink/junction aliases are resolved, not mistaken for their target
    identity. A change seen across these bounded samples fails closed. Filesystem
    errors are reported without echoing a potentially sensitive input path.
    """
    original = _absolute_path(path)
    platform = _host_platform()
    try:
        first = _directory_proof(original, platform, follow_symlinks=True)
        resolved = _resolved_directory(original)
        canonical = _directory_proof(resolved, platform, follow_symlinks=False)
        resolved_again = _resolved_directory(original)
        last = _directory_proof(original, platform, follow_symlinks=True)
        canonical_again = _directory_proof(resolved_again, platform, follow_symlinks=False)
        if (
            os.path.normcase(str(resolved)) != os.path.normcase(str(resolved_again))
            or not first == canonical == last == canonical_again
        ):
            raise ValueError("local directory changed during identity measurement")
        return LocalDirectoryIdentity(
            cwd=str(resolved_again), platform=platform, physical=canonical_again,
        )
    except (OSError, RuntimeError, NotImplementedError) as exc:
        raise ValueError("local directory identity could not be measured") from exc


def require_same_local_directory(path: str, expected: LocalDirectoryIdentity) -> None:
    """Reject a changed canonical target, platform or provider-specific identity."""
    if (
        not isinstance(expected, LocalDirectoryIdentity)
        or not isinstance(expected.cwd, str)
        or not isinstance(expected.platform, PathPlatform)
        or not isinstance(expected.physical, PhysicalIdentityProof)
    ):
        raise ValueError("expected local directory identity is invalid")
    measured = measure_local_directory(path)
    if (
        measured.platform != expected.platform
        or os.path.normcase(measured.cwd) != os.path.normcase(expected.cwd)
        or measured.physical != expected.physical
    ):
        raise ValueError("local directory identity changed")
