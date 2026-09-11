# Current-source OpenCode causal-recovery receipt — 11 September 2026

## Result

**PASS for one bounded same-session recovery case.** Clean source
`93dfef3a77c5c1a92c6adf97d22f2964e9b7f227` ran a real OpenCode 1.18.30
worker through the production HTTP/SSE adapter and the real local Strands
supervisor. The controlled first stop had the exact stage-one artifact, lacked
the required final artifact, and had received no earlier PEX follow-up. PEX
inspected that gap, obtained an independent verifier approval, sent one specific
same-session correction, observed the exact final artifacts, attributed the
successful outcome to that correction, and then stayed quiet on the final stop.

This is a single public diagnostic, not a comparative benchmark, native-desktop
acceptance, a scored win, or AgentCore deployment evidence.

## Bound result

- Run root: `build/opencode-recovery-93dfef3-20260911-r2` (local and ignored).
- PEX session: `opencode:ses_f6ebc5ec7ffeW43vOWUaqK7XPm` throughout.
- Goal: `goal_45c4884e726a44b28f28c2129c01194a`.
- First observed stop: `stage-one.txt` exact, `final.txt` absent, zero prior
  PEX follow-ups.
- Final state: both artifacts exact; 441 retained events; all processing rows
  settled; every semantic review completed.
- Chronological actions: one `SEND_NUDGE`, then one model-backed `NOOP` after
  acceptance became supported. The retained interventions endpoint presents
  newest first, so its raw action array is `[NOOP, SEND_NUDGE]`.
- Delivery result: `sent`; outcome: `goal_evidence_supported`; `helped: true`;
  final outcome marker present; independent verifier approved.
- Worker: `ling-3.0-flash-fin-free`; supervisor:
  `muse-spark-1.3-contributor-free` through saved Zen BYOK.
- Model accounting: 7 calls, 23,611 input tokens, 1,855 output tokens.
- Wall time: 210.50 seconds. The owned OpenCode server exited.

The current official Zen pricing table listed both exact models as Free for
input and output at execution time. No AWS route or paid fallback was enabled.

## Integrity

| Artifact | SHA-256 |
| --- | --- |
| `summary.json` | `41f7a0093ac1431bea3acd6819a1abf53ca0cad21cf1aedc1179d4099f8269fe` |
| `receipt.json` | `55089f84f42469ffe0f2b3a8a2b9a263bb50b087d8480bd31284fb9b14b23b8e` |
| retained `runner.py` | `ba7bcf032449f95d9fa57365bc67b78a0ff5bee05551945f92c5754ed6564e80` |
| retained `completion-fence.py` | `261767e9f0d9c236bb43e1503ef1f439c0dd50548a14793c5f3094cd510186a7` |
| `interventions.json` | `e74578b88cdac26c5605b2ba827f3fdfe27b7bfb07e7e57aa9eb53bb6039c888` |

A byte-exact scan of the 35 retained proof files outside the isolated OpenCode
cache/config/data/state directories found zero copies of the saved vault secret.
Those profile directories remain local for diagnosis and must not be published
without a separate privacy review.

## Defect found and repaired afterward

The successful correction included the right literal but an incorrect derived
parenthetical byte count. The worker still produced the exact 18-byte file, so
the causal recovery result is valid, but that prose is not presentation-quality.
Source `a242a84` now removes model-derived parenthetical byte counts from
worker-facing nudges and tells both the Strands supervisor and independent
verifier to require direct support for numeric claims. The focused recovery
suite passed 92 tests; the expanded Strands/provider/AgentCore/evidence gate
passed 243 with 4 intentional skips. This deterministic repair is newer than
the live receipt and must be included in the final package.

## Remaining gate

Build and verify an exact-source package containing `a242a84`, then complete
visible startup, transparency, pet controls, Zen settings, OpenCode connection,
foreground-resource, and short recording acceptance when the shared screen is
free. Keep the benchmark manifest unfrozen until fair comparative evidence
exists.
