$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot 'pex_process_snapshot.psm1') -Force

function Record([int]$Id, [int]$ParentId, [long]$CreatedTicks) {
    [pscustomobject]@{ Id = $Id; ParentId = $ParentId; CreatedTicks = $CreatedTicks }
}
function Assert-Ids($Records, [string]$Expected, [string]$Label) {
    $actual = @(Select-PexProcessSnapshot -Records $Records -RootId 10 -RootCreatedTicks 100)
    if (($actual.Id -join ',') -ne $Expected) { throw "Failed: $Label" }
}

Assert-Ids @((Record 10 1 100), (Record 20 10 110), (Record 30 20 120)) '10,20,30' 'valid tree'
Assert-Ids @((Record 10 1 100), (Record 20 10 50), (Record 30 20 60)) '10' 'old child of reused root PID'
Assert-Ids @((Record 10 1 100), (Record 20 10 110), (Record 30 20 105)) '10,20' 'old child of reused descendant PID'
Assert-Ids @((Record 10 1 200), (Record 20 10 210)) '' 'root PID reused'
Assert-Ids @((Record 20 10 110)) '' 'root exited'
Assert-Ids @() '' 'empty snapshot'
Assert-Ids @((Record 10 1 100), (Record 20 10 100)) '10' 'ambiguous equal timestamps excluded'
Assert-Ids @((Record 10 20 100), (Record 20 10 110)) '10,20' 'cycle cannot revisit root'

foreach ($name in @('measure_pex_readonly.ps1', 'pex_process_snapshot.psm1')) {
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw "Parse error: $name" }
    $commands = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.CommandAst] }, $true)
    $allowed = @('Import-Module', 'Join-Path', 'Resolve-Path', 'Get-CimInstance', 'ForEach-Object', 'Read-ProcessSnapshot',
        'Where-Object', 'Select-PexProcessSnapshot', 'ConvertTo-Json', 'Select-Object', 'Start-Sleep',
        'Set-StrictMode', 'Sort-Object', 'Export-ModuleMember')
    foreach ($command in $commands) {
        if ($command.GetCommandName() -notin $allowed) { throw "Unexpected command in read-only observer: $($command.GetCommandName())" }
    }
    $methods = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.InvokeMemberExpressionAst] }, $true)
    foreach ($method in $methods) {
        if ($method.Member.Value -notin @('new', 'Add', 'Enqueue', 'Dequeue', 'ContainsKey', 'ToUniversalTime', 'StartNew', 'Round')) {
            throw "Unexpected method in read-only observer: $($method.Member.Value)"
        }
    }
}
'PASS: 8 synthetic identity cases and read-only command allowlist; no app processes inspected, launched or terminated.'
