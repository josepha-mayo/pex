# DECISIONS

## 5 Sep 2026 — Separate standing correction consent and finish claimed results durably

Observation attachment is not correction consent. Grant the four same-thread text actions through an authenticated, exact-scope, revocable Store operation; keep generic adapter capabilities and the original observation-only receipt truthful. Permission is standing authorization, not a per-correction dialog. The model may learn the current route state but cannot author its authority. Preserve existing safety-triage prefixes when appending that context.

Executor receives an exact existing main-effect claim, installs persisted correction attribution before fresh history comparison, and performs final Store/local/transport checks immediately before one start or exact-turn steer. No uncertain retry or fallback. Once Executor returns or is cancelled after a claim, join the entire result-refresh/seal task through repeated cancellation; observer shutdown must not discard a known ACK or strand intentional cleanup between those steps. These are local implementation contracts, not proof of real Strands/AgentCore outcomes. Current review and limitations: [`docs/CODEX_CLAIMED_DISPATCH_REVIEW.md`](docs/CODEX_CLAIMED_DISPATCH_REVIEW.md).

## 5 Sep 2026 — Carry workspace authority through processing without rewriting history

Persist the server-selected workspace/subscription/origin-path witness at dedicated observer publication. Never derive missing authority from a request or database location. Recheck at transactional planning/dispatch and actual queued local-read/provider/adapter entry, with post-read rejection of stale evidence. Generic session refresh cannot mint or erase observer authority. Old witnessed metadata without the new durable server row requires explicit reattachment, not guessed migration.

Keep pre-call refusal distinct from a known or uncertain call: after a dispatch marker, a proven unstarted planner is `failed` with `provider_started=false`; actual model and worker receipts survive workspace loss, while stale session projections do not. Observer loss retains validated history without retrying stale processing. Rollback/cleanup uses its existing separately scoped recovery contract.

Ask needs both workspace-specific tool authority and invocation-lifetime authority: a surviving thread may otherwise start a second provider path after the outer request ends. Scope copies share revocation; each HTTP fallback attempt and scheduled Strands entry checks it. This is not cancellation of already-entered SDK-internal work. Completion excludes detached historical sessions but does not hide attached sessions merely because a UI activity filter does. Evidence and remaining limits: [`docs/WORKSPACE_CONTINUITY_REVIEW.md`](docs/WORKSPACE_CONTINUITY_REVIEW.md).

## 5 Sep 2026 — Explicit origin plus sampled directory evidence for attachment

Bind selected existing-worker attachment to an operator-declared local origin, server-measured directory identity and current registered locator, not a path string or guessed hostname. Preserve project identities/history; separate origin setup from project registration. Even an older bare locator cannot override a conflicting physical claim for that same local directory. Freeze the choice revision/incarnation with the workspace and recheck after authority awaits and at transactional publication. Exact-subscription detach remains possible when the directory/config disappears; it preserves historical evidence, not new action authority. Filesystem samples are deliberately not machine attestation or an atomic worker-cwd lock. Continuous evidence/action fencing remains required before safe worker control.

Origin saves settle their one threaded publication under the attachment lock; uncertain failures require reload. Temporary publication verifies both owned object and exact desired bytes before replacing valid config. Scope stays on the real Recovery loop: backend setup APIs are not finished UI, live observation or Strands outcome proof.

## 5 Sep 2026 — Preserve observations without reviving disconnected authority

