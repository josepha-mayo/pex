"""Explicit local-origin choice, bound to its installation directory.

Directory object IDs are not machine attestation. Copying a choice to another
directory requires operator reconfirmation; no hostname is guessed or rewritten.
Callers serialize saves with the attachment-manager and bridge-process locks.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pex_protocol.project_identity import PhysicalIdentityProof, ProjectOrigin
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pex_bridge.adapters.strict_json import strict_json_dumps, strict_json_loads
from pex_bridge.local_workspace import measure_local_directory

MAX_LOCAL_ORIGIN_CHOICE_BYTES = 16_384
_MAX_REVISION = 2**63 - 1
_CHOICE_ID = re.compile(r"[a-f0-9]{32}\Z")
_SCHEMA = "pex.local-origin-choice.v1"
_FIELDS = {"schema", "revision", "choice_id", "origin", "storage_physical"}
_PROVIDERS = {"pex-os-stat-windows-v1", "pex-os-stat-posix-v1"}


class LocalOriginConfigError(ValueError):
    """The choice cannot be read or written with verified local identity."""


class LocalOriginConflict(LocalOriginConfigError):
    """The caller's exact prior revision/incarnation is no longer current."""


class LocalOriginChoice(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_version: Literal["pex.local-origin-choice.v1"] = Field(default=_SCHEMA, alias="schema")
    revision: int = Field(ge=1, le=_MAX_REVISION)
    choice_id: str
    origin: ProjectOrigin
    storage_physical: PhysicalIdentityProof

    @field_validator("choice_id")
    @classmethod
    def _validate_choice_id(cls, value: str) -> str:
        if not _CHOICE_ID.fullmatch(value) or UUID(hex=value).version != 4:
            raise ValueError("local-origin choice id must be canonical UUID4 hex")
        return value

    @field_validator("storage_physical")
    @classmethod
    def _validate_storage_provider(cls, value: PhysicalIdentityProof) -> PhysicalIdentityProof:
        if value.provider not in _PROVIDERS:
            raise ValueError("local-origin storage measurement provider is unsupported")
        for object_id in (value.volume_id, value.object_id):
            if not re.fullmatch(r"[1-9][0-9]{0,38}", object_id) or int(object_id) >= 2**128:
                raise ValueError(
                    "local-origin storage identity must be a measured positive integer"
                )
        return value


class LocalOriginBindingMismatch(LocalOriginConfigError):
    """A well-formed choice needs explicit installation-directory reconfirmation."""

    def __init__(self, choice: LocalOriginChoice) -> None:
        self.choice = choice
        super().__init__("local-origin storage identity changed; operator reconfirmation required")


@dataclass(frozen=True)
class _ChoiceFile:
    choice: LocalOriginChoice
    raw: bytes
    signature: tuple[int, int, int, int, int]


def _signature(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _regular(info: os.stat_result) -> bool:
    return bool(
        stat.S_ISREG(info.st_mode)
        and not getattr(info, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _path(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or not path.name:
        raise LocalOriginConfigError("local-origin configuration requires an absolute file path")
    return path


def _measure_parent(path: Path) -> PhysicalIdentityProof:
    try:
        measured = measure_local_directory(str(path.parent)).physical
    except (OSError, ValueError) as exc:
        raise LocalOriginConfigError("local-origin storage directory cannot be verified") from exc
    if measured.provider not in _PROVIDERS:
        raise LocalOriginConfigError("local-origin storage measurement provider is unsupported")
    return measured


def _read_file(path: Path) -> _ChoiceFile | None:
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    if not _regular(before):
        raise LocalOriginConfigError("local-origin choice must be a regular, non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        # Windows lstat and fstat expose different legacy ctime meanings. Compare
        # object identity, size and mtime across APIs; ctime still participates
        # in comparisons made through the same API before/after the read.
        if not _regular(opened) or _signature(opened)[:4] != _signature(before)[:4]:
            raise LocalOriginConflict("local-origin file changed while opening")
        raw = handle.read(MAX_LOCAL_ORIGIN_CHOICE_BYTES + 1)
        if _signature(os.fstat(handle.fileno())) != _signature(opened):
            raise LocalOriginConflict("local-origin file changed while reading")
    try:
        after = path.lstat()
    except FileNotFoundError as exc:
        raise LocalOriginConflict("local-origin file disappeared while reading") from exc
    if not _regular(after) or _signature(after) != _signature(before):
        raise LocalOriginConflict("local-origin file was replaced while reading")
    if len(raw) > MAX_LOCAL_ORIGIN_CHOICE_BYTES:
        raise LocalOriginConfigError("local-origin choice exceeds its safety bound")
    try:
        payload = strict_json_loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != _FIELDS:
            raise ValueError("local-origin choice fields are invalid")
        choice = LocalOriginChoice.model_validate(payload, strict=True)
    except (ValueError, RecursionError) as exc:
        raise LocalOriginConfigError(
            "local-origin choice must contain strict, valid UTF-8 JSON"
        ) from exc
    return _ChoiceFile(choice, raw, _signature(after))


def load_local_origin_choice(path: Path) -> LocalOriginChoice | None:
    path = _path(path)
    stored = _read_file(path)
    if stored is None:
        return None
    measured = _measure_parent(path)
    # Verify the selected file did not move while the directory was measured.
    if _read_file(path) != stored:
        raise LocalOriginConflict("local-origin choice changed during directory measurement")
    if stored.choice.storage_physical != measured:
        raise LocalOriginBindingMismatch(stored.choice)
    return stored.choice


def save_local_origin_choice(
    path: Path,
    origin: ProjectOrigin,
    *,
    expected_revision: int | None,
    expected_choice_id: str | None,
    allow_storage_rebind: bool = False,
) -> LocalOriginChoice:
    """CAS a bounded choice through an exclusive, fsynced same-directory temp.

    No directory is created implicitly. Corrupt existing data never becomes a
    first-run choice. A post-replace I/O error is uncertain: reload before retry.
    External same-user mutations cannot be made fully atomic by these checks;
    the application's manager/process locks are required around this operation.
    In particular, the last verified sample is not a lock against replacement
    between temporary-file verification and os.replace.
    """
    path = _path(path)
    if type(allow_storage_rebind) is not bool:
        raise LocalOriginConfigError("storage rebind consent must be boolean")
    if (expected_revision is None) != (expected_choice_id is None):
        raise LocalOriginConflict("revision and choice id must identify the same prior choice")
    if expected_revision is not None and (
        type(expected_revision) is not int
        or not 1 <= expected_revision <= _MAX_REVISION
        or not isinstance(expected_choice_id, str)
        or not _CHOICE_ID.fullmatch(expected_choice_id)
    ):
        raise LocalOriginConflict("expected local-origin revision or choice id is invalid")
    if not isinstance(origin, ProjectOrigin):
        raise LocalOriginConfigError("local origin must be a typed ProjectOrigin")
    origin = ProjectOrigin.model_validate(origin.model_dump(), strict=True)
    measured = _measure_parent(path)
    previous = _read_file(path)
    if previous is None:
        if expected_revision is not None:
            raise LocalOriginConflict("the expected local-origin choice is missing")
        revision = 1
    else:
        if (
            previous.choice.revision != expected_revision
            or previous.choice.choice_id != expected_choice_id
        ):
            raise LocalOriginConflict("local-origin choice changed; reload before saving")
        if previous.choice.storage_physical != measured and not allow_storage_rebind:
            raise LocalOriginBindingMismatch(previous.choice)
        revision = previous.choice.revision + 1
    choice = LocalOriginChoice(
        revision=revision,
        choice_id=uuid4().hex,
        origin=origin,
        storage_physical=measured,
    )
    payload = (
        strict_json_dumps(
            choice.model_dump(mode="json", by_alias=True),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")
    if len(payload) > MAX_LOCAL_ORIGIN_CHOICE_BYTES:
        raise LocalOriginConfigError("local-origin choice exceeds its safety bound")
    temporary = path.parent / f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp"
    temporary_identity: tuple[int, int] | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            info = os.fstat(handle.fileno())
            temporary_identity = (info.st_dev, info.st_ino)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        if _measure_parent(path) != measured or _read_file(path) != previous:
            raise LocalOriginConflict("local-origin storage or choice changed before replacement")
        # Identity alone is insufficient: another actor can modify that object.
        # The cleanup below may remove only our original temporary inode; a
        # foreign replacement object must remain untouched on rejection.
        candidate = _read_file(temporary)
        if (
            candidate is None
            or candidate.signature[:2] != temporary_identity
            or candidate.raw != payload
        ):
            raise LocalOriginConflict("local-origin temporary file changed before replacement")
        os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        if load_local_origin_choice(path) != choice:
            raise LocalOriginConflict("local-origin replacement could not be verified; reload")
        return choice
    finally:
        if temporary_identity is not None:
            try:
                info = temporary.lstat()
            except FileNotFoundError:
                pass
            else:
                if (info.st_dev, info.st_ino) == temporary_identity:
                    temporary.unlink()


__all__ = [
    "LocalOriginChoice",
    "LocalOriginConfigError",
    "LocalOriginConflict",
    "LocalOriginBindingMismatch",
    "MAX_LOCAL_ORIGIN_CHOICE_BYTES",
    "load_local_origin_choice",
    "save_local_origin_choice",
]
