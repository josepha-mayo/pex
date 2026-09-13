from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = Path(
    "apps/desktop/src-tauri/target/release/bundle/nsis/PEX_0.1.0_x64-setup.exe"
)
ARCHITECTURE = Path("docs/architecture/pex-architecture.png")
MARK = Path("docs/demo/assets/pex-mark.png")

ACTIVE_GUIDES = (
    Path("docs/SUBMISSION.md"),
    Path("docs/demo/DEVPOST_FINAL_PAYLOAD.md"),
    Path("docs/demo/README.md"),
    Path("docs/demo/RECORDING_RUNBOOK.md"),
    Path("docs/demo/REHEARSAL_CARD.md"),
    Path("docs/demo/SECOND_LAPTOP_ACCEPTANCE.md"),
    Path("docs/demo/TOMORROW_SHIP_CARD.md"),
    Path("docs/demo/VOICEOVER_SCRIPT.md"),
)

STALE_PATTERNS = (
    "fc20329",
    "9df8f6e14e75b7d7aa5e2a83e744919264b6a0e0f4dd66d8831478e1093fce95",
    "LIVE_OPENCODE_RECOVERY_FC20329",
)


@dataclass(frozen=True)
class ArtifactSpec:
    path: Path
    size: int
    sha256: str
    dimensions: tuple[int, int] | None = None


ARTIFACTS = (
    ArtifactSpec(
        INSTALLER,
        101_722_399,
        "63d9f4ae90ac9b3f83f5334b3d3c9abf8ef3db7d8be82e87ff1876f3b007b18a",
    ),
    ArtifactSpec(
        ARCHITECTURE,
        94_752,
        "dea91e42f057aea78a2d7c61add7b36de1ad3fc630a742bfd916e1a016fadd68",
        (1600, 900),
    ),
    ArtifactSpec(
        MARK,
        99_348,
        "61ff11794df490525b95a3e7b83c6c635e641f01c50f1a0cb8187f1276709795",
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int] | None:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", header[16:24])


def validate_video_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").lower()
    allowed = host in {"youtu.be", "youtube.com", "www.youtube.com", "vimeo.com", "www.vimeo.com"}
    return parsed.scheme == "https" and allowed and bool(parsed.path.strip("/"))


def artifact_check(root: Path, spec: ArtifactSpec) -> dict[str, object]:
    path = root / spec.path
    result: dict[str, object] = {
        "path": spec.path.as_posix(),
        "exists": path.is_file(),
        "expected_size": spec.size,
        "expected_sha256": spec.sha256,
    }
    if not path.is_file():
        result["ok"] = False
        return result
    result["size"] = path.stat().st_size
    result["sha256"] = sha256_file(path)
    if spec.dimensions is not None:
        result["expected_dimensions"] = list(spec.dimensions)
        dimensions = png_dimensions(path)
        result["dimensions"] = list(dimensions) if dimensions else None
    result["ok"] = (
        result["size"] == spec.size
        and result["sha256"] == spec.sha256
        and (spec.dimensions is None or result.get("dimensions") == list(spec.dimensions))
    )
    return result


def scan_stale_guides(root: Path) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for relative in ACTIVE_GUIDES:
        path = root / relative
        if not path.is_file():
            matches.append({"path": relative.as_posix(), "pattern": "missing"})
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in STALE_PATTERNS:
            if pattern.lower() in text.lower():
                matches.append({"path": relative.as_posix(), "pattern": pattern})
    return matches


def _git(root: Path, *args: str) -> tuple[int, str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )
    return completed.returncode, completed.stdout.strip()


def git_check(
    root: Path,
    runner: Callable[..., tuple[int, str]] = _git,
) -> dict[str, object]:
    status_code, status = runner(root, "status", "--porcelain")
    head_code, head = runner(root, "rev-parse", "HEAD")
    remote_code, remote = runner(root, "rev-parse", "origin/main")
    valid_hash = re.fullmatch(r"[0-9a-f]{40}", head or "") is not None
    return {
        "status_readable": status_code == 0,
        "clean": status_code == 0 and status == "",
        "head": head if valid_hash else None,
        "origin_main": remote if re.fullmatch(r"[0-9a-f]{40}", remote or "") else None,
        "pushed": head_code == 0 and remote_code == 0 and valid_hash and head == remote,
    }


def build_report(
    root: Path,
    *,
    video_url: str | None,
    architecture_attached: bool,
    builder_id_confirmed: bool,
    rules_accepted: bool,
    git_runner: Callable[..., tuple[int, str]] = _git,
) -> dict[str, object]:
    artifacts = [artifact_check(root, spec) for spec in ARTIFACTS]
    git = git_check(root, git_runner)
    stale = scan_stale_guides(root)
    required_files = {
        name: (root / name).is_file()
        for name in ("README.md", "LICENSE", "devpost-submission.md")
    }
    attestations = {
        "video_url_valid": validate_video_url(video_url),
        "architecture_attached": architecture_attached,
        "builder_id_confirmed": builder_id_confirmed,
        "rules_accepted": rules_accepted,
    }
    blockers: list[str] = []
    blockers.extend(f"artifact mismatch: {item['path']}" for item in artifacts if not item["ok"])
    if not git["clean"]:
        blockers.append("git worktree is not clean")
    if not git["pushed"]:
        blockers.append("HEAD does not equal origin/main")
    blockers.extend(
        f"required file missing: {name}"
        for name, exists in required_files.items()
        if not exists
    )
    blockers.extend(
        f"stale recording reference: {item['path']} ({item['pattern']})" for item in stale
    )
    if not attestations["video_url_valid"]:
        blockers.append("public YouTube or Vimeo demo video URL is missing or invalid")
    if not architecture_attached:
        blockers.append("architecture diagram upload is not attested")
    if not builder_id_confirmed:
        blockers.append("AWS Builder ID field is not attested")
    if not rules_accepted:
        blockers.append("official rules acceptance is not attested")
    return {
        "schema_version": 1,
        "ready": not blockers,
        "artifacts": artifacts,
        "git": git,
        "required_files": required_files,
        "stale_guide_matches": stale,
        "attestations": attestations,
        "blockers": blockers,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail-closed PEX Devpost submission preflight.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--video-url")
    parser.add_argument("--architecture-attached", action="store_true")
    parser.add_argument("--builder-id-confirmed", action="store_true")
    parser.add_argument("--rules-accepted", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(
        args.root.resolve(),
        video_url=args.video_url,
        architecture_attached=args.architecture_attached,
        builder_id_confirmed=args.builder_id_confirmed,
        rules_accepted=args.rules_accepted,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
