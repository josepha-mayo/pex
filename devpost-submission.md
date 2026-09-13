# Title

PEX — The supervisor for coding agents you already use

## One-line Summary

PEX watches long-running coding agents, checks their work against persistent goals and real evidence, and intervenes only when a specific correction is justified.

## Problem

Using more coding agents often creates a new job for the human: remembering the original goal, catching drift, checking whether “done” is real, re-running verification, and typing “continue.” That repetitive supervision is expensive, interrupts focused work, and gets worse as more sessions run in parallel.

## Solution

PEX is a local Windows companion for existing coding-agent workflows. It connects to supported worker surfaces, keeps a durable goal and acceptance criteria, observes evidence, asks a bounded Strands supervisor for a structured decision, applies local policy, and either stays quiet or sends one evidence-specific correction back to the same worker session. The human retains intent and dangerous approvals; PEX handles the mechanical babysitting.

## Why This Matters

PEX targets professionals who already use coding agents and want leverage without becoming full-time dispatchers. Its value is not more agent chatter. It is fewer unnecessary interruptions, earlier detection of false completion, and a traceable explanation whenever intervention is necessary.

## How We Used AI

The production supervision path uses the Strands Agents SDK as the reasoning layer. Six request-scoped, read-only evidence tools expose the worker state, persistent goal, artifacts, verification results, prior decisions, and policy context. Strands must return a validated structured action such as `NOOP` or `SEND_NUDGE`; evidence-free approvals and unsupported actions collapse safely to `NOOP`. A local deterministic verifier and policy guard remain authoritative, so a model recommendation cannot bypass a denial or invent successful verification.

The focused live OpenCode proof uses Zen BYOK with `muse-spark-1.3-contributor-free`. In the latest installed recovery test (`bf5a25b`), PEX first corrected a missing file, then caught and corrected Windows CRLF endings that violated exact-byte requirements. The same OpenCode session repaired both files, followed by a genuine Strands `NOOP`. These three review dispatches made nine model calls and used 35,221 tokens. The extra verification criterion remained unchecked, so the audit correctly retained uncertainty about overall goal completion rather than marking the second correction helped true. A separate installed `0ea2639` already-correct control produced real Strands NOOP with zero follow-ups. No paid fallback model is silently selected.

PEX also implements a versioned Amazon Bedrock AgentCore Runtime-compatible `/ping` and `/invocations` contract. That protocol is locally tested; this submission does not claim a live AWS AgentCore deployment.

## How We Used Codex

Codex was used throughout implementation, audit, and release hardening: translating the three binding PEX specifications into acceptance gates; reviewing inherited frontend and backend code; repairing session discovery, supervision, policy, UI, packaging, and shutdown behavior; generating and validating tests; running clean-source package builds; reproducing failures; and checking claims against retained receipts. Codex also served as one supported isolated worker harness in same-session supervision tests. Every public claim in this draft is intentionally narrower than the strongest passing evidence.

## Key Features

- Goal-aware supervision above existing OpenCode and isolated Codex App Server sessions.
- Real Strands reasoning with validated structured decisions and bounded review counts.
- Zen BYOK configuration with write-only key entry and operating-system vault storage.
- Same-session correction: PEX resumes the worker that drifted instead of spawning replacement work.
- Quiet completion: verified work produces `NOOP` and no gratuitous follow-up.
- Inspector timeline for goals, evidence, decisions, delivery, and observed outcomes.
- Local policy guard that retains authority over model or remote-runtime proposals.
- Exactly two polished desktop companions, Pex and Von, with dismissible messages and independent hide/restore behavior.
- AgentCore Runtime-compatible protocol with deterministic local fallback and honest deployment labeling.

## Architecture

The desktop shell discovers supported local workers and sends normalized events to a desktop-owned loopback bridge. The bridge stores goals and evidence locally, performs deterministic verification, and invokes the Strands supervisor only within a bounded review budget. The structured proposal then passes through a local policy gate before any same-session delivery. Outcomes return to the evidence ledger and desktop Inspector. The optional AgentCore adapter implements the same typed, session-bound supervision contract without changing local authority.

Required upload asset: `docs/architecture/pex-architecture.png`.

## Testing Instructions

1. On Windows, clone `https://github.com/josepha-mayo/pex` and follow the pinned prerequisites in the README.
2. Run `./scripts/install.ps1`, then `npm --prefix apps/desktop run tauri dev`.
3. Start a throwaway OpenCode worker with `opencode serve --port 4096` and attach a terminal using `opencode attach http://127.0.0.1:4096`.
4. In PEX Settings → Connections, connect OpenCode at `http://127.0.0.1:4096`.
5. In Settings → Supervisor, select Zen, enter `muse-spark-1.3-contributor-free`, provide your own Zen API key, keep the review limit at 3, and save.
6. Attach a persistent goal to the discovered worker. Verify that already-correct work stays quiet and that an intentionally missing artifact causes an evidence-specific correction to the same session. Observe the actual outcome: provider retries or additional output defects may require further review within the cap. Do not treat an uncertain result as completion.
7. Inspect the goal, evidence, decision, delivery, and outcome in Inspector. Pause supervision and verify no new semantic dispatch occurs.

The credential field is write-only and no developer credential ships with PEX. The installer candidate is unsigned. Full judge notes are in `docs/JUDGE_TESTING.md`.

## Public Demo Link

Not required by the official form. No stable hosted demo is claimed; PEX is a local Windows desktop application.

