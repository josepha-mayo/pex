# Current-release Codex/Zen/Strands live pair — 13 September 2026

Source: clean `8e99e9fef70fb99f302f451f7c7f96d2f76b5ae4`, equal to
`origin/main` before and after the run. Product code remains the exact verified
package source at `1cd42c8`; the later commits add package and live evidence
only. Source fingerprint:
`fbd1a913fe91c7ab417f193e20e56dcd0f73441bb4c9e593cf1a6de645d16d16`.

Worker: explicitly pinned `gpt-5.3-codex-spark` through separately owned Codex
stdio app-server processes and the user's approved Codex quota. Supervisor:
saved OS-vault Zen credential, exact `muse-spark-1.3-contributor-free`,
`https://opencode.ai/zen/v1`, and Strands Agents. Review cap three; no provider
substitution, paid fallback, AWS deployment, existing Codex thread, or
comparative benchmark.

## Result

The two unchanged live contract tests passed in 145.36 seconds. JUnit reports
two tests, zero failures, zero errors, and zero skips:

- controlled incomplete stop: 102.467 seconds;
- correct-completion control: 42.566 seconds.

The recovery receipt is `proof_status: validated`. PEX independently verified
the empty `report.txt` as unsatisfied, completed a four-call semantic correction
decision, delivered one evidence-specific `SEND_NUDGE` to the same Codex thread,
observed `report.txt` containing `shipped`, marked the correction `helped: true`,
and completed a final one-call `NOOP`. Two worker turns were used.

The correct-completion receipt is also `proof_status: validated`. One worker
turn wrote `pong`; PEX independently classified the evidence as supported,
completed one model-backed `NOOP`, and emitted no follow-up delivery.

Both proof processes retained initialized app-server identity and unchanged
source provenance. Their owned PIDs 4236 and 6044 were absent after cleanup.
The older Codex app-server PID 12628 predated this run and was not touched.

Retained local receipts under `build/codex-8e99e9f-20260913`:

- `codex_incomplete_proof.json` — SHA-256
  `235f9a35e1de6d3214389efad2d961443fa29dbf2efc505afcaab9170daad579`
- `codex_inspect_proof.json` — SHA-256
  `bacbcac53a62f1998e7c9a843987b4e3e9c1fcceedcd2bcf73f93e9046cbffaf`
- `result.xml` — 514 bytes — SHA-256
  `76db5075300e3e87a4e9dd88b8f2118bb25f7e32fb998cd5058f7e07c854e57b`
- `run.json` — 192 bytes — SHA-256
  `15ced65acd450aa13230e7e9306a31c23bc760abd010ad4a35683d0534fa33d3`

## Claim boundary

This is fresh current-release production-pipeline evidence for one Codex
recovery and one Codex restraint case. It is not a desktop-driven worker turn,
a formal comparative productivity score, statistical interruption-rate proof,
or a live AWS AgentCore deployment. The quiet test checks normalized text, not
an exact byte-level newline contract.
