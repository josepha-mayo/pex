from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_PATH = ROOT / "deploy" / "agentcore" / "preflight.py"


def _load_preflight():
    spec = importlib.util.spec_from_file_location("pex_agentcore_preflight", PREFLIGHT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tools(name):
    return name


def _ready_run(args, timeout=8.0):
    joined = " ".join(args)
    if "node --version" in joined:
        return 0, "v24.0.0"
    if "sts get-caller-identity" in joined:
        return 0, '{"Account":"not-exposed-by-report"}'
    if "docker version" in joined:
        return 0, "amd64"
    if "docker image inspect" in joined:
        return 0, "arm64"
    if "docker buildx inspect" in joined:
        return 0, "Platforms: linux/amd64, linux/arm64"
    if "agentcore deploy --help" in joined:
        return 0, "Usage: agentcore deploy [options] --dry-run"
    if "agentcore --help" in joined:
        return 0, "Commands: create add dev deploy invoke"
    if "agentcore --version" in joined:
        return 0, "1.2.3"
    return 0, "ok"


def test_preflight_requires_active_credentials_not_just_aws_executable(monkeypatch):
    module = _load_preflight()
    monkeypatch.setattr(module.shutil, "which", _tools)

    def no_credentials(args, timeout=8.0):
        if "sts" in args:
            return 1, "NoCredentials"
        return _ready_run(args, timeout)

    monkeypatch.setattr(module, "_run", no_credentials)
    report = module.check()
    assert report["aws_cli"] is True
    assert report["aws_authenticated"] is False
    assert report["deployable"] is False
    assert any("credentials" in item.lower() for item in report["blockers"])
    assert "not-exposed-by-report" not in str(report)


def test_preflight_reports_ready_only_with_arm64_image_and_full_toolchain(monkeypatch):
    module = _load_preflight()
    monkeypatch.setattr(module.shutil, "which", _tools)
    monkeypatch.setattr(module, "_run", _ready_run)
    runtime_arn = (
        "arn:aws:bedrock-agentcore:eu-north-1:123456789012:"
        "runtime/PexRuntime-ABCDEFGHIJ"
    )
    monkeypatch.setenv("PEX_AGENTCORE_RUNTIME_ARN", runtime_arn)
    report = module.check()
    assert report["deployable"] is True
    assert report["invokable"] is True
    assert report["image_architecture"] == "arm64"
    assert report["docker_buildx_arm64"] is True
    assert report["agentcore_cli_current"] is True
    assert report["agentcore_version"] == "1.2.3"
    assert report["blockers"] == []
    assert runtime_arn not in str(report)


def test_deploy_context_and_dockerfile_are_secret_safe_and_arm64():
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    dockerfile = (ROOT / "deploy" / "agentcore" / "Dockerfile").read_text(
        encoding="utf-8"
    )
    requirements = (ROOT / "deploy" / "agentcore" / "requirements.lock").read_text(
        encoding="utf-8"
    )
    assert ".env" in dockerignore
    assert ".git" in dockerignore
    assert ".venv" in dockerignore
    assert "ARG TARGETARCH" in dockerfile
    assert 'test "${TARGETARCH}" = "arm64"' in dockerfile
    assert "--require-hashes" in dockerfile
    assert "USER 10001" in dockerfile
    assert "PEX_SUPERVISOR_WALL_TIMEOUT=20" in dockerfile
    assert "bedrock-agentcore==" in requirements
    assert "strands-agents==" in requirements
    assert not (ROOT / "services" / "supervisor" / "Dockerfile").exists()


def test_node_version_gate():
    module = _load_preflight()
    original = module._tool_version
    try:
        module._tool_version = lambda *_args: "v19.9.0"
        assert module._node_supported("node") == (False, "v19.9.0")
        module._tool_version = lambda *_args: "v20.0.0"
        assert module._node_supported("node") == (True, "v20.0.0")
    finally:
        module._tool_version = original


def test_legacy_agentcore_executable_does_not_pass_current_cli_gate(monkeypatch):
    module = _load_preflight()
    monkeypatch.setattr(module.shutil, "which", _tools)

    def legacy_run(args, timeout=8.0):
        if "agentcore --version" in " ".join(args):
            return 0, "0.1.0"
        if "agentcore --help" in " ".join(args):
            return 0, "configure launch deploy invoke"
        if "agentcore deploy --help" in " ".join(args):
            return 0, "--name --region"
        return _ready_run(args, timeout)

    monkeypatch.setattr(module, "_run", legacy_run)
    report = module.check()
    assert report["agentcore_cli"] is True
    assert report["agentcore_cli_current"] is False
    assert report["deployable"] is False
    assert any("deploy --dry-run" in item for item in report["blockers"])


def test_invalid_runtime_arn_never_becomes_invokable(monkeypatch):
    module = _load_preflight()
    monkeypatch.setattr(module.shutil, "which", _tools)
    monkeypatch.setattr(module, "_run", _ready_run)
    monkeypatch.setenv("PEX_AGENTCORE_RUNTIME_ARN", "configured-but-invalid")

    report = module.check()

    assert report["deployable"] is True
    assert report["runtime_arn_configured"] is True
    assert report["runtime_arn_valid"] is False
    assert report["invokable"] is False
    assert any("valid Runtime ARN" in item for item in report["invocation_blockers"])
    assert "configured-but-invalid" not in str(report)


def test_dockerignore_cannot_reinclude_secret_patterns(tmp_path, monkeypatch):
    module = _load_preflight()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    required = ".git\n.venv\n.env\n.env.*\n*.pem\n*.key\n"
    (tmp_path / ".dockerignore").write_text(
        required + "!.env\n",
        encoding="utf-8",
    )

    assert module._secret_safe_dockerignore() is False

    (tmp_path / ".dockerignore").write_text(
        required + "!.env.example\n",
        encoding="utf-8",
    )
    assert module._secret_safe_dockerignore() is True
