from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _powershell() -> str:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        pytest.skip("Windows PowerShell is unavailable")
    return executable


def _run_setup_with_fake_commands(tmp_path: Path, *, fail_stage: str = "") -> dict:
    log_path = tmp_path / "commands.tsv"
    result_path = tmp_path / "result.json"
    caller = tmp_path / "caller"
    caller.mkdir()
    escaped = {
        "install": str(ROOT / "scripts" / "install.ps1").replace("'", "''"),
        "log": str(log_path).replace("'", "''"),
        "result": str(result_path).replace("'", "''"),
        "caller": str(caller).replace("'", "''"),
        "fail": fail_stage.replace("'", "''"),
    }
    wrapper = f"""
$global:PexSetupLog = '{escaped['log']}'
$global:PexSetupFail = '{escaped['fail']}'
function global:Invoke-PexSetupFake {{
    param([string]$Name, [object[]]$PassedArguments)
    $stage = $Name
    if ($Name -eq 'npm' -and $PassedArguments[-1] -eq 'ci') {{ $stage = 'npm-ci' }}
    if ($Name -eq 'npm' -and $PassedArguments[-1] -eq 'prepare:sidecar') {{
        $stage = 'npm-prepare'
    }}
    Add-Content -LiteralPath $global:PexSetupLog -Encoding UTF8 -Value (
        (@($Name) + @($PassedArguments)) -join "`t"
    )
    if ($global:PexSetupFail -eq $stage) {{
        $global:LASTEXITCODE = 37
    }} else {{
        $global:LASTEXITCODE = 0
    }}
}}
function global:git {{ Invoke-PexSetupFake 'git' @($args) }}
function global:uv {{ Invoke-PexSetupFake 'uv' @($args) }}
function global:node {{ Invoke-PexSetupFake 'node' @($args) }}
function global:npm {{ Invoke-PexSetupFake 'npm' @($args) }}
function global:cargo {{ Invoke-PexSetupFake 'cargo' @($args) }}
function global:rustc {{ Invoke-PexSetupFake 'rustc' @($args) }}
Set-Location -LiteralPath '{escaped['caller']}'
$before = (Get-Location).Path
$failure = $null
try {{
    & '{escaped['install']}'
}} catch {{
    $failure = $_.Exception.Message
}}
$after = (Get-Location).Path
@{{ before = $before; after = $after; failure = $failure }} |
    ConvertTo-Json -Compress |
    Set-Content -LiteralPath '{escaped['result']}' -Encoding UTF8
"""

    result = subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-Command", wrapper],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result_path.read_text(encoding="utf-8-sig"))
    receipt["commands"] = [
        line.split("\t")
        for line in log_path.read_text(encoding="utf-8-sig").splitlines()
        if line
    ]
    return receipt


def test_windows_source_setup_is_fail_fast_and_does_not_install_hooks() -> None:
    script = _text("scripts/install.ps1")

    assert "Invoke-NativeCommand \"uv\" @(\"sync\", \"--dev\")" in script
    assert 'Invoke-NativeCommand "npm" @("--prefix", $desktop, "ci")' in script
    assert (
        'Invoke-NativeCommand "npm" '
        '@("--prefix", $desktop, "run", "prepare:sidecar")'
    ) in script
    assert "$LASTEXITCODE -ne 0" in script
    assert '"git", "uv", "node", "npm", "cargo", "rustc"' in script
    assert "integrations/cursor-hook/install.py" not in script
    assert "click Attach" not in script


