# PEX continuation checkpoint — 6 September 2026

The user's internal shipping target is now **9 September 2026, Africa/Lagos**.
The full three-spec objective remains active. Submission remains **NO-GO**.
This checkpoint supersedes older `current` / `final` claims in the rolling handoff,
STATUS, shipping checklist and submission draft.

## Source and package boundaries

- `43690b8e728f8c69d3b4cdad7939f724ee7adb3f` was pushed and verified against remote
  main. It pins all five frozen public benchmark prompts to LF through `.gitattributes`.
  A new Windows checkout confirmed `i/lf w/lf attr/text eol=lf` for all five prompts.
  The exact-byte regression and original failing test passed; full PexBench passed
  **129 tests** under strict resource/unraisable-warning settings in the main checkout.
- `44fa68b` changes supervisor configuration wording. Constructing a Strands client
  does not prove connection or inference. Credentials may be in the OS vault or
  environment; the previous blanket `.env` claim was incorrect. Provider tests:
  **76 passed**; desktop view-model tests: **62 passed**.
- Current source also repairs Companion settings overflow and checkbox sizing after
  reproducing both in the native app at its normal 920-by-730 window size. The roster
  wraps within its grid area; narrow windows use one settings column. The production
  frontend build and **184 desktop tests** pass. The test run emitted an HMR-port
  warning (`24678` in use), despite all assertions passing. Rendered verification of
  the changed layout is still required.
- The latest retained package receipt is for **`4f8b567`**, not current source.
  Local receipt: `C:\Users\JosephMayo\Projects\pex-release-final-8b\build\pex-package-receipt.json`.
  It reports `release_ready: true`, `blockers: []` for package integrity only.
  MSI SHA-256: `5a725c81bc9a89cf4b1f3285477d80a765a3adeedfdee49d173cbc92c5b49994`.
  NSIS SHA-256: `f133ad58e495bd0ef27195da7b40155f7d11090d6ebbc3caa79aaea460b70c8c`.
  A new final package must incorporate subsequent source changes.

## Full-suite diagnosis

The earlier clean `4f8b567` run failed 16 PexBench tests because Git materialized the
public prompts as CRLF, while text-mode workspace reads normalized LF. This was a
checkout portability defect, not test-order contamination. Keep exact byte/hash checks;
do not normalize only one reader and create mutually inconsistent fingerprints.

The fresh `43690b8` checkout is
`C:\Users\JosephMayo\Projects\pex-release-final-9c`. Its full strict suite was
interrupted after **225 passed, 16 skipped**, while the 65-handoff capacity case appeared
stalled. Independent evidence subsequently showed continued durable handoff progress
and an isolated **PASS in 266.58 seconds**. Therefore a deadlock is not established.
The isolated capacity case passed again under `cProfile` in **281.67 seconds**.
Profiling found roughly **16,046 SQLite connections**: its helper created 65 attached
source siblings, so each new event exercised expanding sibling and automatic-handoff
scans before the intended indexed delivery. The capacity fixture is now narrowed to
one attached source and 65 real, distinct REST handoffs so it still proves the exact
beyond-64 contract without accidentally benchmarking an expanding sibling-scan topology.
The corrected case passed in **116.50 seconds**; two adjacent index/ownership cases
passed in **10.27 seconds**. Independent review approved the unchanged beyond-64
authority, oldest-delivery acknowledgement and artifact-evidence assertions. This is
a fixture-runtime improvement, not a measured production speedup.
This does **not** dismiss the separate production scalability concern: large attached
fleets still cause repeated authority-bound session, recent-event and intervention
reads, and that all-pairs path needs its own bounded performance work and evidence.
A diagnostic run with `faulthandler_timeout=45` emitted a Windows access violation;
do not report that diagnostic as a passing run or silently attribute it to PEX code.
There is still **no completed green full-suite receipt for the latest source**.

## Fresh live supervisor result and current repair

The clean checkout `C:\Users\JosephMayo\Projects\pex-live-final-f53`, source
`f53c13b187421448b3fc26e3b82c2ef0571f34ea`, ran real Codex and Strands with the exact
Zen model `muse-spark-1.3-contributor-free`. Its restraint case passed in **139.97s**:
one worker turn, one real supervisor call, artifact-supported acceptance and `NOOP`.
Raw restraint receipt SHA-256:
`283334E846A7F01273DF5AE3DAE00D0C823F4D4A4EC715F0855DB12A7A002D9E`.

