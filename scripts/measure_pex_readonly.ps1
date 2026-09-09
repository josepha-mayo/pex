[CmdletBinding()]
param(
    [ValidateRange(1, 60)][int]$Seconds = 30,
    [string]$Executable = (Join-Path $PSScriptRoot '..\apps\desktop\src-tauri\target\release\pex-desktop.exe')
)

$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'pex_process_snapshot.psm1') -Force
$expectedPath = (Resolve-Path -LiteralPath $Executable).Path

function Read-ProcessSnapshot {
    Get-CimInstance Win32_Process | ForEach-Object {
        if ($null -eq $_.CreationDate) { return }
        [pscustomobject]@{
            Id = [int]$_.ProcessId
            ParentId = [int]$_.ParentProcessId
            CreatedTicks = $_.CreationDate.ToUniversalTime().Ticks
            Name = $_.Name
            Path = $_.ExecutablePath
            WorkingSetBytes = [long]$_.WorkingSetSize
            CpuSeconds = ([double]$_.KernelModeTime + [double]$_.UserModeTime) / 10000000
        }
    }
}

$initial = @(Read-ProcessSnapshot)
$roots = @($initial | Where-Object { $_.Path -ieq $expectedPath })
if ($roots.Count -ne 1) {
    throw 'Expected exactly one already-running matching PEX executable; nothing was launched or stopped.'
}
$rootIdentity = $roots[0]
$watch = [System.Diagnostics.Stopwatch]::StartNew()
while ($watch.Elapsed.TotalSeconds -lt $Seconds) {
    $records = @(Read-ProcessSnapshot)
    $owned = @(Select-PexProcessSnapshot -Records $records -RootId $rootIdentity.Id -RootCreatedTicks $rootIdentity.CreatedTicks)
    if ($owned.Count -eq 0) {
        [pscustomobject]@{ event = 'root_instance_gone'; seconds = $watch.Elapsed.TotalSeconds } | ConvertTo-Json -Compress
        break
    }
    # Lifetime counters per process instance, not a misleading sum of deltas
    # across changing PIDs. Shared working-set pages may be counted more than once.
    [pscustomobject]@{
        event = 'sample'
        seconds = [Math]::Round($watch.Elapsed.TotalSeconds, 2)
        read_only = $true
        processes = @($owned | Select-Object Id, ParentId, CreatedTicks, Name, WorkingSetBytes, CpuSeconds)
    } | ConvertTo-Json -Depth 4 -Compress
    Start-Sleep -Milliseconds 1000
}
