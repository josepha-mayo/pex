# Bounded native startup observation — 9 September 2026

The exact verified `1985caa` release executable was launched for one bounded
30-second idle observation with supervisor inference and automatic Codex/Cursor
attachment disabled. It opened its Home view, remained available for a native
accessibility/screenshot observation, and the diagnostic exited zero. No mouse
or keyboard input was sent. The owned desktop and bridge were absent afterward.

This is not acceptance of clean-profile onboarding, freeze resolution, current
`4a1f0f2` source, pet interactions, or BYOK. The harness incorrectly assumed that
temporary USERPROFILE/PEX_HOME environment values isolate the native profile.
Inspection of `run_bridge_bootstrap` confirms that Tauri resolves the Windows
known-folder home and explicitly supplies its `.pex` database to the bridge.
The UI displayed existing Cursor state and the saved Ledger pet, corroborating
that this was not an empty profile. The historical raw receipt's
`isolated_profile` field is therefore invalid; it is preserved unchanged, not
silently rewritten. The harness now labels this limitation explicitly.

Raw receipt (local, not uploaded):
`C:\Users\JosephMayo\Documents\Codex\pex-native-smoke-runs\1985caa-20260909T194516Z\receipt.json`.

Measured 15 samples over 29.66 seconds: 11–13 descendant processes, maximum
working set 791,728,128 bytes, private bytes 418,889,728, handles 4,811 and
threads 250. None crossed the configured shutdown caps. Summing working sets
can double-count shared pages. The aggregate CPU count is not monotonic when
short-lived subprocesses exit, so it cannot support a precise CPU utilization
claim. The next diagnostic must retain per-process counters to identify the
source of resource use. This run is too short to rule out the reported freeze.

## Follow-up per-process sample

A second bounded run retained 19 samples over 30.13 seconds and exited zero.
Receipt: the sibling run directory `1985caa-20260909T194754Z/receipt.json`.
It explicitly marks `profile_isolation_verified:false`. No app controls were
changed, and no PEX desktop or bridge process remained afterward.

The persistent bridge process accumulated 9.375 CPU-seconds from first to last
sample and peaked at 112.5 MiB working set. Individual persistent WebView
processes accumulated at most 0.969 CPU-seconds each. This points the next
performance investigation at backend work; it is not proof of a freeze cause.
Summed working sets declined from 825,053,184 to 724,946,944 bytes; final private
bytes were 372,174,848. Short-lived tasklist/conhost counters showed PID reuse,
so their deltas must not be trusted. Future harness samples now include process
start-time ticks to distinguish reused PIDs. Neither run proves long-idle safety.

The normal database exists at roughly 118 MiB. The next non-mutating diagnostic
should attribute backend CPU against the existing-profile idle workload and
check whether historical session projection or startup recovery accounts for it,
without deleting that database or claiming an unmeasured animation fix.
