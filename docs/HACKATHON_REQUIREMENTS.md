# Nebius x NVIDIA hackathon requirement matrix

Verified against the [official rules](https://nebiusglobalaihackathon.devpost.com/rules)
and [official judging update](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works)
on 20 September 2026. The submission deadline is 30 October 2026 at 10:00
a.m. PDT (17:00 UTC).

| Requirement | PEX evidence | Status |
| --- | --- | --- |
| Working application using Nebius Token Factory or Nebius AI Cloud at runtime | `docs/evidence/nebius-live-proof.json` retains a sanitized Token Factory inference receipt. | Satisfied |
| At least one NVIDIA open-source model | The retained runtime receipt names `nvidia/nemotron-3-super-120b-a12b`. | Satisfied |
| Track fit | PEX is a coding-agent supervision and verification harness; target track is Coding and Agentic Engineering. | Satisfied |
| Runs consistently on its intended platform | Windows full suite and Ubuntu CI cover the source; RC13 provides Windows and Debian test builds. | Satisfied for RC13; current-head packages must be rebuilt after product changes |
| Existing project significantly updated after 26 August 2026 | `devpost-submission.md` lists the Nebius provider, BYOK vault, OpenCode/Codex adapters, UI redesign, packaging, and verification work. | Satisfied in draft |
| Free judge-accessible working demo or test build through judging | RC13 is public and free. A current-head release is still required after final fixes. | Incomplete |
| Public repository with source, assets, setup instructions, and visible open-source license | Public GitHub repository, README, and MIT `LICENSE`. | Satisfied |
| English feature and functionality description | `devpost-submission.md`. | Satisfied in draft |
| Public YouTube demonstration under three minutes showing the product functioning | No final public video URL exists. | Incomplete |
| Identify submission track | Coding and Agentic Engineering. | Satisfied in draft |
| Feedback on Nebius and NVIDIA tools/models | Evidence-based feedback is included in `devpost-submission.md`. | Satisfied in draft |
| Testing access stays free and unrestricted until judging ends | Public release requires no PEX license or login; a tester supplies their own model credential. Final judge instructions must make this boundary explicit. | Needs final attestation |

## Judging criteria

Stage one is pass/fail for viability, theme fit, and genuine use of the required
technology. Stage two scores four equally weighted criteria:

1. **Technological implementation** — prove that Nemotron supervision changes a
   real worker outcome through the same OpenCode/Codex session, and retain the
   inference, delivery, and independent verification receipts.
2. **Design** — demonstrate the complete Home → goal → supervision → evidence
   journey in the submitted build, including failure and offline states.
3. **Potential impact** — use a current paired evaluation to measure task
   success, intervention count, and PEX overhead. Do not reuse legacy rows that
   lack current provenance and timing.
4. **Quality of the idea** — show durable context retrieval, restrained
   supervision, same-session correction, handoff evidence, and independent
   completion verification rather than a code-completion wrapper.

## Remaining release order

1. Produce a current, provenance-bound paired diagnostic with and without PEX.
2. Repeat the bounded live recovery on the cooldown-fixed source without paid
   usage, or use a sponsor-provided credit balance with a verified cutoff.
3. Build and verify current Windows and Debian artifacts.
4. Record the submitted build, upload a public under-three-minute YouTube video,
   and verify playback while logged out.
5. Run `scripts/submission_preflight.py` against the exact release and video URL.

