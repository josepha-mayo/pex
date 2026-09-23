# PEX — Nebius × NVIDIA submission draft

## Track

Coding and Agentic Engineering

## One-line summary

PEX supervises the coding agents you already use, checks their work against durable goals and evidence, and sends a bounded correction only when NVIDIA Nemotron finds a justified problem.

## The problem

Running several coding agents creates a new human job: remembering the real goal, catching drift, checking whether “done” is true, and repeatedly typing “continue.” PEX reduces that mechanical supervision while keeping intent and risky decisions with the human.

## What PEX does

PEX is a local Windows and Linux desktop harness for OpenCode and Codex App Server workers. A user connects an existing worker, attaches a persistent goal and acceptance criteria, and sees current evidence on Home. A separate supervisor reviews bounded observations, returns a structured action such as `NOOP` or `SEND_NUDGE`, and passes that proposal through deterministic verification and local policy before any same-session delivery. Inspector retains the goal, evidence, decision, delivery, and observed outcome.

## Nebius and NVIDIA implementation

PEX supports Nebius Token Factory through its OpenAI-compatible inference API at `https://api.tokenfactory.nebius.com/v1`. The primary submission model is `nvidia/nemotron-3-super-120b-a12b`; the UI also exposes account-dependent Nemotron 3.5 Lightning and Ultra suggestions. The key is entered through a write-only BYOK field and stored in the operating-system credential vault. Provider, authentication mode, endpoint, and credential audience are bound together so a pasted key cannot silently follow a configuration change.

The submission must include retained evidence from a successful runtime Token Factory call using an NVIDIA open-source model. Provider configuration or catalog suggestions alone do not satisfy that rule.

## Significant updates during the submission period

PEX existed before August 26, 2026. During the submission period it received substantial product changes:

- a new Nebius Token Factory provider and NVIDIA Nemotron model path;
- a redesigned Home, Inspector, Deck, and segmented Settings harness;
- destination-bound BYOK handling and approved Windows/Linux keyring chains;
- real OpenCode HTTP/SSE attachment with optional Basic authentication;
- indexed Codex App Server discovery and truthful stopped-session activity;
- Windows and Linux discovery, cleanup identity, ACL, startup, and native packaging repairs;
- push CI plus Windows NSIS and Ubuntu Debian package/bootstrap/bridge verification;
- responsive browser acceptance and fail-closed submission checks aligned to this event.

## Why the idea matters

PEX targets developers who already use coding agents and want more parallel work without becoming full-time dispatchers. Its key design choice is restraint: correct work produces `NOOP`; incomplete work receives one evidence-specific, policy-allowed correction on the same worker. The product makes every intervention inspectable instead of hiding supervision inside another chat transcript.

## Product feedback

- Token Factory's OpenAI-compatible global API made provider integration direct: the existing PEX OpenAI transport needed only a provider definition, scoped credential handling, and a model ID. The live Nemotron Super probe followed the requested JSON shape and completed in 54 total tokens.
- Endpoint migration needs a clearer failure path. The older regional hostname returned an authentication error for a valid key, while the current global hostname worked immediately. A redirect, a typed deprecation response, or a prominent migration note would save debugging time.
- Model IDs in the live catalog mix case and separator conventions, for example `nvidia/Nemotron-3_5-Lightning` and `nvidia/nemotron-3-super-120b-a12b`. Canonical aliases or copy-ready examples would reduce configuration mistakes.
- The no-card-charge cutoff is hard to verify. The [published billing guide](https://docs.tokenfactory.nebius.com/other-capabilities/billing) describes auto top-up under the balance menu, but a clear trial-only state beside the balance would make safe testing easier to confirm.

## Testing instructions

1. Download [PEX 0.1.0 RC21](https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc21), or build current `main` with the pinned prerequisites in `README.md`.
2. Start `opencode serve --port 4096`, attach an OpenCode terminal to that exact origin, and create or resume a worker session.
3. In PEX, open **Settings → Connections**, connect the loopback server, return Home, select the worker, and attach a goal with observable acceptance criteria.
4. In **Settings → Supervisor**, choose **Nebius Token Factory**, choose `nvidia/nemotron-3-super-120b-a12b`, enter a tester-owned Token Factory key, and save. Saving is configuration only; confirm a real inference receipt in Inspector.
5. Run one already-correct task and confirm a model-backed `NOOP` with zero worker follow-ups.
6. Run one deliberately incomplete task and confirm an evidence-specific correction reaches the same session, followed by an independently observed result.

The retained live proof on source `66d9b17` uses Nemotron Super as PEX and
Nemotron 3.5 Lightning as the OpenCode worker. Its correct control produced
`NOOP` with zero follow-ups. Its false-claim recovery changed an independently
failing pytest result into an independently passing result through one bounded
verification follow-up in the same session. The sanitized receipt is
`docs/evidence/nebius-opencode-proof.json`.

No developer credential ships with PEX. The public build is unsigned.

## Public repository

https://github.com/josepha-mayo/pex

License: MIT.

## Required submission fields still open

- Working demo or test-build URL: https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc21
- Public YouTube video: TODO — under three minutes and visibly demonstrating the submitted build.
- Nebius runtime proof: completed — sanitized global Token Factory catalog and inference evidence is retained in `docs/evidence/nebius-live-proof.json`.
- NVIDIA model proof: completed — the retained response names `nvidia/nemotron-3-super-120b-a12b` and records 54 total tokens.
- OpenCode recovery and quiet-control proof: completed — the retained exact-source pair records a zero-follow-up `NOOP` control and a failing-to-passing same-session recovery.
- Product feedback: completed — see the evidence-based feedback above.
- Screenshots: completed — privacy-safe Home, Inspector, and Settings frames are retained under `docs/demo/assets/*-browser-rc13.jpg`; their hashes and browser-mode boundary are in `docs/evidence/ui-browser-rc13.json`.

## Suggested video flow (under three minutes)

1. State the coding-agent supervision problem and show the clean Home harness.
2. Connect OpenCode and attach a persistent goal.
3. Show Nebius/Nemotron configuration without exposing the key.
4. Demonstrate one incomplete stop, the evidence-backed same-session correction, and the observed repair.
5. Show a separate correct task producing `NOOP` and no follow-up.
6. Close on Inspector’s audit trail and the local policy boundary.

## Honest limitations

- A valid Nebius key is required for semantic supervision; saving settings does not prove inference.
- Codex support uses an isolated Codex App Server connection, not arbitrary control of ChatGPT desktop conversations.
- The current binaries are unsigned.
- No comparative productivity score is claimed.
