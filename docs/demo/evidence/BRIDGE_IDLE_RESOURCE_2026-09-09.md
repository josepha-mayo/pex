# PEX isolated bridge idle-resource smoke — 9 September 2026

This bounded smoke used the detached clean source that produced the retained installers:
`9966a602be7ed700844979e5fac2e2669cdb8823`.

## Isolation

- Started only `pex_bridge.main`; the native Tauri window and pet overlay remained closed.
- Used a new empty profile at
  `C:\Users\JosephMayo\Documents\Codex\pex-bridge-idle-smoke-9966a60` and port `17421`.
- Set `PEX_SUPERVISOR_DISABLE=1`, `PEX_CLOUD_REASONING=false`, and local supervisor mode.
- Did not read or change the user's retained PEX profile, invoke a model, open a browser,
  start Docker, or contact AWS.

## Measured steady-state window

After startup, one explicit ten-second before/after process sample reported:

```json
{
  "CPUSecondsDelta": 0.0,
  "DurationSeconds": 10,
  "Handles": 207,
  "HandlesDelta": 0,
  "LivenessOk": true,
  "PrivateMiB": 68.72,
  "PrivateMiBDelta": 0.0,
  "Service": "pex-bridge",
  "Threads": 4,
  "ThreadsDelta": 0,
  "WorkingSetMiB": 82.3,
  "WorkingSetMiBDelta": 0.0
}
```

`GET /health/live` returned `200 OK`. Ctrl+C then produced normal application shutdown,
including the StreamableHTTP session manager shutdown, and finished the owned server process.
The explicit smoke files were enumerated and removed; the profile path, port, and process were
all verified absent afterward.

## Claim boundary

This is evidence that the exact-package-source bridge can start on an empty isolated profile,
remain responsive and resource-flat during the measured idle window, and shut down cleanly.
It does not prove native Tauri rendering, overlay animation, click-through, close/reopen,
long-duration stability, or behavior against the user's large retained profile. The reported
whole-PC freeze therefore remains an open native P0 until the separately authorized bounded
native smoke passes.
