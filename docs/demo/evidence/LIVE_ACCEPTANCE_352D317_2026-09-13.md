# Live acceptance of 352d317 — 13 September 2026

## Ten consecutive quiet controls passed

Source `352d317fdda1ca6a8983e27ad896dd7afbcd6783` stayed clean and unchanged
through the complete run. No cases were skipped, replaced or selectively retried.

Command: `.venv\Scripts\python.exe scripts/opencode_quiet_ten.py --run-name quiet-ten-352d317-20260913 --case-count 10`.

Worker: OpenCode `ling-3.0-flash-fin-free`. Supervisor: saved OS-vault Zen BYOK,
`muse-spark-1.3-contributor-free`, real Strands model. Both exact IDs were listed
as free in the [official pricing](https://opencode.ai/docs/zen/#pricing) checked
before the run. No paid fallback or AWS deployment was used.

All ten public artifact tasks had exact output bytes and unchanged input before
PEX's first stop review. Every case passed the worker-generation completion
fence, completed semantic reviews, and settled all observed event-processing
rows. All recorded actions were NOOP; zero follow-ups and zero observed
unnecessary interruptions among these ten eligible tasks.

| Case | Wall seconds | Supervisor API calls | Input tokens | Output tokens |
| --- | ---: | ---: | ---: | ---: |
| Deduplicate | 142.30 | 4 | 14195 | 1465 |
| Quantity | 86.03 | 2 | 7069 | 824 |
| Flag | 68.75 | 4 | 14236 | 1478 |
| Normalize | 99.12 | 5 | 17973 | 1820 |
| Maximum | 66.31 | 3 | 11120 | 932 |
| Failure count | 89.24 | 3 | 10825 | 1191 |
| Headings | 53.83 | 2 | 6814 | 612 |
| Revenue | 97.97 | 2 | 6802 | 706 |
| Identifiers | 77.30 | 5 | 17336 | 1255 |
| Log count | 122.80 | 3 | 10756 | 911 |

Totals: 903.65 case-wall seconds, 14 semantic reviews, 33 supervisor model calls,
117126 input + 11194 output = 128320 supervisor tokens; 1628 settled events.
Worker token usage is not included. Silence does not mean no model usage.

Receipt: `build/quiet-ten-352d317-20260913/summary.json`; SHA-256
`0e4e51e6afdc96e057ed0434de1e3d6955a1d365efbb6bde147aba370cef01fb`.
Runner hash: `694f9f93e874d6f5844f89408d2d856c1263cfb47aac8105230bd70d647b8209`.
Completion-fence hash: `261767e9f0d9c236bb43e1503ef1f439c0dd50548a14793c5f3094cd510186a7`.
Exit 0; owned OpenCode server exited; isolated profiles, task files, journals,
worker messages and receipts retained. No unrelated process was terminated.

These are live source-Pipeline behavioral controls, NOT desktop-supervised
cases, a representative general coding score, a Codex ten-case result, a
baseline comparison, or the formal four-arm benchmark. They measure restraint
on small public artifact tasks, not intervention precision on failing work.
Prior failed batches remain failed and are not combined into this result.

## Rebuilt installed package and native checks

Full sidecar, TypeScript/Vite, Rust, MSI and NSIS build passed. Three frozen
bridge lifetime tests passed in 8.89 seconds. Package extraction/inventory
verification passed first attempt: release_ready true, zero blockers.

Receipt: `build/pex-package-receipt-352d317.json`; SHA-256
`20920f07091f2b8e3395c7697af56ea734a2e571619995fa7f1158d6080db986`.

Retained in `build/release-candidate-352d317/`:

| Installer | Bytes | SHA-256 |
| --- | ---: | --- |
| PEX_0.1.0_x64-setup.exe | 101669843 | `9a6bdca0641564d6f066577d736277a22a86cfb461f85d5e3e352384b52c2149` |
| PEX_0.1.0_x64_en-US.msi | 114466840 | `ab7dd890175f31de35808f2c7dc6702ad73754490b513bb48c10135a2eaac4e9` |

Silent installer exit 0. Installed desktop hash matches extracted executable:
`890ca259c292a183c446fc24d757d8c1d81c58f213e9a8c73ccba7d5de11729a`.

Observed through Windows computer use, confined to PEX:

- Startup reached canonical Home without a bridge error. Zero working agents;
  the old Cursor row no longer falsely inflated the working count.
- Companion settings show exactly Pex and Von; saved Von / scale 1.00 / hidden
  preference survived installation. Von rendered transparently when shown.
- Dismissing the status bubble left Von visible. Hide remained fixed at the
  same location, hid the pet independently, and Settings confirmed hidden.
- Supervisor settings retained Muse Contributor Free, the Zen endpoint, the
  three-dispatch cap, and a write-only OS-vault credential (not exposed).
- Inspector's canonical refresh completed and correctly retained uncertain
  overall completion for the older bf5a25b recovery's unchecked criterion.
- Native Ask PEX answered that the selected OpenCode worker was stopped on
  persistent goal "Installed bf5a25b two-stage recovery". No worker command.
- Normal Alt+F4 shutdown left no PEX desktop or bridge process running.

A 30.2-second settled Inspector sample (seven samples, ten PEX-owned process
IDs, other workers excluded) measured 342.17–346.46 MiB private memory and
17.8% of one core, approximately 1.48% aggregate across 12 logical processors.
This is bounded process sampling, not a leak test, long soak or comparative
performance result. The ten-case worker run was active separately.

## Remaining native finding — not fixed by this acceptance

Selecting the old bf5a25b recovery displayed its previous CRLF correction under
"Latest meaningful progress" and in the Home bubble, while the latest decision
correctly said Stayed Quiet and described the repaired files. This stale copy
is misleading. Do not call the UI perfect. Trace the display projection and
event provenance; preserve the real worker transcript and audit, and add a
regression before changing it. No source edits occurred during the live batch.

Public RC1 remains the older release; these new installers are local. This run
does not redeploy AgentCore, rerun Codex recovery, complete the broad offline
suite, publish a video, or submit Devpost. The persistent goal remains active.