## Public Repository Link

https://github.com/josepha-mayo/pex

License: MIT. The repository includes source, assets, README setup instructions, architecture material, tests, and evidence receipts.

## Demo Video

TODO: add the public YouTube or Vimeo URL after recording. Maximum length: 5 minutes.

Recording flow:

1. State the agent-babysitting problem, audience, and impact.
2. Show Pex, switch briefly to Von, dismiss the message without hiding the pet, and open Inspector.
3. Show one OpenCode task stop with a required artifact missing.
4. Show the Strands `SEND_NUDGE`, same worker session ID, repaired artifact, and observed outcome.
5. Show the separate correct-completion case with model-backed `NOOP` and zero follow-ups.
6. Show the policy boundary and locally tested AgentCore-compatible protocol without claiming a cloud deployment.
7. Close with: “You keep the goals and dangerous approvals. PEX keeps the mechanical supervision quiet.”

## Screenshot Shot List

1. Capture a privacy-safe Home view of the exact current installer with Von and the intended worker selected. `docs/demo/assets/pex-home-49385f2.png` is an older-build thumbnail, not current-build proof.
2. Supervisor Settings showing Zen, `muse-spark-1.3-contributor-free`, and review limit 3, with the key obscured.
3. Inspector showing the incomplete goal, evidence, structured `SEND_NUDGE`, and same-session delivery.
4. Inspector showing repaired artifacts and the actual observed outcome, including uncertainty where present.
5. Quiet completion showing model-backed `NOOP` and zero follow-ups.

## Submission Readiness Notes

- Official hackathon: Agents for Humans; live requirements/dates refreshed on 2026-09-13 at 01:47 UTC. Submissions close 2026-09-15 00:00 UTC / 01:00 Lagos.
- Track: Professional Agents.
- Authenticated Devpost account is registered, the official rules were explicitly acknowledged on 2026-09-12, and project draft `pex-mbcpr4` now exists.
- The privacy-safe Home screenshot was uploaded successfully as the Devpost project thumbnail and is processing on Devpost.
- Public repo and MIT license are ready.
- Public unsigned Windows RC1: `https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc1`. This is older `49385f2`, not the latest tested installer.
- Architecture PNG exists and is below the official 35 MiB limit.
- Current locally installed product source `bf5a25b` has a zero-blocker MSI/NSIS receipt and installed hash match. Copy/hash instructions: `docs/demo/SECOND_LAPTOP_ACCEPTANCE.md`. A matching public release remains to be made; do not overwrite RC1 artifacts.
- Current installed OpenCode recovery and prior separate quiet/Codex receipts are retained under `docs/demo/evidence/`, each bound to its exact source/package. They are not a comparative benchmark or full-spec certification.
- AgentCore protocol is locally implemented and tested but not deployed to AWS.
- PexBench is not frozen, so no comparative score or leaderboard rank is claimed.
- Live project read on 2026-09-13: `state:draft`, `published_at:null`, `video_url:null`, and `submitted_at:null` for this event. No external changes were made in this preparation pass.

## Known Limitations

- PEX currently targets Windows.
- Deep control is focused on OpenCode HTTP and isolated Codex App Server sessions; Cursor support is observe-only.
- A tester supplies their own model credential; saving a provider configuration does not itself prove inference.
- AgentCore is a locally tested deployment target, not a live AWS deployment claim.
- The formal four-arm PexBench experiment is unfrozen, so this submission makes no productivity-uplift claim.
- The release installer is unsigned.
- Current goal-completion proof remains uncertain when acceptance includes an unchecked criterion; exact artifact recovery is not automatically full-goal verification.
- Bounded installed resource checks measured roughly 380–408 MiB private memory during settled interaction. Short checks do not establish leak freedom or clear a prior whole-PC-freeze report.

## TODO Official Form Fields

- Submitter Type (`27729`, required): `Individual` (confirmed by the user on 2026-09-12).
- Country of Residence (`27730`, required): `Nigeria` (confirmed privately by the user on 2026-09-12).
- Organization (`27731`, optional): leave blank unless applicable.
- Track (`27732`, required): `Professional Agents`.
- Public repository (`27733`, required): `https://github.com/josepha-mayo/pex`.
- Architecture diagram (`27734`, required file): upload `docs/architecture/pex-architecture.png` to the Devpost draft.
- AWS Builder ID (`27735`, required): supplied privately by the user on 2026-09-12; do not publish the email in this repository.
- Live demo (`27736`, optional): omit unless a stable public URL exists.
- Testing instructions (`28191`, optional): use the concise instructions above and `docs/JUDGE_TESTING.md`.
- Older public RC1 installer: `https://github.com/josepha-mayo/pex/releases/download/v0.1.0-rc1/PEX_0.1.0_x64-setup.exe`; SHA-256 `6fb27ff7d4ec986e5b64209b1f00b70cab6593b67daafa42e08add5bd90c6d92`. TODO: publish a distinct release matching the filmed build and update this link/hash.
- Bonus blog (`27737`, optional): `https://builder.aws.com/content/3IuxELaimn2aM3bayFznibEnnhK/agents-for-humans-teaching-pex-when-to-stay-quiet` (signed-in Published state observed; logged-out reachability still needs confirmation).
- Demo video (required deliverable): TODO — public YouTube or Vimeo URL, no longer than 5 minutes.
- Codex session ID: not requested by the current official form; omit.
