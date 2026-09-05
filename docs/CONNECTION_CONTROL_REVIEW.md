# Existing-worker connection and internal text control — 5 September 2026

**Goal ACTIVE; release NO-GO; user target 6 September WAT remains at risk.** Source checkpoints, both pushed with exact remote main equality verified at push:

- Desktop connection: `cd399133eddd7384994a7bc7f917b4d1871ef43e`.
- Internal text transport / shared close ownership: `03045b58957414935b54840f15f0a0a98c492a79`.

These make the connection usable in source and supply a tested same-thread write primitive. They do **not** prove installed-worker compatibility, enable generic shared control or complete Recovery's supervisor loop. All three binding specs were reread; optional pet/dashboard expansion was not pursued.

## Desktop implementation and independent review

`SharedConnectionPanel.tsx` is mounted first in Settings through an explicit `workerConnection` slot. Its stable request callback uses the existing native `bridgeToken` acquisition, but the new `operatorRequest.ts` makes exactly one fetch attempt, even for HTTP 401. Credential acquisition failure sends nothing; redirects and foreign routes are refused; responses are not cached. No bearer is stored in web storage or copied to a worker. Tokenless browser development cannot bypass the operator-authenticated backend.

`sharedConnection.ts` owns a testable controller with synchronous duplicate-call blocking, 75-second abort/race timeout, monotonic inspection expiry, four-pending-selection bound, StrictMode-safe activation generations, stale-result suppression and unchanged drafts across reload. Origin setup requires explicit exact labels and revision/choice-ID CAS; copied-installation rebind requires separate consent. Unsafe JavaScript revisions and corrupt/unavailable origin state fail closed. Target edits, including away/back changes, invalidate the reviewed selection. Pending IDs from a reload cannot fabricate the missing full inspection review.

The panel shows exact PEX/vendor identity, supplied and canonical folders, model (including valid unknown/null), and expandable workspace evidence. Confirmation requires the exact selected pair and explicit subscription consent. It validates the returned subscription target/authorization and full canonical workspace receipt before saying confirmed. Known successful confirm/detach performs one GET for current status; failed/unknown mutations require manual reload, never mutation retry. Disconnect still permits exact owned detach. Labels say observe-only and connection **at last refresh**, not continuous live supervision. The original worker is not stopped by detach.

`attachment_review` implemented the controller/panel/tests; `legacy_attach_fence` independently checked the real backend wire contract, request/mount and full new controller/panel/tests. Main reviewed these new files plus changed App/Settings paths, added the one-attempt request helper and browser fixture, and integrated/tested the result. App and Settings received changed-path review, not blanket whole-file approval. React skill guidance influenced event-only mutations, stable subscriptions, lifecycle cleanup and accessible form semantics.

### Findings repaired before acceptance

- Valid Codex inspection can have `model: null`; it must render Unknown, not reject a real thread.
- Independent reproduction accepted a matching top-level session with a wrong subscription selection/workspace as confirmed. Full subscription and canonical workspace checks now reject this; negatives cover authorization, selection, session/thread/root/project/cwd, flags, schema, counters, locator and physical receipt changes. Equivalent JSON key reordering remains valid.
- Browser accessibility scan flagged named generic divs. They now have group roles. Snapshot wording explicitly identifies last-refresh state.
- Early browser attempts while HMR was changing the controller lost their reviewed selection; a stale element reference could not confirm. Those are not a passing stable-tree run. The final successful flow below was rerun after the source freeze.

## Verification ledger: desktop and API

- Main focused controller/request: 55 passed at the intermediate receipt-fix checkpoint.
- Final owner: **57 passed in 212.7375ms** (49 controller + 8 request); independent reviewer **57 passed in 219.5ms**. These overlap the full test command.
- Main `npm test` from `apps/desktop`: **154 passed, 0 failed, 0 skipped in 337.4539ms**. Separate `tsc --noEmit` exit 0. Final three JSX accessibility/snapshot-label edits were independently approved afterward and included in the successful production frontend build.
- Main `npm run build`: TypeScript passed, Vite 6.4.3 transformed 58 modules and built successfully in 1.22s. This is a frontend build only, **not** normal Tauri/sidecar packaging or clean-profile startup.
- Actual backend routes with temporary Store/config and fake vendor transport: **42 passed in 21.56s** across `test_workspace_attachment.py`, `test_workspace_attachment_review.py`, `test_codex_shared_attach.py`. This is separate-layer API evidence, not a native browser-to-worker end-to-end run.
- Whitespace checks passed for all ten staged desktop source/test/fixture paths.

