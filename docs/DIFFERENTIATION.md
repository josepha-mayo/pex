# Why PEX is not another orchestrator

The 2026 market is full of **spawn-and-supervise** products: Omnigent/Polly, Orca, Agent Orchestrator, Traycer, Conductor, T3 Code, OpenCastle, Claude Squad. They are good at starting agents in worktrees, showing a kanban of CLIs, and merging diffs.

PEX's unit of optimization is different:

> the human + currently active AI workers + the persistent intent behind their work

## What we take from them (real features, not cargo-cult)

| Their feature | What PEX actually implements |
| --- | --- |
| Parallel agent list | Pet + Now view over *already running* sessions |
| Worktree isolation | JIT overlay + optional fork/probe, not forced PEX-owned git |
| Approval gates | Local policy broker; cloud cannot bypass |
| Shared context | Context mesh with scored bundles, not a dumped transcript |
| Mobile/remote | Same attention policy on Telegram/Discord later |
| Pets (Codex) | Current source contains exactly eight built-in Codex-v2 atlases, each with nine animation rows and sixteen look directions. Custom imports and one-call hatch outputs stay separate; hatch output is only an unverified base candidate. Playable custom-pet assembly, independent QA, and release packaging remain incomplete. |

## What we refuse to become

- A place work *must originate*
- A multi-agent chatroom
- A task board with mocked agents
- A wrapper around one harness
- A notification tray
- Polly-style "I am the tech lead, you work in my worktrees"

Those products spawn a workforce. **PEX babysits the workforce you already have.**

If an adapter cannot control a vendor, the label is Observe-only / Experimental / Unavailable — never a fake Deep checkbox.
