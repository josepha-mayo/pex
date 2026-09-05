# Known failures

## Dispatch authority repair and remaining races — 5 Sep 2026

The bounded Store repair now rejects changed goal intent, session pause/resume, target cwd ABA and later accepted human input, without cancelling plans on routine discovery refresh. It also prevents stale event plans from restoring an old cwd. See the handoff for regressions and final integration/push receipt. This does not yet fence actual transport reconnects, raw unaccepted input, global pause/resume ABA or changes after a dispatch claim commits. Codex content normalization, active-steer/idle-continue separation and configuration-preserving same-worker delivery remain required. Shared connector/coordinator work is uncommitted and unintegrated; no live supervision claim follows.

## Existing Codex session and current setup limits — 5 Sep 2026

The current Codex stdio adapter starts a separate App Server and reads only its notifications. Stored thread listing/resume is not proof of the user's existing worker stream. Shared subscription/reconciliation, live user-client visibility and a safe concurrent-input fence remain open; see `docs/CODEX_EXISTING_SESSION_AUDIT.md`. Failed attachment recovery, polling-derived false activity and missing worker Attach UI still need repair. Provider credential and catalog routing races now pass bounded local regressions, and default source setup no longer mutates Cursor hooks, but clean-profile/provider/native UI/package proof remains absent.

A development fixture failure exposed an ambient credential in local tool output. Only a MockTransport was used; no external request carried it. Isolation and assertion output are corrected, but historical exposure remains: the user was informed and should rotate the credential if live. Do not store its value or claim rotation without evidence. The unexplained unowned `loop.py` edit continues to change and must remain untouched pending writer identification.

## Exact-evidence/startup checkpoint limits — 5 Sep 2026

Exact bounded main/verifier observations, failed-remote-action suppression, timeout/crash replay preservation and visible serialized startup recovery have local regression coverage (332 backend, 74 frontend checks). They are not live model quality or GUI proof. The frozen `pex-cursor-observe` executable remains absent; Rust's 12-test/Clippy checks required an explicitly disclosed process-local externalBin override. Normal release config/preflight still requires all sidecars and remains unproven. No Windows Job Object/parent watchdog reaps an orphan after desktop crash; an occupied unknown port is safely reported, not killed or adopted. Packaged single-instance, retry, process-crash and clean-profile smoke remain open. First-run provider/worker attachment is not completed by adding a startup error screen. Formal benchmark isolation/network enforcement, live same-session usefulness, all-eight-pet review and final submission evidence remain open.

## Production Cursor delivery boundary — 5 Sep 2026

The queued-message false acceptance has been replaced with distinct prepared, helper-stdout-flushed, and same-session-activity observations. Aborted/error stops cannot dispatch follow-ups. This **does not establish vendor acceptance or causal continuation**: the helper ACK precedes successful process exit/vendor parsing, and missing user-prompt callbacks leave coverage incomplete. `helped` remains unknown; original effects remain delivery-uncertain. First ACKs fail closed on wrong project, nonce, boot, age, or any intervening accepted event. This may conservatively lose a real delivery observation under concurrency/timeout; it must never retry the worker message or invent a receipt. Legacy fake turn IDs are not upgraded into evidence. Real independent same-session Strands quality, benchmark runtime isolation/network policy, six live cells, release/package smoke, and submission proof remain open.

## Production supervision repair — 4 Sep 2026 continuation

Current work closes reproduced prompt-policy bypass, false human-override classification, stale deterministic-plan replacement of semantic decisions, AgentCore failure fallback, and loss of post-inference provenance. Strict independent-verifier receipts are required for remote STOP interventions and retained in the durable audit. Final stable-source verification passed **334 tests**; the handoff records scope and push receipts. Bounded lexical intent triage is not a full semantic parser; ambiguous and quoted conflicts may conservatively ask instead of silently creating durable authority. Cursor response construction/prepared stop delivery is not vendor acceptance proof. Local fake-model tests cannot establish live independent Strands quality, same-session effectiveness, benchmark improvement, or submission readiness.

