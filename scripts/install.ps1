#Requires -Version 5.1
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found on PATH. See README.md for Windows prerequisites."
    }
}

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "Command '$FilePath $($ArgumentList -join ' ')' exited with code $LASTEXITCODE."
    }
}

$root = Split-Path -Parent $PSScriptRoot
$desktop = Join-Path $root "apps\desktop"

foreach ($command in @("git", "uv", "node", "npm", "cargo", "rustc")) {
    Assert-Command $command
}

Push-Location $root
try {
    Write-Host "Preparing the PEX source workspace..."
    Write-Host "This default setup does not install or change Cursor hooks."
    Invoke-NativeCommand "uv" @("sync", "--dev")
    Invoke-NativeCommand "npm" @("--prefix", $desktop, "ci")
    Invoke-NativeCommand "npm" @("--prefix", $desktop, "run", "prepare:sidecar")
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "PEX source dependencies and all required desktop sidecars are prepared."
Write-Host "Start the authenticated desktop from the repository root:"
Write-Host "  npm --prefix apps/desktop run tauri dev"
Write-Host ""
Write-Host "Worker attachment, optional hook installation, provider setup, and goal order are"
Write-Host "documented in README.md. This source bootstrap is not a packaged release install."