### Rendered test, explicitly not live supervision

Browser skills were used with agent-browser 0.36.0, a task-owned isolated browser session and Vite at `http://127.0.0.1:1425/tests/connection-qa.html`. `tests/connection-qa.tsx` mounts the **real panel** with a labeled in-memory fake API; it performs no fetch/native/provider calls and is not a normal production build entry. It must never be used as a live-product demo or benchmark.

Observed browser flow: initial disabled submit → exact origin fields and checkbox → one PATCH → exact socket/thread/project/cwd → inspect only → explicit confirmation → automatic status GET → Observing only. A fake disconnect plus reload showed Disconnected with detach available. Injecting a lost detach response left a warning and disabled further mutation; reload showed no active connection. Captured mutation count stayed **one detach** before and after recovery. No Vite error overlay or browser page error was observed. The final accessibility scan had zero reported violations, but gradient contrast remained an **incomplete/manual check**; this is not WCAG certification or final UX approval.

Local screenshots inspected by main:

- `C:/Users/JosephMayo/.agent-browser/tmp/screenshots/screenshot-1788620472314.png` — initial form.
- `C:/Users/JosephMayo/.agent-browser/tmp/screenshots/screenshot-1788621235693.png` — lost-response recovery, disabled detach and last-known connection.

Screenshots are local evidence, not committed release assets. The task-owned browser was closed and Vite process explicitly stopped after verification. No user's browser or running worker was restarted.

## Internal same-thread text dispatch

The transport's dedicated `_dispatch_text` supports idle `turn/start` and active `turn/steer`; **there is no production caller yet**. Generic `request()` still rejects mutations, `shared_observe_only=True`, and UI/API capability labels stay observe-only. This checkpoint is a prerequisite, not a claim that sending now works through the supervisor.

The caller must supply exact thread, endpoint/generation, observed complete-envelope revision, bounded nonempty text, correlation ID, expected active turn (or explicitly choose start), and a synchronous final local-authority callback. The callback and epoch/revision checks run under write serialization immediately before enqueue, without initialization/reconnect or configuration overrides. Decoded complete envelopes advance the local revision and route before releasing the protocol lock or awaiting a flush. This revision includes responses/server requests, not just normalized lifecycle events; it is still **not a global/server input revision**.

Strict acknowledgements return an immutable receipt. Pre-enqueue refusal differs from post-enqueue cancellation/timeout/malformed response. A matching vendor JSON-RPC error retains only a sanitized code and `returned_error` classification but remains delivery-uncertain: an internal error does not prove no side effect. No error switches start/steer or resends. `clientUserMessageId` is correlation, not documented vendor idempotency.

Self-review reproduced a concurrent-read cleanup failure: one caller detached the channel while dispatch's own close returned early. Shared transport close now captures and retains one cleanup task; concurrent callers settle it through repeated cancellation, join reader-owned EOF cleanup and block reopening until cleanup settles. Revocation precedes waits. Failed cleanup does not become proof of successful termination.

`transport_review` owned these two paths and reproduced the cleanup failure; main read the changed production paths and entire new regression file. Independent reviewers checked the wire behavior and classification; final independent gate from `attachment_review` was **183 passed in 4.27s**, scoped Ruff clean. `legacy_attach_fence` additionally reproduced the raw-retention activation blocker below before its review turn hit model capacity; its interrupted review is not counted as final approval.

### Transport gates and scope

