# PEX Devpost final payload

This is the exact review map for project `pex-mbcpr4` in the Agents for Humans
Hackathon. It contains no private credential or email value. The live Devpost
requirements fetched on 12 September 2026 remain authoritative.

## Project fields already present

- Name: `PEX`
- Tagline: `Stop babysitting coding agents. Keep the goals and irreversible decisions.`
- State: draft
- Owner: authenticated project author
- Built with: Strands Agents, Python, Rust, Tauri, React, TypeScript, FastAPI,
  SQLite, OpenCode, Codex, Zen, Amazon Bedrock AgentCore
- Public repository: `https://github.com/josepha-mayo/pex`
- Public Windows judge build:
  `https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc1`
- Thumbnail: privacy-safe PEX Home screenshot uploaded successfully; Devpost
  returned HTTP 200 and processing state.

## Required custom answers

| Field ID | Devpost label | Exact value/status |
| ---: | --- | --- |
| `27729` | Submitter Type | `Individual` |
| `27730` | Country of Residence | `Nigeria` |
| `27732` | Track | `Professional Agents` |
| `27733` | Public code repository | `https://github.com/josepha-mayo/pex` |
| `27734` | Architecture diagram | Upload `docs/architecture/pex-architecture.png`; do not send as a text answer |
| `27735` | AWS Builder ID | Use the email Joseph supplied privately; never copy it into Git or chat output |

The architecture file is a 104,099-byte PNG with SHA-256
`6839bdcf9667b3de104e87a675df896a75654ff62adc6111bb619d26b41eae73`,
visually reviewed at its original 1243×1733 resolution. It shows the goal/evidence/Strands/verifier/policy loop,
same-session OpenCode/Codex action, Zen BYOK vault boundary, SQLite audit, and
optional AgentCore Runtime explicitly labeled `NOT DEPLOYED`.

## Required video

The form requires one public YouTube or Vimeo URL and rejects a missing video.
Maximum length is five minutes. Use
[`SECOND_LAPTOP_ACCEPTANCE.md`](SECOND_LAPTOP_ACCEPTANCE.md) and
[`VOICEOVER_SCRIPT.md`](VOICEOVER_SCRIPT.md).

Status: **TODO — waiting for Joseph's clean-laptop recording URL.**

## Optional answers

### Live demo URL (`27736`)

Leave blank. A downloadable Windows installer is not the same as a hosted live
demo, and PEX should not mislabel it.

### Testing instructions (`28191`)

> Download the unsigned Windows judge build from
> https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc1 and verify the
> NSIS SHA-256 is
> 6fb27ff7d4ec986e5b64209b1f00b70cab6593b67daafa42e08add5bd90c6d92.
> Start a throwaway OpenCode server with `opencode serve --port 4096`, attach
> with `opencode attach http://127.0.0.1:4096`, connect PEX to that address,
> and configure Zen BYOK with the exact
> `muse-spark-1.3-contributor-free` model and review cap 3. Attach a persistent
> goal. A deliberately incomplete task should receive one evidence-specific
> correction on the same OpenCode session; a complete task should produce a
> model-backed NOOP and zero follow-ups. No key ships with PEX. AgentCore is
> locally tested, not deployed. PexBench is unfrozen and has no claimed score.

### Bonus blog (`27737`)

Candidate URL:
`https://builder.aws.com/content/3IuxELaimn2aM3bayFznibEnnhK/agents-for-humans-teaching-pex-when-to-stay-quiet`

The unauthenticated endpoint returned HTTP 200 on 12 September, but its SPA
shell did not expose the article title and exact-title search did not find it.
Keep this optional answer out until the rendered public article is independently
confirmed. Do not republish a duplicate.

## Final action gates

Before requesting `yes, submit`:

1. Attach the architecture PNG to field `27734`.
2. Add and independently open the public video URL.
3. Confirm the private Builder ID value in field `27735`.
4. Confirm Individual, Nigeria, Professional Agents, and the repository URL in
   the rendered form.
5. Review the complete project page for formatting, privacy, and claim accuracy.
6. Run the tracked-secret scan and verify `HEAD == origin/main`.
7. Present the exact payload to Joseph and receive the unambiguous phrase
   `yes, submit` before calling the final Devpost submit action.
