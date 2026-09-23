# Nebius x NVIDIA hackathon requirement matrix

Verified against the [official rules](https://nebiusglobalaihackathon.devpost.com/rules)
and [official judging update](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works)
on 23 September 2026. The submission deadline is 30 October 2026 at 10:00
a.m. PDT (17:00 UTC).

| Requirement | PEX evidence | Status |
| --- | --- | --- |
| Working application using Nebius Token Factory or Nebius AI Cloud at runtime | `docs/evidence/nebius-live-proof.json` retains a sanitized Token Factory inference receipt. | Satisfied |
| At least one NVIDIA open-source model | The retained runtime receipt names `nvidia/nemotron-3-super-120b-a12b`. | Satisfied |
| Track fit | Target Best Apps and Agents: PEX is a user-facing supervision app powered by Nemotron on Token Factory. The Coding and Agentic Engineering description calls for Token Factory Sandboxes, which PEX does not currently use. | Aligned in draft |
| Runs consistently on its intended platform | Exact-source RC23 passed Windows and Ubuntu source suites, desktop builds, Windows package verification, and tagged Linux packaging and bridge smoke checks. | Satisfied for RC23 |
| Existing project significantly updated after 26 August 2026 | `devpost-submission.md` lists the Nebius provider, BYOK vault, OpenCode/Codex adapters, UI redesign, packaging, and verification work. | Satisfied in draft |
| Free judge-accessible working demo or test build through judging | RC23 is public and free at the repository release URL. | Satisfied for RC23 |
| Public repository with source, assets, setup instructions, and visible open-source license | Public GitHub repository, README, and MIT `LICENSE`. | Satisfied |
| English feature and functionality description | `devpost-submission.md`. | Satisfied in draft |
| Public YouTube demonstration under three minutes showing the product functioning | No final public video URL exists. | Incomplete |
| Identify submission track | Best Apps and Agents. | Selected in draft; not submitted |
| Feedback on Nebius and NVIDIA tools/models | Evidence-based feedback is included in `devpost-submission.md`. | Satisfied in draft |
| Testing access stays free and unrestricted until judging ends | Public release requires no PEX license or login, but semantic supervision currently needs a tester-owned Token Factory key. Free, unrestricted judging of that feature is not yet proven. | Incomplete |

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

1. Extend the current five-task Codex recovery diagnostic to natural repository
   tasks and repeated trials; the retained pairs prove the runner path and
   report observed overhead, but do not establish general performance lift.
2. Repeat the bounded live recovery only if sponsor-provided credit is available
   with a verified cutoff; RC23 packaging made zero paid provider calls.
3. Record the submitted build, upload a public under-three-minute YouTube video,
   and verify playback while logged out.
4. Run `scripts/submission_preflight.py` against the exact release and video URL.