- Initial gate 173 passed, then concurrent-read cleanup reproduction **1 failed in 0.88s**; the earlier green gate was not acceptance.
- After consolidation, one test initially cancelled a second close task before that task entered; the test now waits for entry before testing shared ownership. No production semantics were weakened.
- Final owner: **183 passed in 4.16s**, covering new framed-dispatch plus complete transport/subscription/subscription-close files. Independent reviewer result above overlaps it.
- Main final integration: **406 passed in 70.85s across 18 complete files**; scoped Ruff and staged whitespace passed for both changed paths. Exact command from repo root:

```powershell
.venv/Scripts/python.exe -m pytest tests/unit/test_codex_shared_transport.py tests/unit/test_codex_shared_text_dispatch.py tests/unit/test_codex_subscription.py tests/unit/test_codex_subscription_close_ownership.py tests/unit/test_codex_shared_attach.py tests/unit/test_codex_shared_adapter.py tests/unit/test_observer_session_publication.py tests/unit/test_observer_lifecycle_pipeline.py tests/unit/test_codex_attach_serialization.py tests/unit/test_codex_pipeline_pump.py tests/unit/test_existing_sessions.py tests/unit/test_generic_dispatch_authority.py tests/unit/test_codex_shared_status_pipeline.py tests/unit/test_codex_partial_intent.py tests/unit/test_codex_observation_retention.py tests/unit/test_observer_retention_store.py tests/unit/test_codex_reconciliation_retention.py tests/unit/test_workspace_continuity_pipeline.py -q -ra --tb=short
```

All backend tests used temporary state/fake byte channels, no native worker/model. The excluded unowned supervisor `loop.py` still has 28 inserted lines, SHA256 `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`; preserve it and disclose the dirty-checkout limitation. Overlapping test totals must not be summed.

## Next critical path and activation gates

1. **Durable received-envelope journal before filtering/clearing.** Independent framed reproduction: with a text acknowledgement withheld, a received human notification existed (count 1) before timeout, then close cleared it (count 0). Preserve received observations durably under exact attachment/epoch provenance, including failure/recovery; journal failure must disable new control. Do not resurrect old-epoch notifications as live authority. This is received-stream coverage, not proof of events lost before receipt or emitted before attachment.
2. **Coordinator/adapter reconciliation.** Fresh same-thread read with `includeTurns`, positive `canAcceptDirectInput`, validated identity/workspace and current input/turn. Existing local `active_turn_id` and `input_revision` are insufficient: initialization can be unknown and a stale completion can clear the field. Track/correlate PEX-originated input so its corrective text cannot silently become new human intent.
3. **Durable goal/policy/effect integration.** Bind the selected action to current persistent goal, accepted trigger, intent/control revision, subscription, workspace and freshest received state. Persist before write; record acknowledged/returned-error/unknown outcomes and never reissue uncertain effects. Goal-scoped autonomy, not one human confirmation per correction. Then wire `_dispatch_text` through the real executor and truthful capability negotiation.
4. **Installed same-worker loop.** Preserve protected executable/endpoint checks; obtain applicable runtime/provider authority and prove real Strands NOOP and evidence-grounded correction with independently observed same-worker outcome, followed by ten quiet cases. Minimum source UI and framed wire tests do not prove this.

Official OpenAI documentation was checked using OpenAI Docs: [App Server turn semantics](https://learn.chatgpt.com/docs/app-server). Previously generated local schema source was also read at `C:/Users/JosephMayo/AppData/Local/Temp/pex-codex-ts-9d21ed590a4d4ceab9a021615792d3f5/v2/`; it is not fresh installed-runtime provenance. Steering checks the active turn ID, not newer input within that turn; start exposes no equivalent idle/input compare-and-swap. Another client can act after PEX's last check. Enforce measured freshness and post-action observation, disclose the residual race, and do not turn an impossible perfect cross-client lock into endless scaffolding or a fabricated guarantee.

Then complete the remaining full code/spec audit, required cross-harness/human workflow, normal release, exactly eight pets, visible fair Cursor/Codex four-arm comparisons and separately labeled OpenCode diagnostics, and independent submission GO/NO-GO. No native benchmark, deployment, installer/package, live provider call or submission occurred in this checkpoint.
