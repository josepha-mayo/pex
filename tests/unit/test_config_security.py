from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pex_bridge.config import Settings, normalize_loopback_host
from pydantic import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.10", "example.test"])
def test_bridge_rejects_non_loopback_bind_hosts(host: str) -> None:
    with pytest.raises(ValueError, match="loopback"):
        normalize_loopback_host(host)
    with pytest.raises(ValidationError, match="loopback"):
        Settings(host=host)


@pytest.mark.parametrize(
    ("host", "expected"),
    [("localhost", "localhost"), ("127.0.0.1", "127.0.0.1"), ("::1", "::1")],
)
def test_bridge_accepts_only_local_bind_hosts(host: str, expected: str) -> None:
    assert normalize_loopback_host(host) == expected
    assert Settings(host=host).host == expected


def test_bridge_settings_bound_control_plane_values() -> None:
    with pytest.raises(ValidationError):
        Settings(port=0)
    with pytest.raises(ValidationError):
        Settings(token="x" * 513)
    with pytest.raises(ValidationError, match="32-512 printable ASCII"):
        Settings(token="guessable")
    with pytest.raises(ValidationError):
        Settings(max_recent_events=501)
    with pytest.raises(ValidationError):
        Settings(autonomy="invented")


def test_unauthenticated_settings_require_the_explicit_test_constructor(monkeypatch) -> None:
    with pytest.raises(ValidationError, match="Settings.for_test"):
        Settings(require_auth=False)

    test_settings = Settings.for_test(require_auth=False)
    assert test_settings.require_auth is False

    monkeypatch.setenv("PEX_REQUIRE_AUTH", "false")
    with pytest.raises(ValidationError, match="Settings.for_test"):
        Settings()


def test_settings_repr_never_contains_operator_token() -> None:
    operator = "repr-redaction-operator-token-that-is-long-enough"
    settings = Settings(token=operator)
    assert settings.token == operator
    assert operator not in repr(settings)
    assert "token" not in settings.model_dump()


@pytest.mark.parametrize("environment_name", ["PEX_TOKEN", "pex_token"])
def test_settings_consumes_operator_token_environment_case_insensitively(
    monkeypatch,
    environment_name: str,
) -> None:
    operator = "environment-operator-token-that-is-long-enough"
    monkeypatch.setenv(environment_name, operator)
    settings = Settings()

    assert settings.token == operator
    assert all(name.casefold() != "pex_token" for name in os.environ)


def test_release_cli_rejects_no_auth_environment_before_server_start() -> None:
    environment = os.environ.copy()
    environment["PEX_REQUIRE_AUTH"] = "false"
    completed = subprocess.run(
        [sys.executable, "-m", "pex_bridge", "--port", "0"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=environment,
    )

    assert completed.returncode != 0
    assert "unauthenticated bridge settings are available only through" in completed.stderr
    assert "Uvicorn running" not in completed.stderr


def test_asgi_import_rejects_no_auth_environment() -> None:
    environment = os.environ.copy()
    environment["PEX_REQUIRE_AUTH"] = "false"
    completed = subprocess.run(
        [sys.executable, "-c", "import pex_bridge.app"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        env=environment,
    )

    assert completed.returncode != 0
    assert "unauthenticated bridge settings are available only through" in completed.stderr


def test_opencode_plugin_has_no_machine_specific_debug_sink() -> None:
    source = (
        _REPO_ROOT / "integrations" / "opencode-plugin" / "pex-plugin.js"
    ).read_text(encoding="utf-8")

    assert "JosephMayo" not in source
    assert "benchmarks\\\\results\\\\_scratch" not in source
    assert "node:fs" not in source
    assert "appendFile" not in source
    assert "writeFile" not in source
    assert "createWriteStream" not in source
