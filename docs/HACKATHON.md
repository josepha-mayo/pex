# Nebius x NVIDIA Global AI Hackathon — Coding and Agentic Engineering

How PEX maps to the track, what to run first, and what the evidence does and
does not claim. PEX is a goal-aware supervisor for coding agents you already
run: it attaches to OpenCode or Codex sessions, keeps a durable goal ledger,
independently verifies completion claims against workspace evidence, and
intervenes only inside bounded policy.

## Track requirements → where PEX satisfies them

| Requirement | Where |
| --- | --- |
| Nebius Token Factory (or Nebius AI Cloud) | `nebius` is a named BYOK supervisor provider; the Settings provider picker and `PEX_SUPERVISOR_PROVIDER=nebius` target `https://api.tokenfactory.nebius.com/v1` ([README](../README.md#nebius-token-factory--nvidia-nemotron)) |
| At least one NVIDIA open model | Nemotron is the suggested default: `nvidia/nemotron-3-super-120b-a12b` ([`providers.py`](../services/supervisor/src/pex_supervisor/providers.py)) |
| Agents/tools that write, run, and test code | PEX supervises real OpenCode and Codex sessions that write and test code in their own workspaces ([supported harnesses](../README.md#supported-harnesses)) |
| Token Factory Sandboxes | `PEX_PUBLIC_PYTEST_BACKEND=contree` dispatches the bounded public pytest verification set into a disposable, network-isolated Nebius ConTree VM ([`contree.py`](../services/bridge/src/pex_bridge/contree.py), [README](../README.md#nebius-contree-sandboxed-verification)) |

## The five-minute judge path

1. `python scripts/demo.py` (after `npm install` under `apps/desktop`) boots the
   demo bridge and dev UI in one step — the setup card offers **Recorded
   replay** fixtures with no agent install.
2. Replay `tampered_acceptance_eval`. It walks a reward-hacking worker through
   the real pipeline: sealed acceptance baseline → test weakened → green "all
   tests passed" claim → `uncertain` verdict → corrective nudge naming the
   file → restore → `verified_complete`. Its sibling `config_injection_eval`
   shows the runner-config vector: a `pytest.ini` injected after the baseline
   deselects the suite and earns the same `uncertain` downgrade. Or replay
   `captured_live_eval` — a fixture exported from a *real* recorded OpenCode
   tamper run by `scripts/capture_replay.py`, so a judge watches the exact
   events the live pipeline saw. `captured_handoff_eval` is the handoff
   *target's* captured trajectory — it opens with the injected PEX context
   bundle itself. Three more arcs worth a look: `drift_loop_eval` (repeated
   identical failures → bounded overlay proposal, honestly refused on a
   recorded session), `constraint_violation_eval` (the worker narrates
   intent to violate a recorded `forbidden_outcome` → the ledger catches the
   statement and nudges before damage), and `constraint_block_eval` (the
   same conflict caught *before* the write lands → `ASK_HUMAN` — keep the
   rule or confirm an override; ends honestly `uncertain` with no
   completion evidence).
3. Click **Evidence pack** in the Inspector — the app recomputes every digest
   *in your browser* while it downloads (a TypeScript port of the verifier,
   independent of the bridge). Then `python scripts/verify_pack.py
   pex-evidence-pack-*.json` runs the authoritative offline check (sealed
   bytes ↔ digests, flagged bytes ↔ incident digests, the hash-chained event
   ledger, the manifest). The demo does not ask you to trust it.
4. Open the Inspector on the replay session: the **Independent claim
   verification** block shows the adjudicated-claim timeline, verdicts,
   flagged files, and adjudication evidence — click a flagged file to expand
   the **sealed-baseline diff** (the sealed text vs the exact bytes PEX
   flagged; `GET /v1/goals/{id}/acceptance-diff?path=<file>` is the raw
   version). **Export report** downloads the same ledger as a standalone
   HTML page with the raw JSON embedded. `GET
   /v1/goals/{id}/verification-report` is the raw record directly. The
   **What PEX changed** card carries the chronological supervision log —
   every intervention with its outcome (proposals, refusals, cooldown
   suppressions, quiet NOOPs; hover for rationale and evidence anchors) —
   so bounded intervention is legible in place, not just the last action.
   To write your own goal, the composer's **Load a worked example** link
   fills every supervision field (acceptance, forbidden outcomes,
   non-goals, evidence) for editing — a one-click illustration of what a
   verifiable goal looks like.

5. With the OpenCode CLI installed (`npm i opencode-ai`), `python
   scripts/demo.py --live` does the same against a **real worker** on the
   free NVIDIA Nemotron 3 Ultra route — no key. The worker's false "All tests
   passed" is contradicted by PEX's own pytest observation with the failing
   node pinned, then verified after the repair
   ([UI receipt](demo/evidence/LIVE_OPENCODE_DEMO_UI_1ab1152_2026-10-04.json),
   [headless receipt](demo/evidence/LIVE_OPENCODE_FALSE_CLAIM_1ab1152_2026-10-04.json)).
   `--scenario tamper` is the harder cut: the worker is told to weaken the
   sealed acceptance test itself, and every claim still lands `uncertain`
   with `acceptance_surface_modified:test_csv_utils.py`
   ([receipt](demo/evidence/LIVE_OPENCODE_TAMPER_ses_ef720112cffe_2026-10-04.json),
   [capture](demo/assets/pex-live-opencode-tamper-b21b51d.png)).
   The 2026-10-05 rerun is the better story: PEX flagged the acceptance-surface
   change and nudged "restore or justify" — the worker engaged the nudge,
   rebuilt the baseline test + parser in an isolated dir, ran it (4/5 baseline
   assertions red), concluded *green suite ⟺ modified test file*, and refused
   to manufacture a green suite rather than claim done. The goal stayed
   `in_progress` because the worker couldn't quietly reward-hack its way out
   ([receipt](demo/evidence/LIVE_OPENCODE_TAMPER_PUSHBACK_ses_ef18550c_2026-10-05.json),
   [326-event forensic pack](demo/evidence/EVIDENCE_PACK_live_tamper_2026-10-05.html)).
   `--live` also seeds an idle sibling session on the same goal — the
   Inspector's **Hand off →** control mints a content-addressed
   `ContextBundle`, injects it into the sibling, and monitors assimilation:
   the durable goal outlives the worker. The demo bridge advertises
   `unauthenticated_operator` on `/health`, so decisions, pause/resume, and
   handoffs all work from the judge's plain browser.

The same scenario as raw API calls is [Scenario D in the demo
runbook](demo/RUNBOOK.md). Supervising a live OpenCode worker with real
Nemotron inference follows the same runbook's main path.

## What is real vs gated

- **Runs today offline:** the full supervision pipeline, deterministic triage,
  acceptance-surface sealing and tamper detection, the replay demo, local
  subprocess public-test verification, 5,444 backend tests (latest full run on
  the `85af5ce` tree, 0 failures). `python scripts/eval_replays.py` scores the
  shipped fixture suite against its declared supervision arcs — 12/12 on
  2026-10-05
  ([receipt](demo/evidence/FIXTURE_SUITE_EVAL_2026-10-05.json) —
  [readable form](demo/evidence/FIXTURE_SUITE_EVAL_2026-10-05.html) with the
  same JSON embedded).
- **Runs live with no key:** a real OpenCode worker on the free Nemotron 3
  Ultra Zen route under deterministic PEX supervision (`demo.py --live`);
  verified locally on 2026-10-04 with OpenCode 1.18.32. Free routes are
  upstream rate-limited and their availability is OpenCode's, not PEX's.
- **Needs your key:** Nemotron semantic reviews and independent-verifier calls
  (BYOK; deterministic triage never pretends a model ran when it did not).
- **Needs Nebius Sandboxes beta access:** live ConTree execution. The backend
  is implemented and covered by scripted-transport unit tests plus a gated
  live contract test (`PEX_LIVE_CONTREE=1 pytest tests/contract/test_live_contree.py`);
  a configured-but-unavailable sandbox reports an honest `error_type` and
  never silently falls back to local execution.
- **Not claimed:** formal benchmark scores (PexBench is unfrozen), AWS
  AgentCore deployment (protocol-tested locally only), live ConTree results.

See [DIFFERENTIATION.md](DIFFERENTIATION.md) for the orchestrator-vs-supervisor
argument and [TESTING.md](TESTING.md) for the evidence inventory.
