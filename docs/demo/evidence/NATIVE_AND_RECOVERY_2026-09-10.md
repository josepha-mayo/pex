# Native acceptance and recovery diagnostic — 10 September 2026

Submission remains NO-GO. User explicitly resumed bounded PEX-only live checks.

## Native package 2dc5d81: same-session correction and final semantic NOOP observed

Both MSI/NSIS content, hash and eight-pet inventory checks passed, exit 0.
Receipt: `build/pex-package-receipt-2dc5d81.json`.
MSI SHA-256: `cc3e5fb36f0885af4d86d57c06e127615ecd2c9662c775fffa71605456855fa5`.
NSIS SHA-256: `29ac8123a13b6440f6aff774fcac54d06aa9212c9603d4682f89e658a43dfe43`.

Native Computer Use verified cold startup with saved Zen, the OpenCode connection
form, accurate Discovered status before prompting, compact Inspector selection,
selected-worker Ask PEX suggestions, and visible exact goal attachment. Von's
hidden preference remained respected. The desktop bridge was the only supervisor.
No manual correction, abort, second Pipeline, or paid fallback was used.

Synthetic root: `build/native-opencode-2dc5d81-20260910`.
Vendor session: `ses_f7686539affeBwGz2a5flGNYju`.
Worker: `ling-3.0-flash-fin-free`; supervisor:
`muse-spark-1.3-contributor-free`, Strands 1.53.0, local execution.

- Initial worker prompt requested only phase one; attached persistent goal required
  both files. The worker stopped with only stage-one.txt present.
- First semantic proposal failed evidence-reference validation and became NOOP.
  This consumed a review; it is retained as a failed proposal, not hidden.
- Second semantic review and independent verifier inspected missing final.txt.
  PEX delivered one specific SEND_NUDGE. The vendor receipt identifies user turn
  `msg_08983773c001iOihiSLrUsvD5r` in the SAME session; retained assistant messages
  reference that parent and end in a completed stop.
- Both artifacts became exact: stage-one.txt = 13 bytes `stage-one-ok\n`,
  final.txt = 18 bytes `pex-supervised-ok\n`.
- Third semantic review read both files and chose NOOP because their contents
  were correct. This is observed semantic silence after correction, not a
  separate quiet-case benchmark or ten-case false-positive result.
- Three reviews used ten model calls total: 35,389 input / 2,828 output tokens.
  Their recorded latencies were 11,394 / 14,810 / 10,925 ms (second includes its
  independent verifier). These are diagnostic costs, not a comparative claim.
- All 306 accepted events eventually completed. Processing noticeably lagged
  worker execution. The driver stopped its owned server at the predefined
  seven-minute post-first-idle budget; the native bridge drained buffered work
  afterward. Its intervention outcome remained unset (`helped:null`), despite
  external same-parent messages and exact-file evidence. Do not call the full
  product outcome-tracking gate passed.

Scoped local audit: `native-audit.json`, SHA-256
`5d96e5a4da92b1dddbe70a48ab6df7358bd1aac2f2b2aedea24bc6fb7320438c`.
Worker messages: `worker-messages.json`, SHA-256
`b73743c15ef9a4cc885ab0acfa3b515eab280f56607a7e26f934b8de074d636a`.
Only the dedicated session was extracted, not the historical database. Review
before publishing raw diagnostic records. Server/profile cleanup receipt confirms
owned server exit and no remaining temporary profiles. PEX closed normally with
Alt+F4; no unrelated app was closed. Ten-second read-only process sampling was
performed during processing, not an idle resource or stability acceptance test.

### Repairs prompted by this run (not yet packaged)

The deterministic verifier incorrectly interpreted "followed by one newline" as
literal required content, and treated "exactly" as a substring match. Four new
regressions failed before repair. Exact checks now compare the complete UTF-8
content, handle one LF newline, and keep unsupported prose/incomplete reads
uncertain. All 89 verifier tests pass, including invalid UTF-8 and oversized input.

