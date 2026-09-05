"""Selected local workspace authority, separate from vendor thread identity.

These are bounded filesystem samples plus an explicit operator origin choice,
not machine attestation or an atomic lock on the worker's cwd.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal

from pex_protocol.project_identity import ProjectLocator, ProjectLocatorKind
from pydantic import BaseModel, ConfigDict

from pex_bridge.local_origin_config import LocalOriginChoice, load_local_origin_choice
from pex_bridge.local_workspace import (
    LocalDirectoryIdentity,
    measure_local_directory,
    require_same_local_directory,
)


class WorkspaceAuthorityError(ValueError):
    """A saved workspace witness no longer authorizes new processing.

    Historical observation and effect receipts remain valid records. Callers
    must settle them without treating this error as proof that dispatched work
    never ran, or as permission to inspect a replacement directory.
    """

    code = "workspace_authority_changed"


class WorkspaceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["pex.local-workspace-binding.v1"] = "pex.local-workspace-binding.v1"
    project_id: str
    project_binding: str
    origin_choice: LocalOriginChoice
    directory: LocalDirectoryIdentity
    locator: ProjectLocator | None


def require_locator_directory(
    locator: ProjectLocator,
    choice: LocalOriginChoice,
    directory: LocalDirectoryIdentity,
) -> None:
    # Origin comparison must precede touching the locator's path: it can refer
    # to a foreign machine even if that lexical path happens to exist here.
    if (
        locator.kind != ProjectLocatorKind.LOCAL_PATH
        or locator.origin != choice.origin
        or locator.platform != directory.platform
        or (locator.physical is not None and locator.physical != directory.physical)
    ):
        raise ValueError("project locator does not identify the selected local origin")
    require_same_local_directory(locator.raw, directory)


def require_local_locator_consistency(
    locators: Iterable[ProjectLocator],
    choice: LocalOriginChoice,
    directory: LocalDirectoryIdentity,
) -> None:
    """Do not bypass a conflicting physical claim using an older bare locator."""
    for locator in locators:
        if (
            locator.kind != ProjectLocatorKind.LOCAL_PATH
            or locator.origin != choice.origin
            or locator.platform != directory.platform
        ):
            continue
        try:
            require_same_local_directory(locator.raw, directory)
        except ValueError:
            continue
        if locator.physical is not None and locator.physical != directory.physical:
            raise ValueError("local project has conflicting or unsupported physical identity")


def require_current_workspace(binding: WorkspaceBinding, origin_path: Path) -> None:
    if load_local_origin_choice(origin_path) != binding.origin_choice:
        raise ValueError("local origin choice changed; inspect the workspace again")
    require_same_local_directory(binding.directory.cwd, binding.directory)
    if binding.locator is not None:
        require_locator_directory(binding.locator, binding.origin_choice, binding.directory)
    elif not binding.project_binding.startswith("legacy:") or os.path.normcase(
        measure_local_directory(binding.project_id).cwd
    ) != os.path.normcase(binding.directory.cwd):
        raise ValueError("unregistered project must name the exact selected local directory")


def require_workspace_sample(
    binding: WorkspaceBinding, origin_path: Path, *, cwd: str | None = None
) -> None:
    """Recheck a server-issued witness at a synchronous local-read boundary.

    This does not replace Store's transactional locator/session validation or
    make filesystem sampling atomic. Never construct the path from event data.
    """
    try:
        require_current_workspace(binding, origin_path)
        if cwd is not None:
            require_same_local_directory(cwd, binding.directory)
    except (ValueError, OSError) as exc:
        raise WorkspaceAuthorityError("workspace authority changed before evidence use") from exc