## Cursor evidence boundary — 4 Sep 2026 continuation

Private nonce-bound observed capture and prompt-release-to-stop timing are now implemented; final verification/push receipts are recorded in the handoff. This does not provide authenticated writers, backend acceptance, full vendor-event coverage, human-action coverage, worker-only duration, or total task duration. Stop-supplied benchmark timing/human logs are ignored. Partial evidence stays diagnostic; the official attempt terminates with an abort. Runtime OS isolation and enforced Cursor network policy remain missing and real benchmark calls remain blocked before dispatch.

## Current safety correction — 4 Sep 2026

- Source commits/pushes are now explicitly authorized; the older matrix's commit restriction is superseded. Other publish/deploy/spend/submission gates remain.
- Cursor local hook receipts are now chronological, namespace-bound, hash-checked, and captured after stdout flush. They do not authenticate shared-host writers or prove vendor acceptance/causal impact. Controller timing/action/raw-log capture remains missing; legacy drops are not upgraded to evidence.
- The permissive execution/report split at `cbd5427` is now corrected in the four-arm driver: real entrypoints and CLI prepare/run/evaluate enforce implementation-owned safety blockers and static leakage checks. The runtime isolation backend itself is still **not implemented**, so live execution remains held regardless of manifest assertions. Evaluator-library subprocesses are not an OS sandbox and must not be used as a bypass. Natural-task provenance and completed raw logs/outcomes remain separate report requirements.

## Contest honesty matrix (3 Sep 2026)

| State | What |
| --- | --- |
| **Verified locally** | Typed `REQUEST_VERIFICATION` beyond pytest; worker-delivery receipts; attached-only completion; untrusted human-decision framing; supervisor DNS answers pinned to a literal IP + SNI before connect (rebinding adversary unit test); Windows token-file owner-only DACL with parent directory handle held; `PEX_TOKEN` scrubbed from process env at sidecar start. |
| **Not yet verified** | Live Codex App Server closed-loop; live Strands two-Agent capture; four-arm freeze (`can_freeze` stays false); packaged installer / sidecar smoke; git-tracked Von spritesheet + `_audit/release/current-20260831` on a clean clone. |
| **Blocked by operator authorization** | Commit; AgentCore deploy; spend; installer package; Devpost submit; freeze; spawning a second `pex-bridge` on `127.0.0.1:7420`. |

- The newest offline gate is recorded in `STATUS.md`. Worker
  delivery is fail-closed: bare adapter `True` is `delivery_uncertain`; Codex still uses
  `pex.worker-delivery.codex-turn.v1`; Synthetic/Qwen/Stop-hook followups use
  `pex.worker-delivery.v1`. Goal completion does not credit STOP evidence from a session that
  is no longer attached to that goal. Human
  decisions, direct messages, handoffs, and goal-control operations now use prospective
  durable actor/idempotency authority appropriate to each effect; worker delivery remains on
  the non-downgradable v3
  exact-turn contracts, frozen-binding first finalization/replay, and fail-closed terminal
  reads. Handoff recovery also requires its exact v2 dispatch/candidate authority before
  mutation. Historical v1 rows remain legacy without backfilled turn IDs. The binding
  missing proof is still real Codex + real Strands same-session observation, decision,
  action, exact-turn outcome, and audit.
- Goal create/update/override and session attachment remain outside the measured human
  total, but authenticated REST now has caller idempotency, non-secret actor assurance,
  semantic intent revisions, and an atomic append-only terminal operation row. Exact replay
  survives restart/stale CAS, concurrent duplicates serialize once, receipt insertion failure
  rolls back the mutation, and typed replay rejects a coherently rehashed response whose
  outcome or goal/session authority contradicts the operation row. Desktop retries retain the
  same key for unchanged create/update/attach intent. Prospective Build Spec §58.2 eligibility
  is now frozen separately for every post-boundary authenticated update/override/attach:
  creates, no-ops, unattached or paused/observe-only edits are excluded; changed attachments
  and attached-live semantic mutations count once; implicit N-session override rebinds never
  multiply the action. Pre-boundary operations remain explicitly unverified without backfill.
  The canonical human-intervention total remains null because out-of-band manual context,
  manual verification, and consented active-human time are still incomplete.