Every OpenCode event also performed process discovery for the optional focus
button. A concurrent twenty-probe regression reproduced twenty discoveries;
the focus-only hint now shares a five-second bounded lookup. HTTP message and
permission authority remain live-probed; fresh scoped snapshots override the hint.
Retained ingestion retries no longer erase intact lineage; transport failures
still mark gaps. Both retry cases failed before that follow-up repair.
Combined verifier/OpenCode/discovery/lineage gate: 248 passed in 13.56 seconds.
Independent Terra review found no code defect and requested downstream gap
coverage. Added direct pump-retry-to-delivery-guard checks: intact retries match,
actual transport failures reject later outcome authority. Full lineage file:
55 passed in 3.52 seconds. AgentCore client/runtime, durable event processing,
and lazy-import gate: 199 passed in 45.44 seconds. Ruff and diff checks pass.

Broad offline run on 2dc5d81: 4,272 passed, 2 failed, 16 skipped, 16 deselected
in 1,262.76 seconds. Failures were the stale Muse chat-only test fixture and a
missing Rust PATH during preflight. Corrected chat fixture plus explicit Rust
toolchain rerun: 3 passed in 39.27 seconds. This is not a clean full-suite rerun
of the subsequent source changes; that remains required.

## Native package 66b5e52: connection passed, recovery failed

Both installers verified; `release_ready:true` describes packaging only.
MSI SHA-256: `9cce0a26e91265e0b3e5277013659cd7e1df13b8eeefc561454bc080efe79148`.
NSIS SHA-256: `1e6bf1198f7eca2ecf363d91aabe2b897f2c9e4edb0a8c48d251f174ddc993c5`.
Receipt: `build/pex-package-receipt-66b5e52.json`.

Observed through PEX-only Windows Computer Use:

- Saved Zen activation succeeded on cold start, without another Settings Save.
- Von remained hidden after relaunch, preserving the earlier close preference.
- Connections accepted the dedicated OpenCode server at loopback port 4097.
- Home showed the real session title and exact workspace.
- Goal editor saved and attached both artifact criteria and evidence paths.
- Review allowance displayed three remaining, zero reserved.
- The Inspector incorrectly expanded dozens of historical session chips, and
  OpenCode discovery incorrectly promoted an idle session to Working.

Diagnostic root: `build/native-opencode-66b5e52-20260910-resumed`.
Vendor session: `ses_f76a75292ffeLuZiBCzdyvkscH`.
Real native bridge was the sole supervisor; the fixture driver did not construct
a separate Pipeline. Worker: Ling 3.0 Flash Fin Free. Saved supervisor: Muse
Spark 1.3 Contributor Free, local Strands route, not a deployed AgentCore runtime.
The worker briefly reported a provider endpoint retry, then completed phase one.
A manual abort returned HTTP 200 while investigating that retry; this is an
experimenter intervention and invalidates a clean autonomous-run claim.

stage-one.txt had its exact 13 bytes; final.txt remained absent. The native
journal retained one complete deterministic event and one accepted event without
advancing to semantic review. All three reviews remained unused. This is a failed
native diagnostic, not a benchmark. The retained journal snapshot is private
local evidence containing historical state; do not publish it wholesale.
An offline copy could claim and finish the accepted row with no model attached.
That narrows investigation but does not establish the original exception.

Two source regressions reproduced independently: discovery invented Working,
and a transient ingest exception replayed the completed batch prefix. The latter
also regenerated event time/lineage metadata, which can defeat durable retry
identity. Repair retains one exact normalized pending event and its bounded
batch's completed-prefix progress. It does not infer raw cursor positions from
filtered event counts. An additional real SQLite acceptance test commits
the second event, raises once, and verifies that all three events finish.
Native rerun is still required; do not call the initial failure fixed solely
from those tests. Discovery now preserves event-owned status/capability state.
Inspector replaces its chip wall with a labeled native select and prioritizes
the selected worker in Ask PEX suggestions.

The first setup attempt was stopped with Escape before any worker prompt; its
server and temporary profile were cleaned. The resumed run's server/profile were
also cleaned, and PEX was closed with normal Alt+F4. No unrelated app was closed.

## Quiet diagnostic: inconclusive, not a NOOP pass

`build/opencode-quiet-66b5e52-20260910` ended at its five-minute diagnostic limit.
Both artifacts were correct and no follow-up was sent, but the last event was
still planning. No completed semantic NOOP was retained (`used_llm:false` in the
terminal receipt). Worker and supervisor need separate observation budgets on
the next run. Retain this result; do not count silence alone as verified NOOP.

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
