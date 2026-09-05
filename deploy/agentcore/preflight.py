"""Truthful, read-only AgentCore deployment preflight.

This script never logs in, creates resources, builds images, or invokes a paid
runtime. It exits zero only when the local deployment prerequisites and an
ARM64 image are already present.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path

PREFERRED_REGION = "eu-north-1"
RUNTIME_MICROVMS = True
RUNTIME_INSTANCES = False
FALLBACK_REGIONS = ("eu-west-1", "eu-central-1")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE = "pex-supervisor:agentcore-arm64"
_RUNTIME_ARN = re.compile(
    r"^arn:aws(?:-[a-z0-9-]+)?:bedrock-agentcore:(?P<region>[a-z0-9-]+):[0-9]{12}:runtime/"
    r"[A-Za-z][A-Za-z0-9_]{0,99}-[A-Za-z0-9]{10}$"
)
_MAX_COMMAND_OUTPUT_BYTES = 64 * 1024
_MAX_IMAGE_CHARS = 256
_IMAGE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,255}$")


def _run(args: list[str], timeout: float = 8.0) -> tuple[int, str]:
    try:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        return 1, type(exc).__name__
    captured = bytearray()
    output_exceeded = threading.Event()

    def drain() -> None:
        assert proc.stdout is not None
        while chunk := proc.stdout.read(4096):
            remaining = _MAX_COMMAND_OUTPUT_BYTES - len(captured)
            if remaining > 0:
                captured.extend(chunk[:remaining])
            if len(chunk) > remaining:
                output_exceeded.set()
                try:
                    proc.kill()
                except OSError:
                    pass
                return

    reader = threading.Thread(target=drain, name="agentcore-preflight-output", daemon=True)
    reader.start()
    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        proc.wait()
        reader.join(timeout=2)
        return 1, "TimeoutExpired"
    reader.join(timeout=2)
    if reader.is_alive() or output_exceeded.is_set():
        try:
            proc.kill()
        except OSError:
            pass
        reader.join(timeout=2)
        return 1, "OutputLimitExceeded"
    return returncode, captured.decode("utf-8", errors="replace")[:2_000]


def _tool_version(command: str, *args: str) -> str | None:
    code, output = _run([command, *args])
    return output.strip().splitlines()[0][:200] if code == 0 and output.strip() else None


def _node_supported(node: str | None) -> tuple[bool, str | None]:
    if not node:
        return False, None
    version = _tool_version(node, "--version")
    match = re.search(r"v?(\d+)", version or "")
    return bool(match and int(match.group(1)) >= 20), version


def _current_agentcore_cli(command: str | None) -> tuple[bool, str | None]:
    """Distinguish the current Node CLI from older tools with the same command."""
    if not command:
        return False, None
    version = _tool_version(command, "--version")
    help_code, help_text = _run([command, "--help"])
    deploy_code, deploy_help = _run([command, "deploy", "--help"])
    commands = {"create", "add", "dev", "deploy", "invoke"}
    current = (
        bool(version)
        and help_code == 0
        and deploy_code == 0
        and all(name in help_text.lower() for name in commands)
        and "--dry-run" in deploy_help.lower()
    )
    return current, version


def _aws_authenticated(aws: str | None) -> bool:
    if not aws:
        return False
    code, _ = _run([aws, "sts", "get-caller-identity", "--output", "json"])
    return code == 0


def _docker_state(docker: str | None, image: str) -> tuple[bool, bool, str | None]:
    if not docker:
        return False, False, None
    engine_code, _ = _run([docker, "version", "--format", "{{.Server.Arch}}"])
    if engine_code != 0:
        return False, False, None
    image_code, architecture = _run(
        [docker, "image", "inspect", image, "--format", "{{.Architecture}}"]
    )
    image_arch = architecture.strip().splitlines()[0][:32] if image_code == 0 else None
    if image_arch and not re.fullmatch(r"[a-z0-9_-]+", image_arch):
        image_arch = None
    return True, image_arch == "arm64", image_arch


def _buildx_arm64(docker: str | None) -> bool:
    if not docker:
        return False
    code, output = _run([docker, "buildx", "inspect"])
    return code == 0 and "linux/arm64" in output.lower()


def _secret_safe_dockerignore() -> bool:
    path = ROOT / ".dockerignore"
    try:
        is_junction = getattr(path, "is_junction", None)
        if (
            path.is_symlink()
            or bool(is_junction and is_junction())
            or not path.is_file()
        ):
            return False
        with path.open("rb") as handle:
            raw = handle.read(64 * 1024 + 1)
        if len(raw) > 64 * 1024:
            return False
        ordered_entries = [
            line.strip()
            for line in raw.decode("utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except (OSError, UnicodeError):
        return False
    negations = {entry for entry in ordered_entries if entry.startswith("!")}
    if negations - {"!.env.example"}:
        return False
    entries = set(ordered_entries)
    return {".git", ".venv", ".env", ".env.*", "*.pem", "*.key"}.issubset(entries)


def check() -> dict:
    aws = shutil.which("aws")
    docker = shutil.which("docker")
    node = shutil.which("node")
    cdk = shutil.which("cdk")
    agentcore = shutil.which("agentcore")
    configured_image = os.environ.get("PEX_AGENTCORE_IMAGE", DEFAULT_IMAGE).strip()
    image_valid = bool(
        configured_image
        and len(configured_image) <= _MAX_IMAGE_CHARS
        and _IMAGE_REFERENCE.fullmatch(configured_image)
        and not any(character.isspace() or ord(character) < 32 for character in configured_image)
    )
    image = configured_image if image_valid else DEFAULT_IMAGE

    node_ok, node_version = _node_supported(node)
    agentcore_current, agentcore_version = _current_agentcore_cli(agentcore)
    aws_ok = _aws_authenticated(aws)
    docker_engine, arm64_image, image_arch = _docker_state(docker, image)
    if not image_valid:
        arm64_image = False
        image_arch = None
    buildx_arm64 = _buildx_arm64(docker)
    dockerignore = _secret_safe_dockerignore()
    runtime_arn = os.environ.get("PEX_AGENTCORE_RUNTIME_ARN", "").strip()
    runtime_arn_configured = bool(runtime_arn)
    runtime_match = _RUNTIME_ARN.fullmatch(runtime_arn)
    runtime_arn_valid = runtime_match is not None
    # Mirror Settings normalization and the bridge's target checks without
    # constructing Settings (which also processes unrelated local secrets).
    raw_region = os.environ.get("PEX_AGENTCORE_REGION", "")
    region = raw_region.strip()
    region_valid = len(raw_region) <= 64 and (
        not region or bool(runtime_match and region == runtime_match.group("region"))
    )
    qualifier = os.environ.get("PEX_AGENTCORE_QUALIFIER", "DEFAULT").strip()
    qualifier_valid = bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", qualifier))

    blockers: list[str] = []
    if not aws:
        blockers.append("AWS CLI is not installed")
    elif not aws_ok:
        blockers.append("AWS credentials are not active; authenticate explicitly before deploy")
    if not node_ok:
        blockers.append("Node.js 20 or newer is required")
    if not agentcore:
        blockers.append("the current @aws/agentcore CLI is not installed")
    elif not agentcore_current:
        blockers.append(
            "the agentcore executable is not the current @aws/agentcore CLI "
            "with deploy --dry-run"
        )
    if not cdk:
        blockers.append("AWS CDK is not installed")
    if not docker:
        blockers.append("Docker is not installed")
    elif not docker_engine:
        blockers.append("Docker engine is not running")
    elif not buildx_arm64:
        blockers.append("the active Docker buildx builder does not advertise linux/arm64")
    if not arm64_image:
        blockers.append(f"{image} is not a locally verified ARM64 image")
    if not image_valid:
        blockers.append("PEX_AGENTCORE_IMAGE is not a bounded Docker image reference")
    if not dockerignore:
        blockers.append(".dockerignore is missing")

    deployable = not blockers
    invocation_blockers = list(blockers)
    if not runtime_arn_configured:
        invocation_blockers.append("PEX_AGENTCORE_RUNTIME_ARN is not configured")
    elif not runtime_arn_valid:
        invocation_blockers.append("PEX_AGENTCORE_RUNTIME_ARN is not a valid Runtime ARN")
    if not region_valid:
        invocation_blockers.append(
            "PEX_AGENTCORE_REGION must fit 64 characters and match the Runtime ARN region"
        )
    if not qualifier_valid:
        invocation_blockers.append(
            "PEX_AGENTCORE_QUALIFIER must be a valid AgentCore endpoint name"
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "preferred_region": PREFERRED_REGION,
        "agentcore_runtime_microvms": RUNTIME_MICROVMS,
        "agentcore_runtime_instances": RUNTIME_INSTANCES,
        "fallback_regions": list(FALLBACK_REGIONS),
        "aws_cli": bool(aws),
        "aws_authenticated": aws_ok,
        "node_version": node_version,
        "agentcore_cli": bool(agentcore),
        "agentcore_cli_current": agentcore_current,
        "agentcore_version": agentcore_version,
        "aws_cdk": bool(cdk),
        "docker": bool(docker),
        "docker_engine": docker_engine,
        "docker_buildx_arm64": buildx_arm64,
        "image": image if image_valid else "<invalid>",
        "image_architecture": image_arch,
        "arm64_image": arm64_image,
        "dockerignore": dockerignore,
        "runtime_arn_configured": runtime_arn_configured,
        "runtime_arn_valid": runtime_arn_valid,
        "runtime_region_valid": region_valid,
        "runtime_qualifier_valid": qualifier_valid,
        "deployable": deployable,
        "invokable": not invocation_blockers,
        "blockers": blockers,
        "invocation_blockers": invocation_blockers,
        "source": (
            "https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/"
            "agentcore-regions.html"
        ),
        "note": (
            "This is a read-only local readiness report. Deployment and paid invocation "
            "still require separate action-time authorization."
        ),
    }


if __name__ == "__main__":
    report = check()
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["deployable"] else 2)
