# DECISIONS

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
Ten starters are generated as 8×11 / 192×208 atlases with the hatch-pet row contract. We import user Codex pets (`pet.json` + `spritesheet.webp`) and never copy Codex built-in sprites.

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