The fresh recovery case **FAILED in 219.53s**. It produced one initial STOP decision,
not zero: the main model proposed a correction, but the independent verifier spent
all three model calls on evidence reads and returned no typed verdict. Its status
was `missing_structured_output`; PEX correctly failed closed to `NOOP`, and no second
worker turn occurred. The test's old `no initial STOP intervention` assertion was
misleading because it assigned the first decision only after seeing two. Do not
describe this source as a freshly validated live pair. The earlier `5c49c10` pair
remains historical evidence only. The failed case's temporary SQLite was inspected
before pytest's normal retention removed it; future live runs must use a unique
explicit `--basetemp` under ignored scratch so failures remain inspectable.

A bounded free-provider diagnostic confirmed Muse rejects `tool_choice=required`
with HTTP 400 and explicitly supports only `auto`. Do not change the adapter to
required or claim its compatibility mapping caused this failed run. The reviewed
repair instead gives the verifier generic budget guidance: gather sufficient
independent evidence efficiently, reserve a call for its typed verdict, and reject
when evidence is insufficient. Runtime limits and evidence/permission gates are
unchanged. The strict Strands-runtime unit gate passed **47 tests**, including
one/two evidence-call approval controls and three-call exhaustion failing closed.
This supports the safety boundary; only another real run can verify model behavior.

Independent review also found the reusable proof omitted the verifier receipt and
the requested worker model. Strengthening that proof contract is in progress;
aggregate model-call counts alone do not prove a separate verifier. Requested model
configuration must not be mislabeled as authoritative executed-model identity.

## Native interaction evidence

Computer Use became available with the refreshed plugin on this continuation.
The exact extracted `4f8b567` desktop was launched from
`build\native-smoke-4f8-01\pex-desktop.exe`, using the retained isolated
`build\native-profile-4f8-01` via `PEX_HOME`. It reached **All quiet**.

Observed through the native accessibility tree and screenshots:

- The separate pet window showed Pex and its status bubble.
- Clicking **Dismiss PEX status message** removed the bubble and retained the pet and
  accessible status label.
- **Alt+F4** removed the pet window while the main PEX window remained open.
- Companion settings exposed all eight named built-ins, but the old package layout
  overflowed horizontally and rendered oversized visibility checkboxes.
- Supervisor settings eventually loaded. Their old `Semantic model is loaded` and
  `.env` wording triggered the truthfulness repair above.

The user pressed physical Escape during the next UI refresh. Computer Use stopped
immediately. **Settings restoration, restart persistence, final all-eight animation
replay and rendered validation of the new layout remain incomplete.** Resume app input
only when the user directs it. Do not bypass the stop through another UI tool.
The current app/process/window IDs are ephemeral; rediscover them before reuse.

## Remaining execution order

1. Finish profiling the 65-handoff cost; fix any demonstrated production bottleneck,
   independently review it, then complete the necessary full-suite gate.
2. Visually validate the settings repair and complete native close/restore/restart and
   all-eight-pet checks when app interaction resumes.
3. Recapture the real Codex + Strands restraint/recovery pair on the final runtime,
   including independent verifier evidence where required and ten quiet tasks.
   The retained live pair proves only source `5c49c10`; see the curated live receipt.
4. Complete required cross-harness behavior, honest isolated comparisons, AgentCore
   deployment under the user's no-card-charge condition, and the final audited package.
5. Record the real public demo video and finish the truthful submission artifacts.
   PexBench remains unfrozen; no leaderboard rank or measured productivity lift exists.

Use bounded subagents and independent review. New subagents use GPT-5.6 Sol low.
Push reviewed scoped updates, verify remote equality, and preserve the complete product
goal rather than redefining readiness around tests or packaging.

Protected operator-owned file: `services/supervisor/src/pex_supervisor/loop.py`.
Do not edit, stage, restore, format or clean it. Its rechecked SHA-256 remains
`392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`.
No cloud deployment, paid call, public post or submission occurred in this continuation.
