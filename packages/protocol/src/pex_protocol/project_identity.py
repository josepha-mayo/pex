from __future__ import annotations

import hashlib
import json
import ntpath
import posixpath
import re
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROJECT_LOCATOR_SCHEMA = "pex.project-locator.v2"
PROJECT_IDENTITY_SCHEMA = "pex.project-identity.v2"
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_DRIVE_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_DRIVE_RELATIVE = re.compile(r"^[A-Za-z]:(?:$|[^\\/])")
_ASCII_UPPER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


class ProjectLocatorKind(StrEnum):
    LOCAL_PATH = "local_path"
    REMOTE_PATH = "remote_path"
    REPOSITORY_URI = "repository_uri"
    PROVIDER_WORKSPACE = "provider_workspace"
    WORKSPACE_SET = "workspace_set"
    OPAQUE = "opaque"


class PathPlatform(StrEnum):
    POSIX = "posix"
    WINDOWS = "windows"


class ProjectOrigin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str = Field(min_length=1, max_length=256)
    host: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_origin(self) -> Self:
        if not _SAFE_LABEL.fullmatch(self.namespace):
            raise ValueError("project origin namespace is invalid")
        if self.host != self.host.strip() or "\x00" in self.host:
            raise ValueError("project origin host is invalid")
        return self

    @property
    def canonical_host(self) -> str:
        # Repository DNS hosts are case-insensitive. Other namespaces may carry
        # provider tenant/workspace identifiers whose case contract is unknown,
        # so conservative exact matching avoids a cross-tenant merge.
        if self.namespace == "repository":
            return self.host.translate(_ASCII_UPPER)
        return self.host


class PhysicalIdentityProof(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1, max_length=128)
    volume_id: str = Field(min_length=1, max_length=512)
    object_id: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_proof(self) -> Self:
        if not _SAFE_LABEL.fullmatch(self.provider):
            raise ValueError("physical proof provider is invalid")
        for value in (self.volume_id, self.object_id):
            if value != value.strip() or "\x00" in value:
                raise ValueError("physical proof value is invalid")
        return self

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.provider, self.volume_id, self.object_id)


def _validate_raw(value: str, *, label: str, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise ValueError(f"{label} is invalid")
    if "\x00" in value or value != value.rstrip("\r\n"):
        raise ValueError(f"{label} is invalid")
    return value


def _canonical_posix_path(raw: str) -> str:
    _validate_raw(raw, label="POSIX project path")
    if not raw.startswith("/"):
        raise ValueError("POSIX project path must be absolute")
    canonical = posixpath.normpath(raw)
    if not canonical.startswith("/"):
        raise ValueError("POSIX project path normalization escaped its root")
    return canonical


def _canonical_windows_path(raw: str) -> str:
    _validate_raw(raw, label="Windows project path")
    normalized_separators = raw.replace("/", "\\")
    device_path = normalized_separators.startswith("\\\\?\\")
    if device_path and not (
        re.match(r"^\\\\\?\\[A-Za-z]:\\", normalized_separators)
        or re.match(r"^\\\\\?\\UNC\\[^\\]+\\[^\\]+", normalized_separators, re.I)
    ):
        raise ValueError("Windows device project path is unsupported or incomplete")
    if _DRIVE_RELATIVE.match(normalized_separators):
        raise ValueError("Windows drive-relative project paths are ambiguous")
    if not (
        _DRIVE_ABSOLUTE.match(normalized_separators) or normalized_separators.startswith("\\\\")
    ):
        raise ValueError("Windows project path must be drive-absolute or UNC")
    if normalized_separators.startswith("\\\\") and not device_path:
        unc_parts = [part for part in normalized_separators.split("\\") if part]
        if len(unc_parts) < 2:
            raise ValueError("Windows UNC project path requires server and share")
    if device_path:
        # Extended-length paths deliberately bypass Win32 normalization. Never
        # invent lexical equivalence by collapsing dot segments on their behalf.
        device_parts = [part for part in normalized_separators.split("\\") if part]
        if any(part in {".", ".."} for part in device_parts):
            raise ValueError("Windows device project path contains an ambiguous dot segment")
    if not device_path:
        parts = [part for part in normalized_separators.split("\\") if part]
        checked_parts = parts[1:] if parts and parts[0].endswith(":") else parts
        if any(part not in {".", ".."} and part.endswith((" ", ".")) for part in checked_parts):
            raise ValueError("Windows project path has an ambiguous trailing dot or space")
    canonical = (
        normalized_separators if device_path else ntpath.normpath(normalized_separators)
    ).replace("\\", "/")
    folded_canonical = canonical.translate(_ASCII_UPPER)
    if normalized_separators.startswith("\\\\") and not device_path:
        unc_root = "/".join(unc_parts[:2]).translate(_ASCII_UPPER)
        if (
            not folded_canonical.removeprefix("//").startswith(f"{unc_root}/")
            and folded_canonical != f"//{unc_root}"
        ):
            raise ValueError("Windows UNC project path escaped its share root")
    if re.fullmatch(r"[A-Za-z]:", canonical):
        canonical += "/"
    # Avoid Unicode case-fold collisions such as sharp-s versus ss. Physical
    # identity can establish aliases that conservative lexical identity cannot.
    return folded_canonical


def canonical_absolute_path(raw: str) -> tuple[PathPlatform, str]:
    """Return a conservative lexical identity for one absolute local path.

    This deliberately does not touch the filesystem: an observation must not
    acquire authority by resolving a symlink, a drive mapping, or another local
    alias.  It is suitable only for comparing two already-bound path strings.
    """

    _validate_raw(raw, label="absolute path")
    if raw != raw.strip():
        raise ValueError("absolute path must not have surrounding whitespace")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in raw):
        raise ValueError("absolute path must not contain control characters")
    if any(part in {".", ".."} for part in re.split(r"[\\/]", raw)):
        raise ValueError("absolute path must not contain dot components")
    # A leading ``//`` is POSIX syntax too.  Do not make a Windows UNC claim
    # from slash-only input, where doing so would silently case-fold a POSIX path.
    if raw.startswith("//"):
        raise ValueError("absolute path has an ambiguous slash-only UNC prefix")
    normalized_separators = raw.replace("/", "\\")
    if _DRIVE_ABSOLUTE.match(normalized_separators) or raw.startswith("\\\\"):
        return PathPlatform.WINDOWS, _canonical_windows_path(raw)
    if raw.startswith("/"):
        return PathPlatform.POSIX, _canonical_posix_path(raw)
    raise ValueError("absolute path must be POSIX-absolute, drive-absolute, or UNC")


