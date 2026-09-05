# Fresh worker state and final dispatch validation — 5 September 2026

Goal ACTIVE; product/release NO-GO. The user's 6 September WAT target remains at risk. This is a bounded source checkpoint, not enabled worker control or installed-runtime proof. All three binding specs were reread in this implementation cycle. The Recovery real-loop milestone remains the priority before optional expansion.

Accepted source: **`e64270c1e947d3e0f7c95598ec108bc2a28dc282`**, pushed with exact remote main equality verified. Six staged source/test paths passed whitespace checks. Whole-worktree diffcheck additionally reports the preserved unowned `loop.py` trailing blank line; it is not part of this commit. All bounded agents and test handles finished before handoff.

## What changed

- `adapters/codex_shared.py`: immutable `SharedCodexReadSnapshot` captures exact result JSON, connection epoch, complete-envelope revision, raw-chunk revision and monotonic observation time **at response routing**, not when the awaiting caller resumes. `read_current_thread()` reads the selected existing thread with `includeTurns=true`; it does not initialize, resume, reconnect, drain observations or write worker input. Newer local input/epoch changes or incomplete parsing refuse the snapshot.
- The transport's small `ClientProtocol` subclass tracks bytes fed versus the last successfully completed HTTP-upgrade/frame offset using the installed parser's actual consumption. Empty parser buffers alone are insufficient: an incomplete frame header may already have been consumed into a suspended generator. Complete-frame, complete-message and journal/pending checks now fence the internal text writer. No second WebSocket parser was introduced.
- `adapters/codex_subscription.py`: `refresh_control_snapshot()` validates exact selected identity, explicit direct-input support, full turn history, coherent idle/active state and complete supported text input. It freezes user item/turn IDs, content and exact nullable client correlation into a digest. Unknown/approval-wait runtime flags, partial/summary history, conflicting turns and incomplete/redacted/unsupported human content refuse control. Observation behavior remains unchanged. The method never drains the consumer queue, replays history as human events or changes reconciled history/watermarks.
- `store.py`: `validate_main_event_effect_dispatch()` reuses the complete main-effect claim checks in validation-only mode. It requires the exact already-dispatching effect/version/action, current process boot and processing owner/lease, immutable plan/intervention ALLOW binding, current goal intent/control/project/workspace and absence of later accepted human input. It samples authority again without renewing leases, advancing markers or claiming a second dispatch. Canonical action JSON is frozen before awaits; boolean/number substitution cannot exploit Python equality. The original claim API retains its behavior.

## Review and evidence

Main reviewed all three new test files and changed production paths; this is not blanket full-file approval of Store, transport or coordinator. `transport_review` owned only the Store slice and its new test file. `attachment_review` independently examined protocol semantics, reproduced the consumed-header issue, authored only the new framed read tests and approved the bounded transport diff. Main owns transport/coordinator integration. `transport_review` independently reviewed the coordinator, reproduced the unknown/empty-item-type bypass, then approved main's control-only 18-type allowlist and reran all 34 coordinator tests successfully. Unknown types remain observable but cannot be silently excluded from control intent coverage. The allowlist matches the existing generated local schema; this is not fresh installed-runtime compatibility proof.

Main final combined gate: **483 passed in 86.41 seconds**, no skips, across these 18 complete files. This supersedes the earlier 481-pass run before the two new coverage regressions:

```text
tests/unit/test_codex_shared_read_snapshot.py
tests/unit/test_codex_control_snapshot.py
tests/unit/test_main_effect_live_revalidation.py
tests/unit/test_codex_shared_transport.py
tests/unit/test_codex_shared_text_dispatch.py
tests/unit/test_codex_shared_adapter.py
tests/unit/test_codex_subscription.py
tests/unit/test_codex_subscription_close_ownership.py
tests/unit/test_codex_shared_attach.py
tests/unit/test_codex_shared_status_pipeline.py
tests/unit/test_codex_received_journal.py
tests/unit/test_codex_received_journal_transport.py
tests/unit/test_codex_received_journal_attachment.py
tests/unit/test_generic_dispatch_authority.py
tests/unit/test_event_processing_store.py
tests/unit/test_workspace_continuity_store_review.py
tests/unit/test_workspace_continuity_pipeline.py
tests/unit/test_workspace_continuity_executor.py
```