- The prior 1698/21 whole run emitted one aiosqlite worker-thread event-loop-shutdown warning
  under `test_focus_does_not_inject_worker_text`. The exact test passed 1/1 without the
  warning and the full Cursor contract passed 37/37 without it. Treat it as a retained,
  non-reproduced resource-lifecycle warning; the fresh 1707/21 run also completed without
  that warning. Retain the historical receipt and do not make a speculative production
  change without a reproduction.
- The packaged Cursor observer is now a distinct required sidecar and Tauri external bin,
  but it has intentionally not been built. Current v2 sidecar bytes/stamp are stale against
  the v3 three-helper contract, and check-only preflight is NO-GO. Source tests prove helper
  selection and no hook-file mutation on a missing observer; they do not prove PyInstaller
  one-file cold start stays within Cursor's 3-second observe timeout. A package smoke is a
  separate action-time authorization gate.
- Recovery's real Codex milestone is still unproven. Local production-graph tests now bind
  each intervention to an exact returned Codex turn and `pex.codex.closed_loop.v3` rejects
  unrelated-turn outcomes, but neither `PEX_LIVE_CODEX=1` nor
  `PEX_LIVE_SUPERVISOR=1` was authorized/run. Do not present the 1698/21 local gate as a
  live model or live App Server demo. The next valid evidence is two fresh isolated cases:
  evidence-supported NOOP and incomplete→specific same-thread continuation→exact-turn
  observed outcome, with correlated SQLite/JSONL audit and unchanged source/process proof.
- Historical delivered Codex interventions created before exact turn receipts cannot be
  causally attributed. On a later observation they are finalized as
  `worker_delivery_causality_unavailable_legacy`, never backfilled or credited. A malformed
  stored receipt is finalized as corruption rather than blocking the shared Codex pump.
  A bridge crash after vendor acceptance but before the exact receipt is committed remains
  honestly delivery-uncertain; PEX must not resend or infer causality after restart.
