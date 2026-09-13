# PEX Devpost final payload

This is the exact review map for project `pex-mbcpr4` in the Agents for Humans
Hackathon. It contains no private credential or email value. The live Devpost
requirements fetched on 12 September 2026 remain authoritative.

## Project fields already present

- Name: `PEX`
- Tagline: `Stop babysitting coding agents. Keep the goals and irreversible decisions.`
- State: public project page exists; hackathon submission receipt is still absent
- Owner: authenticated project author
- Built with: Strands Agents, Python, Rust, Tauri, React, TypeScript, FastAPI,
  SQLite, OpenCode, Codex, Zen, Amazon Bedrock AgentCore
- Public repository: `https://github.com/josepha-mayo/pex`
- Public Windows judge build: RC4 is public at
  `https://github.com/josepha-mayo/pex/releases/tag/v0.1.0-rc4` and contains
  product source `f2832a8` with server-recorded matching hashes.
- Thumbnail: the clean `docs/demo/assets/pex-mark.png` mark is uploaded.

## Required custom answers

| Field ID | Devpost label | Exact value/status |
| ---: | --- | --- |
| `27729` | Submitter Type | `Individual` |
| `27730` | Country of Residence | `Nigeria` |
| `27732` | Track | `Professional Agents` |
| `27733` | Public code repository | `https://github.com/josepha-mayo/pex` |
| `27734` | Architecture diagram | Upload `docs/architecture/pex-architecture.png`; do not send as a text answer |
| `27735` | AWS Builder ID | Use the email Joseph supplied privately; never copy it into Git or chat output |

The architecture file is a 94,752-byte PNG with SHA-256
`dea91e42f057aea78a2d7c61add7b36de1ad3fc630a742bfd916e1a016fadd68`,
visually reviewed at its original 1600×900 resolution. It shows the goal/evidence/Strands/verifier/policy loop,
same-session OpenCode/Codex action, Zen BYOK vault boundary, SQLite audit, and
optional AgentCore Runtime explicitly labeled `NOT DEPLOYED`.

The replacement project mark is a transparent 1024×1024 PNG at
`docs/demo/assets/pex-mark.png`, SHA-256
`61ff11794df490525b95a3e7b83c6c635e641f01c50f1a0cb8187f1276709795`.

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

> Download the unsigned Windows judge build from the RC4 release and
> verify `PEX_0.1.0_x64-setup.exe` SHA-256 is
> 63d9f4ae90ac9b3f83f5334b3d3c9abf8ef3db7d8be82e87ff1876f3b007b18a.
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
2. Confirm the already-public `f2832a8` RC4 asset and server-recorded NSIS hash.
3. Add and independently open the public video URL.
4. Confirm the private Builder ID value in field `27735`.
5. Confirm Individual, Nigeria, Professional Agents, and the repository URL in
   the rendered form.
6. Review the complete project page for formatting, privacy, and claim accuracy.
7. Run the tracked-secret scan and verify `HEAD == origin/main`.
8. Present the exact payload to Joseph and receive the unambiguous phrase
   `yes, submit` before calling the final Devpost submit action.
