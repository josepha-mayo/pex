"""Project binding comparison without treating every identifier as a Windows path."""

import re

from pex_protocol.project_identity import canonical_absolute_path

_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def project_binding_key(value: str) -> str:
    """Preserve opaque/POSIX IDs; retain legacy absolute Windows drive spelling.

    This is transport comparison, not proof of filesystem identity. In particular
    it does not resolve symlinks, relative paths, UNC aliases or filesystem case
    sensitivity. Those still require the bridge's workspace-authority witness.
    """
    if not _WINDOWS_DRIVE_PATH.match(value):
        return value
    try:
        # Reuse conservative ASCII case normalization, preserving drive roots
        # and avoiding Unicode case-fold collisions such as sharp-s versus ss.
        return canonical_absolute_path(value)[1]
    except ValueError:
        return value
