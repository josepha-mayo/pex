"""Curate the public offline PEX runtime for the Linux supervisor boundary.

Wheels must match uv.lock hashes. Only PEX source packages and the public
decision process are included; controllers, tasks and evaluators are excluded.
This bundle does not provide live model transport or benchmark eligibility.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
PACKAGES = (
    ("packages/protocol/src/pex_protocol", "pex_protocol"),
    ("services/bridge/src/pex_bridge", "pex_bridge"),
    ("services/supervisor/src/pex_supervisor", "pex_supervisor"),
)


def build_runtime(wheelhouse: Path, destination: Path) -> dict:
    if destination.exists() or destination.is_symlink():
        raise ValueError("runtime destination must be fresh")
    if destination.resolve() != destination.absolute():
        raise ValueError("runtime destination has a linked ancestor")
    wheels = sorted(wheelhouse.glob("*.whl"))
    if not wheels:
        raise ValueError("runtime requires locked dependency wheels")
    lock = (REPO / "uv.lock").read_text(encoding="utf-8")
    wheel_receipts = []
    members: dict[str, tuple[Path, str]] = {}
    total_bytes = 0
    for wheel in wheels:
        if wheel.is_symlink() or not wheel.is_file() or wheel.stat().st_size > 200_000_000:
            raise ValueError("dependency wheel must be a regular file")
        digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
        if f"sha256:{digest}" not in lock:
            raise ValueError(f"dependency wheel does not match uv.lock: {wheel.name}")
        wheel_receipts.append({"file": wheel.name, "sha256": digest})
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.infolist():
                original_name = member.orig_filename
                path = PurePosixPath(original_name)
                if (
                    path.is_absolute() or ".." in path.parts or "\\" in original_name
                    or ":" in original_name
                    or stat.S_ISLNK(member.external_attr >> 16)
                ):
                    raise ValueError("dependency wheel contains an unsafe path")
                if member.is_dir():
                    continue
                if member.filename in members:
                    raise ValueError("dependency wheels overlap")
                total_bytes += member.file_size
                members[member.filename] = (wheel, member.filename)
                if len(members) > 20_000 or total_bytes > 200_000_000:
                    raise ValueError("dependency runtime exceeds its bounds")
    sources = []
    for relative, package in PACKAGES:
        root = REPO / relative
        if root.resolve() != root.absolute():
            raise ValueError("public package source is linked")
        for source in sorted(root.rglob("*")):
            if source.is_symlink():
                raise ValueError("public package source contains a link")
            if source.is_file() and source.suffix in {".py", ".md", ".json"}:
                if "__pycache__" not in source.parts:
                    sources.append((source, Path(package) / source.relative_to(root)))
    source_paths = {target.as_posix() for _, target in sources}
    if source_paths.intersection(members):
        raise ValueError("dependency wheels shadow public PEX source")
    process_source = REPO / "benchmarks/pex_supervisor_process.py"
    if process_source.resolve() != process_source.absolute() or not process_source.is_file():
        raise ValueError("public process source must be a regular unlinked file")
    site = destination / "site-packages"
    site.mkdir(parents=True)
    for relative, (wheel, member) in members.items():
        target = site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(wheel) as archive:
            target.write_bytes(archive.read(member))
    for source, relative in sources:
        target = site / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    shutil.copyfile(
        process_source, destination / "public_process.py",
    )
    (destination / "pex_supervisor_process.py").write_text(
        "import runpy, sys\n"
        "sys.path.insert(0, '/runtime/site-packages')\n"
        "runpy.run_path('/runtime/public_process.py', run_name='__main__')\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "pex.offline-supervisor-runtime.v1",
        "model_transport": "disabled",
        "wheels": wheel_receipts,
        "files": [
            {"path": path.relative_to(destination).as_posix(),
             "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(destination.rglob("*")) if path.is_file()
        ],
    }
    (destination / "runtime-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8",
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wheelhouse", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()
    receipt = build_runtime(arguments.wheelhouse, arguments.destination)
    print(json.dumps({"files": len(receipt["files"]), "wheels": len(receipt["wheels"])}))
