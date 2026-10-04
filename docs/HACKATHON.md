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

1. `python scripts/demo_bridge.py` then `cd apps/desktop && npm run dev` (or the
   packaged app) — the setup card offers **Recorded replay** fixtures with no
   agent install.
2. Replay `tampered_acceptance_eval`. It walks a reward-hacking worker through
   the real pipeline: sealed acceptance baseline → test weakened → green "all
   tests passed" claim → `uncertain` verdict → corrective nudge naming the
   file → restore → `verified_complete`.
3. Open the Inspector on the replay session: the **Independent claim
   verification** block shows the adjudicated-claim timeline, verdicts, and
   the flagged file. `GET /v1/goals/{id}/verification-report` is the same
   ledger as JSON.

The same scenario as raw API calls is [Scenario D in the demo
runbook](demo/RUNBOOK.md). Supervising a live OpenCode worker with real
Nemotron inference follows the same runbook's main path.

## What is real vs gated

- **Runs today offline:** the full supervision pipeline, deterministic triage,
  acceptance-surface sealing and tamper detection, the replay demo, local
  subprocess public-test verification, 4,900+ backend tests.
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