Command: `.venv/Scripts/python.exe -m pytest -q` followed by the listed paths. Scoped Ruff passed for the three changed Python files and three new test files. Overlapping author/reviewer gates must not be added: Store owner 96 passed/31.60s across three files; independent transport reviewer 39 new tests/2.26s and 141 combined/8.10s; coordinator first gate 32/1.07s. These use real temporary Store/Sans-I/O protocol and fake vendor boundaries, never live worker/model calls.

Development failures: Store fixtures initially conflicted with existing immutable vendor/intervention guards; fixtures were repaired without weakening production guards. A large-content framing fixture correctly hit the existing notification metadata limit; the reviewer replaced only its oversized content with legal JSON whitespace to isolate 64-bit framing. Initial coordinator lint found two long lines, repaired before the combined gate. After the first 481-pass gate, main added two negative unknown/empty-item-type cases: both failed, independently reproduced as 2 failed/32 passed. The explicit control taxonomy repaired them; main and reviewer each reran 34 passed/1.01s before the final combined rerun. No failing test was removed to manufacture acceptance.

## Boundaries and exact next integration

There is still **no production caller of the text dispatch primitive**. Shared capability remains observe-only. These components are required ingredients, not a completed end-to-end control path. Do not enable control by changing a capability label.

1. Bind each decision to its actual observed human-input baseline. A fresh read finding newer input must refuse that decision and let the normal consumer continue; awaiting consumer drainage from inside its Pipeline action would deadlock.
2. Persist PEX outbound correction provenance **before enqueue**, binding exact client correlation/content/session/thread/subscription/epoch/effect. Observed userMessage uses `clientId`; outbound start/steer uses `clientUserMessageId`. Only an exact trusted match may become record-only correction evidence, including an uncertain attempt's echo. Never suppress by `pex-` prefix or silently classify unknown/mismatched content as owned. Repair stale turn-completion bookkeeping alongside this integration.
3. Wire real Pipeline/Executor effect context to fresh coordinator state, live local policy and the new Store validator, then the one same-channel start/steer primitive. Preserve known-unstarted versus attempted/uncertain outcomes. Never retry an uncertain action or fall back from steer to start. Store validation is a local transaction sample, not a lock across vendor I/O; callbacks alone are not durable authority.
4. Under applicable runtime/provider authority, prove actual existing-worker Strands NOOP, justified correction and independently observed outcome, plus ten quiet cases. Then finish the remaining full-spec/code/UI/cross-harness/release/eight-pet/visible fair comparison gates in `SHIP_CHECKLIST.md`.

Independent next-slice design (`attachment_review`, read-only): extend the existing main effect payload at Pipeline planning (~2685), validate server-generated correlation/content/identity in `Store.commit_event_plan` (~21465), and carry its claimed grant through `_resume_planned_event` into `executor.py`. Exact line numbers will shift with edits. Do not accept binding from action/model metadata. Preserve the existing four-key Codex worker-delivery receipt; keep richer provenance with the effect. Register/load trusted bindings before enqueue and before a reattached adapter pump starts (`codex_shared_attach.py` publication path). Historical exact attribution can survive reattachment under the same proven worker/workspace; old subscription/epoch must never regain delivery authority. Missing/truncated binding loads must not silently turn known prior PEX corrections into human intent. STATUS event type alone does not make an echo record-only: add an explicit Store-validated record-only branch in `Pipeline.ingest_shared_codex_event`. Use the same classifier for live echoes and fresh-history human-input digests. Test echo before ACK, echo after uncertain send, restart attribution, mismatch/spoofed prefix, failed persistence with zero writes and no additional supervisor invocation from a PEX echo. No design source edits were made by that reviewer.

Vendor races remain: start has no idle/latest-input CAS; steer fences an active turn ID, not another client's latest human input. Local byte revisions and receipt time do not provide server-global atomicity. Coordinator text-only certification intentionally refuses unsupported input; that is a control limitation, not loss of the retained observation. No public raw snapshot endpoint or model export was added. Crash recovery and uncertain-delivery recovery remain separate work.

No installed proxy/worker/provider, new Cursor, native UI benchmark, package/freeze, deployment or submission ran. No production global settings/hooks/ACLs were changed. Tests ran on the existing dirty checkout; the unowned supervisor `loop.py` +28 was preserved, SHA256 `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`. It must not be staged or represented as reviewed. A dirty-checkout gate is not clean-package evidence.