def test_windows_source_setup_parses_without_running_it() -> None:
    path = str(ROOT / "scripts" / "install.ps1").replace("'", "''")
    command = (
        "$errors=$null; "
        f"[System.Management.Automation.Language.Parser]::ParseFile('{path}', "
        "[ref]$null, [ref]$errors) | Out-Null; "
        "if ($errors.Count -gt 0) { $errors | Out-String | Write-Error; exit 1 }"
    )

    result = subprocess.run(
        [_powershell(), "-NoProfile", "-NonInteractive", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr


def test_windows_source_setup_executes_only_ordered_fake_commands(tmp_path: Path) -> None:
    receipt = _run_setup_with_fake_commands(tmp_path)
    desktop = str(ROOT / "apps" / "desktop")

    assert receipt["failure"] is None
    assert receipt["before"] == receipt["after"] == str(tmp_path / "caller")
    assert receipt["commands"] == [
        ["uv", "sync", "--dev"],
        ["npm", "--prefix", desktop, "ci"],
        ["npm", "--prefix", desktop, "run", "prepare:sidecar"],
    ]


def test_windows_source_setup_stops_and_restores_location_on_failure(tmp_path: Path) -> None:
    receipt = _run_setup_with_fake_commands(tmp_path, fail_stage="npm-ci")
    desktop = str(ROOT / "apps" / "desktop")

    assert "exited with code 37" in receipt["failure"]
    assert receipt["before"] == receipt["after"] == str(tmp_path / "caller")
    assert receipt["commands"] == [
        ["uv", "sync", "--dev"],
        ["npm", "--prefix", desktop, "ci"],
    ]


def test_readme_documents_reproducible_source_setup_and_all_sidecars() -> None:
    readme = _text("README.md")
    prose = " ".join(readme.split())
    package = json.loads(_text("apps/desktop/package.json"))
    tauri = json.loads(_text("apps/desktop/src-tauri/tauri.conf.json"))
    builder = _text("apps/desktop/scripts/build-sidecar.mjs")

    assert "uv sync --dev" in readme
    assert "[`.node-version`](.node-version)" in readme
    assert "[`.python-version`](.python-version)" in readme
    assert "[`rust-toolchain.toml`](rust-toolchain.toml)" in readme
    assert "npm --prefix apps/desktop ci" in readme
    assert "npm --prefix apps/desktop run prepare:sidecar" in readme
    assert "npm --prefix apps/desktop run tauri dev" in readme
    assert package["scripts"]["prepare:sidecar"] == "node scripts/build-sidecar.mjs"
    assert package["scripts"]["tauri"] == "tauri"
    assert tauri["build"]["beforeDevCommand"].startswith("npm run prepare:sidecar")

    sidecars = set(tauri["bundle"]["externalBin"])
    assert sidecars == {
        "binaries/pex-bridge",
        "binaries/pex-cursor-hook",
        "binaries/pex-cursor-observe",
    }
    assert all(sidecar.removeprefix("binaries/") in builder for sidecar in sidecars)
    assert "bridge, Cursor control hook, and Cursor observer" in readme
    assert "not a packaged installer" in prose


def test_readme_uses_real_connection_and_goal_surfaces() -> None:
    readme = _text("README.md")
    prose = " ".join(readme.split())

    assert "opencode serve --port 4096" in readme
    assert 'PEX_OPENCODE_URL="http://127.0.0.1:4096"' in readme
    assert "OPENCODE_SERVER_USERNAME" in readme
    assert "OPENCODE_SERVER_PASSWORD" in readme
    assert 'PEX_CODEX_ATTACH="1"' in readme
    assert "new isolated Codex App Server" in readme
    assert "no generic worker **Attach** button" in readme
    assert "already live vendor session" in prose
    assert "After a genuine vendor session appears" in readme
    assert "used_llm=false" in readme


def test_cursor_hook_install_is_explicit_and_uses_workspace_python() -> None:
    readme = _text("README.md")
    prose = " ".join(readme.split()).lower()
    install = _text("integrations/cursor-hook/install.py")

    assert "uv run python integrations/cursor-hook/install.py" in readme
    assert "separate, explicit opt-in" in readme
    assert "~/.cursor/hooks.json" in readme
    assert "hooks.json.pex-backup" in readme
    assert "observe-only hooks" in readme.lower()
    assert "backup is only the state seen immediately before the most recent" in prose
    assert "do not restore the backup blindly" in prose
    assert "later cursor or user edits" in prose
    assert "remove only the pex command entries" in prose
    assert "not yet an automated uninstall command" in prose
    assert "install_user_hooks(cursor_dir)" in install


def test_readme_does_not_repeat_superseded_supervisor_claims() -> None:
    readme = _text("README.md")

    assert "six request-scoped" not in readme
    assert "public-web tools" not in readme
    assert "observation IDs" in readme
    assert "returned observation proves what the tool returned" in readme.lower()