- **Not submission-ready.** Companion, inspect loop, and adapters are in progress. Do not treat a local Vite window as a Devpost demo.
- Live bridge on `127.0.0.1:7420` may be an old process. Restart after pulling. Cursor pre-hooks must not freeze the editor.
- Isolated `codex app-server` ≠ ChatGPT.exe private JSON-RPC. A working isolated App Server thread is kept when ChatGPT.exe is also open; idle listed threads still drop if the transport is down.
- This editor’s Cursor hooks are **observe** (`pex_cursor_observe.py`, timeout 3, no failClosed). Control-mode failClosed Delete/Task/destructive-shell gates are opt-in for isolated bench worktrees only. Same-session stop follow-up is not claimed on observe. Observe now extracts `workspace_roots` from huge stdin; a conversation still has no same-session follow-up without ACP or a waiting stop hook.
- Starter `{harness}:desktop` rows cannot attach a goal, cannot `send_message`, and cannot send/receive `POST /v1/sessions/{id}/handoff`. Attach the isolated App Server thread or `cursor:{conversation_id}`, never the inventory tile. Live Cursor→Codex auto-handoff is still unproven.
- Handoff delivery and target evidence remain separate. The former newest-64 passive scan is replaced by an immutable manifest-bound dispatch candidate index; exact self-attested ACK and artifact read/edit evidence remain `verified:false` and `assimilation_proven:false`. Genuine migrated v1 effects without a manifest remain `monitoring_unavailable_legacy`; a prospective v3 effect cannot be rewritten to a v1 watermark, and relevant v2 corruption fails typed evidence closed. REST handoff is now operator-authenticated and broad response/event/audit surfaces use content-free digest/ID receipts; exact bundle detail is limited to the canonical effect, target delivery, one authenticated REST field, and explicit authenticated desktop detail. The canonical v1 bound Intervention still internally duplicates the effect bundle until a versioned migration. A real isolated Cursor↔Codex target-action demo is still unproven and authorization-gated.
- Exactly eight built-in pets are packaged as v2 sheets on this worktree and hash-locked to `release-manifest.json`; they are not gitignored. Von’s spritesheet is still untracked in git HEAD, so a clean clone would miss it until an authorized commit. Custom imports remain separate. Do not treat a local Vite/Tauri window as a Devpost demo.
- Do not cite leaked four-arm numbers under `benchmarks/results/INVALID_LEAKED_RUNS_DO_NOT_USE/`.
- Cursor stop-drop replay cannot prove a same-session PEX continuation. The hook can now record delivered follow-ups and four-arm can wait for a later stop. Isolated STOP verifies claims, treats a still-failing pytest as unfinished work, and lifts labeled TASK.md acceptance lists onto the isolated Goal. Create/patch extract labeled objective lists when those Goal fields are empty; an explicit empty PATCH list is not restored. The inspector can PATCH the attached ledger. Labeled decisions, rejected approaches, and unresolved questions persist as Decision rows and are shown on the inspector; prompt lint treats an active rejected approach as a contradiction. Handoff bundles use those rejected approaches as `do_not_redo` and pick a real next objective instead of canned continue text. Explicit override prompts persist as Decision rows; constraint contradictions still ASK and name the constraint. Accidental-ambiguity prompts continue with a ledger-grounded rewrite (`user_message` while `continue` is true); that is hook-contract evidence, not a live Cursor submit. A downstream eval/train command is redirected only when the required artifact is observed missing. Ask PEX answers spec questions from canonical state without interrupting workers and without letting a loaded supervisor model override those answers. “Did the eval finish?” inspects attached results.jsonl row counts when cwd is present. Freeform Ask with a Strands model uses a read-only inspect review Agent, not decide(). Deleting a ledger-required artifact is held before the command; agent output that contradicts an active constraint is redirected. An observed background job that is still running on STOP is checked against the OS process table (live child process in tests); a pid that has already exited is not woken. That is this-machine process-table evidence, not a live Codex/Cursor worker. Broad unrelated refactors are redirected and the session is marked `drifting` until a later observation (required-file edit, USER_PROMPT, STOP, or ERROR); sending the nudge is not claimed as “corrected.” Compaction checkpoints the attached ledger (synthetic COMPACTION, not a live Cursor `preCompact`). Repeated forgotten facts after compaction are named in that checkpoint; after two such cycles overlay-capable harnesses pin those facts and drop unrelated research tools. Duplicate work across sibling agents on the same goal is redirected from overlapping observed paths or identical non-test commands; that is synthetic two-session evidence, not a live Cursor+Codex pair. Cloud supervisor unavailability preserves local deterministic corrections; that is a fake remote failure, not a live AgentCore drop. A malformed Cursor hook does not stop sibling supervision. Repeated identical failing commands can apply a reversible overlay. After two verifier-backed gap/contradiction STOPs, overlay-capable harnesses can pin a reversible evidence-before-done overlay whose instructions are the specific missing-evidence correction; a first-sample STOP still nudges. Agents fingerprints are counted STOP/overlay aggregates (`supported` vs gap/contradiction); unmeasured token/tool rates stay null rather than invented personality. Context health is scored from observed events; unmeasured token utilization and summary depth stay null. Now reads attention truth from a separate Store snapshot rather than recent intervention cards; incomplete human-action coverage and unconsented active time remain null. Two cheap unresolved questions can propose a human-gated OpenCode/synthetic fork probe; a live `opencode serve` fork was not run. Human-decision waits write `{PEX_HOME}/channels/inbox.jsonl`; Telegram/Discord/WhatsApp/Slack stay disconnected even if env tokens exist. A live messenger delivery was not run. Open agent can open an allowlisted existing Devin URL; a live Devin click and packaged Tauri opener remain unproven. Cursor hook install on this editor is observe-only JSONL; fail-closed Delete/Task and destructive-shell gates are opt-in for isolated bench worktrees. Same-session stop follow-up is not claimed on observe. A disable-pinned premature-stop CLI returns a real non-`PEX:` nudge (`followups >= 1`, `used_llm: false`). Presentation rows still fail closed until a live this-desktop chain with `used_llm` audits exists. Compact is the pet plus live counts; the eight-mascot roster is Settings. Submit remains blocked.
- PexBench retains only the five recovery-spec fixtures. They are not yet the required natural public-repository/SWE-bench task set, and the spec forbids expanding the task list before the live recovery loop passes.
- Current harness capture does not expose complete worker token/cost, active-human-time, vendor raw-log, or source-repo commit evidence. Records and reports keep those measurements null rather than converting missing telemetry to zero.
- Complete immutable vendor raw event logs are not yet retained and rebound at freeze time, so benchmark preflight remains NO-GO even if result-row coverage exists.
- Lifecycle cleanup/restore has a verified immutable pathname authority, quarantine-first
  executor, exact audit, and Undo, but no production component currently creates a valid
  lifecycle resource. `FORK_PROBE`/`START_AGENT` create sessions without isolated owned
  worktrees; PexBench workspaces remain project roots and retained evidence; lexical temp
  dirs and owned transports already self-clean. Do not add a public registrar, path/PID
  heuristic, dummy resource, or relabel a test fixture. Stale processes require a separate
  process-identity ledger. Cleanup-ready IDs are also absent from the production supervisor
  request, so registration by itself would remain operationally dead. Real filesystem
  wiring must wait for an isolated PEX-owned worktree or finalized run-owned sandbox with
  creation and disposability receipts plus a bounded provenance-safe proposal projection.
