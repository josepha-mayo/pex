"""Data-only adapter to preserved paired_smoke.Arm. Never executes candidates.

The protected receipt belongs to the controller, never a worker mount. Directory
permissions are hygiene, NOT execution isolation. Live run gates remain external.
"""

import hashlib
import json
import os
from pathlib import Path
import stat

TASK = "05_uncertain_commit"
FILES = (
    ".gitignore",
    "TASK.md",
    "pyproject.toml",
    "reliable.py",
    "tests/test_smoke.py",
)
PROTECTED = (
    "evaluator/acceptance/test_05_uncertain_commit.py",
    "evaluator/run_tests.py",
    "evaluator/grade.py",
)
MANIFEST_SHA256 = "533c7e055167fe6a86c6ed8fed481605405fab96db45bc7dd60f9705fea3d019"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def read_regular(root, relative):
    path = root / relative
    if root.resolve(strict=True) != root or path.resolve(strict=True) != path:
        raise ValueError("linked source refused")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > 524288
        ):
            raise ValueError("source must be bounded regular unlinked file")
        data = os.read(fd, 524289)
        after = os.fstat(fd)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or len(data) != before.st_size:
            raise ValueError("source changed during read")
        return data
    finally:
        os.close(fd)


def exclusive(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)


def stage(package: Path, destination: Path):
    """Pin existing package; copy only five public files to two independent arms.

    No reference implementation is read/copied. Private acceptance inputs remain
    at the preserved package; only controller receipt holds their pinned hashes.
    """
    package = package.absolute()
    destination = destination.absolute()
    if destination.parent.resolve(strict=True) != destination.parent:
        raise ValueError("destination parent must be unlinked")
    raw = read_regular(package, "MANIFEST.json")
    if digest(raw) != MANIFEST_SHA256:
        raise ValueError("unexpected frozen suite manifest")
    manifest = json.loads(raw)
    public = {}
    for name in FILES:
        relative = f"public/{TASK}/{name}"
        data = read_regular(package, relative)
        if digest(data) != manifest["files"][relative]:
            raise ValueError("frozen public input changed")
        public[name] = data
    prompt = read_regular(package, "INITIAL_PROMPT.txt")
    if digest(prompt) != manifest["files"]["INITIAL_PROMPT.txt"]:
        raise ValueError("initial prompt changed")
    protected = {}
    for relative in PROTECTED:
        data = read_regular(package, relative)
        if digest(data) != manifest["files"][relative]:
            raise ValueError("protected evaluator input changed")
        protected[relative] = digest(data)
    hashes = {name: digest(data) for name, data in public.items()}
    public_hash = digest(encoded(hashes))
    destination.mkdir(mode=0o700, exist_ok=False)
    for condition in ("baseline", "pex"):
        for name, data in public.items():
            exclusive(destination / "workers" / condition / name, data)
    receipt = {
        "schema": "pex.fixed-task-pair-staging.v1",
        "task": TASK,
        "suite_manifest_sha256": MANIFEST_SHA256,
        "public_files": hashes,
        "public_sha256": public_hash,
        "prompt_sha256": digest(prompt),
        "execution_boundary_verified": False,
        "real_inference_calls": 0,
        "quality_measured": False,
    }
    exclusive(destination / "controller" / "staging.json", encoded(receipt))
    exclusive(
        destination / "controller" / "evaluator-inputs.json",
        encoded(
            {
                "schema": "pex.protected-evaluator-inputs.v1",
                "task": TASK,
                "inputs": protected,
                "candidate_execution_permitted": False,
                "requires": [
                    "verified external isolation and expiry",
                    "confirmed worker stop",
                    "immutable candidate hash",
                    "protected evaluator mount",
                ],
                "public_sha256": public_hash,
            }
        ),
    )
    return receipt, prompt.decode("utf-8")


def make_arms(destination, receipt, prompt, worker, arm_type):
    """Construct existing paired_smoke.Arm objects; no budget/default overrides.

    Both arms receive the SAME frozen Worker object and prompt. A turn is an
    autonomous run to a natural stop, not an artificially one-step baseline.
    Supervisor token/time/cost overhead must be recorded separately by runner.
    """
    if (
        receipt["task"] != TASK
        or digest(prompt.encode()) != receipt["prompt_sha256"]
        or set(receipt["public_files"]) != set(FILES)
        or digest(encoded(receipt["public_files"])) != receipt["public_sha256"]
    ):
        raise ValueError("task/prompt identity mismatch")
    for condition in ("baseline", "pex"):
        root = Path(destination).absolute() / "workers" / condition
        for relative, expected in receipt["public_files"].items():
            if digest(read_regular(root, relative)) != expected:
                raise ValueError("staged public bytes changed")
    return tuple(
        arm_type(
            condition,
            Path(destination).absolute() / "workers" / condition,
            receipt["public_sha256"],
            prompt,
            worker,
        )
        for condition in ("baseline", "pex")
    )
