# Native acceptance and recovery diagnostic — 10 September 2026

Submission remains NO-GO. User explicitly resumed bounded PEX-only live checks.

## Native package observed

Opened `apps/desktop/src-tauri/target/release/pex-desktop.exe` through Windows
Computer Use. SHA-256 `f3d1d780ebb959c3e8eed18db447c6558dcc5c6f310e8b95fc4fef05819f95f8`
matches the b9702fd package receipt. No unrelated app was closed or restarted.

- Main window opened with a working bridge, not the bridge-failure page.
- Saved Zen setup entered `SupervisorActivationTimeout`. Visible Settings Save
  recovered the same vault-backed `muse-spark-1.3-contributor-free` route at
  `https://opencode.ai/zen/v1`; no key was exposed or replaced.
- Saved review cap changed from unset to three dispatches per session. This is
  not a dollar/token cap and Save itself does not verify inference.
- Selected built-in Von. The native overlay was transparent around the pet:
  underlying window content remained visible, with no white rectangular canvas.
- Status bubble dismissed via its minus control. The independent X control hid
  only the pet window; main PEX and the other returned windows remained open.
- Von remained in place across captures. This is a short observation, not a
  measured animation-speed or long-duration stability guarantee.
- Ten-second read-only process sampling completed. No process was terminated by
  the observer. Samples include multiple WebView processes and both frozen bridge
  processes; do not equate their summed working sets with exclusive RAM.

Screenshots and exact UI tool results are retained in the task conversation.
The connection page still foregrounds a lengthy Codex-specific flow; OpenCode
visible onboarding and full goal-to-outcome UX remain unproven.

## Startup repair

Source 7133696 separates background cold-start activation (60 seconds) from
interactive Save (10 seconds). Startup remains off the event loop and guarded by
configuration generation. All 60 supervisor-settings tests passed in 108.78s,
including hung startup, health responsiveness and the separate budget. Ruff
passed. This mitigation still needs rebuilt-native cold-start validation. The
specific slow operation within the original cold activation was not measured.

## Current-source recovery failure — retained, not scored

Proof root: `build/opencode-recovery-7133696-20260910` (ignored local artifacts).
OpenCode 1.18.29, worker `opencode/ling-3.0-flash-fin-free`, supervisor Zen
`muse-spark-1.3-contributor-free`, three-dispatch cap, default 15-second verifier.
Fresh fixture workspace and isolated OpenCode profile, not an OS security sandbox.

Worker session: `ses_f76d83590ffe5ynTCaa5Vfd6Iv`.
The worker created stage-one.txt (13 exact bytes) and stopped. Main Strands
inference inspected workspace and verification evidence and detected missing
final.txt. The fresh independent verifier also observed the missing artifact,
but timed out at 15,049 ms before returning its structured verdict. Policy
correctly produced NOOP, with no follow-up. Final artifact remained absent.

The diagnostic ended exit 1 with `success:false`, `supervisor_used_llm:true`,
213 retained SSE events and profile cleanup complete. This is a failed controlled
recovery case, not a benchmark score or native desktop integration proof. It must
remain in the evidence alongside later runs; never replace it with a passing run.

## Separate 25-second diagnostic — recovery passed

Proof root: `build/opencode-recovery-7133696-verifier25-20260910`.
Same model IDs and three-dispatch cap; no verification bypass. Session
`ses_f76d1818bffeXG0br1d6c1ZWka` received one SEND_NUDGE from PEX and created
final.txt with the required exact bytes; stage-one.txt also ended with the exact
required bytes. Diagnostic exit 0; 525 retained SSE events; profile cleanup
complete. One further proposed nudge was suppressed by cooldown, not delivered.

There were two semantic reviews, each with main and independent-verifier calls:
8 model calls total, 25,619 recorded input tokens and 3,023 output tokens.
Verifier latencies were 12,923 and 8,009 ms, both under 15 seconds on this run.
Therefore this pass does NOT prove that increasing the deadline alone caused
recovery: provider latency varied. The failed default run establishes that the
old deadline can reject a legitimate proposal. A 25-second default adds headroom
within the existing hard maximum; it does not add retries or model calls.

Receipt hashes:

- Failed run: `e276748a276618708f4248f52392eec64a435ffece65622839329047bef49909`.
- Passed run: `a31c27a66143adab9f807332767b562728fdce62657d7149c02c9b979e1408d3`.

The recovery script independently reads exact file bytes, but this run does not
prove a final quiet supervisor review, comparative performance, or the native
desktop-to-worker integration. No paid model or AWS runtime was invoked.