def same_absolute_path(left: str | None, right: str | None) -> bool:
    """Compare two absolute paths without filesystem resolution or alias trust."""

    if not isinstance(left, str) or not isinstance(right, str):
        return False
    try:
        return canonical_absolute_path(left) == canonical_absolute_path(right)
    except ValueError:
        return False


def _canonical_repository_uri(raw: str) -> tuple[str, ProjectOrigin]:
    _validate_raw(raw, label="repository URI")
    split = urlsplit(raw)
    if split.scheme not in {"https", "ssh"} or not split.hostname:
        raise ValueError("repository URI must use https or ssh with a host")
    if split.username or split.password or split.query or split.fragment:
        raise ValueError("repository URI credentials, query, and fragment are forbidden")
    if "\\" in split.path or not split.path.startswith("/"):
        raise ValueError("repository URI path is invalid")
    host = split.hostname.translate(_ASCII_UPPER)
    port = split.port
    default_port = (split.scheme == "https" and port in {None, 443}) or (
        split.scheme == "ssh" and port in {None, 22}
    )
    display_host = f"[{host}]" if ":" in host else host
    authority = display_host if default_port else f"{display_host}:{port}"
    path = posixpath.normpath(split.path)
    canonical = urlunsplit((split.scheme, authority, path, "", ""))
    return canonical, ProjectOrigin(namespace="repository", host=authority)