- Human-attention product metrics now use an exact Store snapshot. Authenticated
  pause/resume and goal update/override/attachment have prospective append-only coverage and
  atomic action/eligibility receipts, but full human-action coverage is still unavailable:
  out-of-band manual context, manual verification, and consented focus intervals lack complete
  append-only receipts.
  Therefore the canonical human-intervention count, human active seconds, unnecessary-alert
  rate, and auto-resolution confidence remain null; only explicitly labeled observed source
  counts and completed reversal receipts are numeric. The live Decisions inbox is authority-
  filtered and exact-counted, with a newest-200 detail page and an explicit truncation flag.
  Product attention metrics are not PexBench evidence.
- Direct worker-message REST mutation now requires the operator bearer even in explicit
  test-only no-auth mode and carries non-secret actor evidence into a prospective,
  append-only reservation plus atomic content-free delivered-action receipt. Validated
  deliveries enter only the observed direct-message lower bound; failed/skipped/uncertain
  outcomes remain separate, and legacy/internal calls remain unverified. Human-requested
  authenticated REST handoffs now use the same prospective actor ledger and atomic bound
  Intervention/audit receipt. MCP, automatic, internal, and legacy handoffs remain
  excluded; delivery is still not assimilation or helpfulness. Goal mutations/attachments
  now contribute only prospective validated eligibility decisions, but out-of-band human
  actions remain incomplete, so the canonical human total stays null.
- Supervisor BYOK/custom routing is locally complete with fake-store, restart, rollback,
  concurrency, hostile endpoint, and non-echoing API tests. It is not provider-live or
  package proof: tests did not write a real OS credential or invoke a paid model, and the
  frozen sidecar was not rebuilt. Consumer login and AgentCore auth remain unimplemented;
  Azure OpenAI and generic SageMaker remain truthfully unavailable. Credential-bearing custom
  clients now disable redirects and environment proxies, reject non-global or mixed DNS
  answers on every request, and rewrite a passing hostname to a literal global IP with the
  original Host header and httpcore `sni_hostname` so a later resolver answer cannot retarget
  the TCP connect. Public scrape URLs with DNS names are resolved the same way and fail closed
  on non-global answers. Residual risk is limited to a cooperating local stub transport that
  ignores the rewritten URL; the production httpx/httpcore path uses the pinned origin.
