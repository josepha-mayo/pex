#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "Installing PEX workspace..."
uv sync
python integrations/cursor-hook/install.py

Write-Host ""
Write-Host "Start the local bridge:"
Write-Host "  uv run pex-bridge --no-auth"
Write-Host ""
Write-Host "If OpenCode is already serving:"
Write-Host "  `$env:PEX_OPENCODE_URL='http://127.0.0.1:4096'"
Write-Host "or click Attach in the pet Agents tab after GET /v1/discover finds it."
Write-Host ""
Write-Host "AgentCore image (Docker required, not installed on this machine last check):"
Write-Host "  docker build -f deploy/agentcore/Dockerfile -t pex-supervisor ."
