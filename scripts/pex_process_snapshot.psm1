Set-StrictMode -Version Latest

function Select-PexProcessSnapshot {
    <# Read-only attribution, never authority to terminate a process. #>
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][object[]]$Records,
        [Parameter(Mandatory)][int]$RootId,
        [Parameter(Mandatory)][long]$RootCreatedTicks
    )
    $root = @($Records | Where-Object {
        $_.Id -eq $RootId -and $_.CreatedTicks -eq $RootCreatedTicks
    })
    if ($root.Count -ne 1) { return }
    $selected = [System.Collections.Generic.Dictionary[int, object]]::new()
    $selected.Add($RootId, $root[0])
    $pending = [System.Collections.Generic.Queue[object]]::new()
    $pending.Enqueue($root[0])
    while ($pending.Count -gt 0) {
        $parent = $pending.Dequeue()
        foreach ($child in $Records) {
            if ($selected.ContainsKey([int]$child.Id)) { continue }
            # Old children retain a numeric parent PID even after that PID is
            # reused. A child cannot predate the current parent instance.
            if ($child.ParentId -ne $parent.Id -or
                $child.CreatedTicks -le $parent.CreatedTicks) { continue }
            $selected.Add([int]$child.Id, $child)
            $pending.Enqueue($child)
        }
    }
    $selected.Values | Sort-Object Id
}

Export-ModuleMember -Function Select-PexProcessSnapshot