A later invalid/closing notification must not erase a validated prefix. Freeze full bounded batches before queue backpressure; after stream loss, use a dedicated adapter-object-witnessed record-only Pipeline/SQLite path. It preserves canonical duplicate bindings and processing modes, does not project over current session/human controls, and cannot invoke the semantic planner. Keep recovery acceptance, pending counts and the local disconnect receipt distinct. Support both full reconciliation drains, not only normal streaming capacity. Retention bounds/timeouts are explicit, not claims of full raw capture or process-crash durability. Normal live-ingestion authority checks and disabled shared delivery remain unchanged. Official lifecycle semantics were rechecked through the OpenAI Docs skill: [Codex App Server events](https://learn.chatgpt.com/docs/app-server).

## 5 Sep 2026 — Observer state is not worker activity or control authority

Existing-thread Codex observations use a dedicated internal callback with an in-flight adapter object witness. It freezes a per-event runtime/activity/coverage snapshot; generic HTTP/plugin ingestion cannot supply that reserved marker. SQLite rechecks the durable subscription receipt and cwd, then projects from the canonical accepted event rather than current mutable adapter state or arbitrary planned metadata. Thread runtime and turn terminal status remain independent. Local observer loss is atomic record-only state, never a synthetic worker STOP or supervisor trigger. A new observer incarnation preserves current human goal/pause and revokes old session-control authority; task cancellation settles publication, but process-crash recovery remains required.

Normalized human input is evidence, not automatic authorization: incomplete, truncated, malformed or redacted Codex content cannot create an explicit HUMAN override. It remains a USER_PROMPT observation for provenance and stale-action fencing. Existing redaction markers conservatively retain uncertainty even when text was redacted upstream.

This source checkpoint deliberately does not certify full raw/durable coverage or same-worker delivery. Complete supervision still requires the real Strands/evidence/decision/policy/action/outcome loop. Current protocol reference: [official Codex App Server documentation](https://learn.chatgpt.com/docs/app-server).

## D1 — Local bridge is the side-effect authority
The Strands/AgentCore supervisor proposes typed actions. The local Python bridge enforces policy, redacts secrets, and executes adapter calls. Cloud cannot bypass this.

## D2 — Deterministic triage before any frontier model
High-frequency events never each invoke a model. Drift, stagnation, repeated commands, missing tests, and routine permission class are computed in code. Strands is used when semantic judgment is actually required or when explicitly forced.

## D3 — Synthetic adapter is a first-class harness
M0 cannot depend on mocked control. The synthetic adapter is a real in-process control surface used by tests and demos. It is labeled honestly and is not presented as Cursor/Codex.

## D4 — Cursor via official hooks first
Preference order from the spec: official structured APIs, then ACP, then hooks. Cursor hooks are official, bidirectional enough for stop follow-ups, prompt gating, and shell permission. ACP/CLI is the next deepening step, not a replacement that throws hooks away.

## D5 — Fail-open hooks, fail-closed destructive policy
If the bridge is down, Cursor hooks return `{}` so the user's harness is not frozen. Destructive commands still cannot be auto-approved when the bridge *is* up.

## D6 — MIT license
Hackathon requires MIT or Apache. MIT keeps contribution friction low.

## D7 — uv workspace + Python 3.11+
Bridge, supervisor, and protocol are a uv workspace so the Strands supervisor can be imported locally and also deployed as an AgentCore service.

## D9 — Never call PATH `agent` for Cursor
On this machine `agent` is Grok Build. Cursor is this desktop session via `~/.cursor/hooks.json`. Do not install or spawn `%LOCALAPPDATA%\\cursor-agent`. Do not open a second Cursor window.

## D11 — Pets are Codex-v2 compatible, original art
Exactly eight built-ins (`pex`, `ledger`, `mesh`, `nudge`, `drift`, `quiet`,
`ember`, `von`) use 8×11 / 192×208 atlases with the hatch-pet row contract.
User imports (`pet.json` + `spritesheet.webp`) and hatches are a separate custom
roster; they never expand or replace the built-in eight. We never copy Codex
built-in sprites.

## D12 — Deep means a live official transport
OpenCode and Qwen are Deep only with an attached HTTP transport. Codex is Deep only after App Server handshake. Cursor's primary official transport is `~/.cursor/hooks.json` (Strong; Deep only if ACP is *explicitly* attached later). Grok Build ACP is `grok agent stdio`. Registration is not a capability claim.

## D13 — Codex App Server over stdio on Windows
`codex app-server daemon` is Unix-only. On this machine PEX attaches with `codex app-server --listen stdio://` (JSONL, `jsonrpc` header omitted). Deep only after `initialize` + `initialized` succeeds. Binary discovery is not a capability claim.

## D14 — Attach to running desktops first
The operator already runs coding apps. Discovery prefers live desktop processes. Cursor control is `~/.cursor/hooks.json` in the editor, never a leftover `cursor-agent` CLI. Codex control is App Server JSON-RPC against the same `~/.codex` the desktop uses. Grok Bot stays observe-only until an official local control API exists. Hermes and Devin desktops are optional — do not open them unless the operator asks. Grok Build is CLI (`grok agent stdio` / `grok -p`), not Grok Bot.

## D15 — Grok Build CLI is not Grok Bot
Grok Bot is the desktop app (`Grok Bot.exe`): cloud-computer teammates ([docs](https://docs.x.ai/grok-bot/overview)). Grok Build is `~/.grok/bin/grok.exe` ([docs](https://docs.x.ai/build/overview)). Official Grok Build ACP is `grok agent stdio`. Headless one-shot is `grok -p`. PATH `agent` is Grok Build and must never be used as Cursor ACP.

## D16 — Every increment is audited before it is claimed done
`uv run pytest` must pass. Honesty invariants in `tests/unit/test_audit_invariants.py` must pass. After a change batch, run Bugbot on the uncommitted (or branch) diff. Do not freeze PexBench from synthetic smoke. Do not spawn extra Cursor windows to "fix" Cursor attach.

## D17 — Supervisor credentials are local, opaque, audience-bound, and transactional
The JSON supervisor snapshot stores only versioned routing fields and an opaque secret
reference. Raw BYOK values live in an allowlisted native OS keyring backend and are never
returned by REST or UI. Provider/auth/protocol/base URL form the credential audience;
cross-audience reuse fails closed. PATCH validates and constructs a task-local candidate
before atomic persistence and live swap, uses revision compare-and-swap when supplied,
and cleans staged/retired secrets around the commit boundary. Login and AgentCore auth do
not silently fall back to API-key or Bedrock behavior when their adapters are absent.

## D18 — Attention metrics come from one durable backend snapshot, never UI pages
`ASK_HUMAN` is an attention request, not a human intervention. Product metrics are read
from one SQLite snapshot over exact durable ledgers, with an all-time window, source
watermarks, explicit coverage, null-preserving denominators, and separate current-live
pending authority. Because pause/resume, goal mutation, and out-of-band human actions do
not yet have complete append-only receipts, the canonical human-intervention total stays
null; an authenticated observed lower bound is labeled separately. Existing direct
message/handoff receipts are actor-unverified and cannot become human proof retroactively.
Human active time and unnecessary-alert rate stay null until consented focus intervals and
alert exposure/adjudication exist. Operational product counts are never benchmark evidence.