class ProjectLocator(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_version: Literal["pex.project-locator.v2"] = Field(
        default=PROJECT_LOCATOR_SCHEMA,
        alias="schema",
    )
    kind: ProjectLocatorKind
    raw: str = Field(min_length=1, max_length=4096)
    canonical: str = Field(min_length=1, max_length=8192)
    origin: ProjectOrigin
    platform: PathPlatform | None = None
    members: tuple[ProjectLocator, ...] = ()
    physical: PhysicalIdentityProof | None = None

    @model_validator(mode="after")
    def validate_binding(self) -> Self:
        _validate_raw(self.raw, label="project locator")
        expected: str
        if self.kind in {
            ProjectLocatorKind.LOCAL_PATH,
            ProjectLocatorKind.REMOTE_PATH,
        }:
            if self.platform is None or self.members:
                raise ValueError("path locator platform/member binding is invalid")
            expected = (
                _canonical_windows_path(self.raw)
                if self.platform == PathPlatform.WINDOWS
                else _canonical_posix_path(self.raw)
            )
        elif self.kind == ProjectLocatorKind.REPOSITORY_URI:
            if self.platform is not None or self.members or self.physical is not None:
                raise ValueError("repository locator platform/member binding is invalid")
            expected, uri_origin = _canonical_repository_uri(self.raw)
            if self.origin != uri_origin:
                raise ValueError("repository locator origin does not match its URI")
        elif self.kind == ProjectLocatorKind.WORKSPACE_SET:
            if self.platform is not None or not self.members or self.physical is not None:
                raise ValueError("workspace set requires members and no platform")
            fingerprints = sorted(member.fingerprint for member in self.members)
            if len(fingerprints) != len(set(fingerprints)):
                raise ValueError("workspace set contains a duplicate locator")
            expected = "set:" + hashlib.sha256("\n".join(fingerprints).encode("ascii")).hexdigest()
        else:
            if self.platform is not None or self.members or self.physical is not None:
                raise ValueError("opaque locator platform/member binding is invalid")
            expected = self.raw
        if self.canonical != expected:
            raise ValueError("project locator canonical value does not match its typed input")
        return self

    @classmethod
    def path(
        cls,
        raw: str,
        *,
        platform: PathPlatform,
        origin: ProjectOrigin,
        remote: bool = False,
        physical: PhysicalIdentityProof | None = None,
    ) -> Self:
        canonical = (
            _canonical_windows_path(raw)
            if platform == PathPlatform.WINDOWS
            else _canonical_posix_path(raw)
        )
        return cls(
            kind=(ProjectLocatorKind.REMOTE_PATH if remote else ProjectLocatorKind.LOCAL_PATH),
            raw=raw,
            canonical=canonical,
            origin=origin,
            platform=platform,
            physical=physical,
        )

    @classmethod
    def repository(cls, raw: str) -> Self:
        canonical, origin = _canonical_repository_uri(raw)
        return cls(
            kind=ProjectLocatorKind.REPOSITORY_URI,
            raw=raw,
            canonical=canonical,
            origin=origin,
        )

    @classmethod
    def provider_workspace(
        cls,
        raw: str,
        *,
        origin: ProjectOrigin,
    ) -> Self:
        _validate_raw(raw, label="provider workspace")
        return cls(
            kind=ProjectLocatorKind.PROVIDER_WORKSPACE,
            raw=raw,
            canonical=raw,
            origin=origin,
        )

    @classmethod
    def opaque(cls, raw: str, *, origin: ProjectOrigin) -> Self:
        _validate_raw(raw, label="opaque project locator")
        return cls(
            kind=ProjectLocatorKind.OPAQUE,
            raw=raw,
            canonical=raw,
            origin=origin,
        )

    @classmethod
    def workspace_set(
        cls,
        members: tuple[ProjectLocator, ...] | list[ProjectLocator],
        *,
        origin: ProjectOrigin,
        display: str = "workspace set",
    ) -> Self:
        frozen = tuple(members)
        fingerprints = sorted(member.fingerprint for member in frozen)
        if not fingerprints:
            raise ValueError("workspace set requires at least one member")
        canonical = "set:" + hashlib.sha256("\n".join(fingerprints).encode("ascii")).hexdigest()
        return cls(
            kind=ProjectLocatorKind.WORKSPACE_SET,
            raw=display,
            canonical=canonical,
            origin=origin,
            members=frozen,
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "schema": self.schema_version,
            "kind": self.kind.value,
            "origin": {
                "namespace": self.origin.namespace,
                "host": self.origin.canonical_host,
            },
            "platform": self.platform.value if self.platform is not None else None,
            "canonical": self.canonical,
            "members": sorted(member.fingerprint for member in self.members),
            "physical": (
                {
                    "provider": self.physical.provider,
                    "volume_id": self.physical.volume_id,
                    "object_id": self.physical.object_id,
                }
                if self.physical is not None
                else None
            ),
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "ploc_" + hashlib.sha256(encoded).hexdigest()


def same_project_locator(left: ProjectLocator, right: ProjectLocator) -> bool:
    same_lexical_locator = bool(
        left.kind == right.kind
        and left.origin.namespace == right.origin.namespace
        and left.origin.canonical_host == right.origin.canonical_host
        and left.platform == right.platform
        and left.canonical == right.canonical
        and sorted(member.fingerprint for member in left.members)
        == sorted(member.fingerprint for member in right.members)
    )
    if same_lexical_locator:
        if (
            left.physical is not None
            and right.physical is not None
            and left.physical.key != right.physical.key
        ):
            return False
        return True
    return bool(
        left.origin.namespace == right.origin.namespace
        and left.origin.canonical_host == right.origin.canonical_host
        and left.physical is not None
        and right.physical is not None
        and left.physical.key == right.physical.key
    )


class ProjectIdentity(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
        serialize_by_alias=True,
    )

    schema_version: Literal["pex.project-identity.v2"] = Field(
        default=PROJECT_IDENTITY_SCHEMA,
        alias="schema",
    )
    id: str = Field(pattern=r"^prj_[0-9a-f]{32}$")
    locator_fingerprints: tuple[str, ...]
    created_at: datetime

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if not self.locator_fingerprints:
            raise ValueError("project identity requires a locator fingerprint")
        if tuple(sorted(set(self.locator_fingerprints))) != self.locator_fingerprints:
            raise ValueError("project identity locators must be unique and sorted")
        if any(
            not re.fullmatch(r"ploc_[0-9a-f]{64}", value) for value in self.locator_fingerprints
        ):
            raise ValueError("project identity locator fingerprint is invalid")
        if self.created_at.tzinfo is None:
            raise ValueError("project identity timestamp must be timezone-aware")
        return self

    @classmethod
    def create(
        cls,
        locators: list[ProjectLocator] | tuple[ProjectLocator, ...],
        *,
        now: datetime,
    ) -> Self:
        fingerprints = tuple(sorted({locator.fingerprint for locator in locators}))
        return cls(
            id=f"prj_{uuid4().hex}",
            locator_fingerprints=fingerprints,
            created_at=now,
        )


ProjectLocator.model_rebuild()
