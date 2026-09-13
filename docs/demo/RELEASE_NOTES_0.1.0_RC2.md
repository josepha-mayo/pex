# PEX 0.1.0 RC2 — Windows judge build

Draft release notes, not a published release. Built from
[0ea2639](https://github.com/josepha-mayo/pex/commit/0ea2639fb9e8c20df413b18843d7056610af9b03).

This update adds a larger, crisp flat cat logo and shows recorded supervisor
provider, model, call count and token usage in Inspector when available. It
retains the two companions, Pex and Von, Zen BYOK, OpenCode and Codex App Server
support, and Strands supervision with local evidence verification.

Download `PEX_0.1.0_x64-setup.exe` for the recommended Windows installer, or use
the MSI alternative. These installers are unsigned.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| PEX_0.1.0_x64-setup.exe | 101667761 | `ba170b74edbb6a7a381f78e1ff360e175462baef23eace63e4192100d2d7074f` |
| PEX_0.1.0_x64_en-US.msi | 114466840 | `b97b932bb7e12e0832d7e2303981217c10a89a2a01d785aa9887cb69727acb0a` |

Both package inventories passed verification. The installed NSIS desktop hash
matched its receipt; Home, Inspector, Ask PEX and pet Hide were checked natively.
Inspector visibly shows the correct model and token usage for the retained live
review. Desktop checks passed 300 tests with one Windows symlink skip; the
packaged authenticated settings smoke passed with zero provider calls.

Follow the [judge guide](https://github.com/josepha-mayo/pex/blob/main/docs/JUDGE_TESTING.md)
and [recording setup](https://github.com/josepha-mayo/pex/blob/main/docs/demo/SECOND_LAPTOP_ACCEPTANCE.md).
Supply your own supervisor key; credentials are not bundled.

The retained live OpenCode demonstrations show one same-session correction for
a controlled incomplete stop and no follow-ups for correct completion. A fresh
installed `103f4ec` recovery also passed, exposing the UI receipt-mapping bug
fixed in this build. The supervisor and adapter code is unchanged; the repaired
UI was tested against that retained receipt, not a second new worker run.
The stationary Hide control and independent message dismissal passed on the
installed `32a0499` package. A fresh native quiet test on that package produced
correct files but its independent verifier timed out: it is a failed quiet
acceptance test, not a pass. This candidate installs the subsequent Markdown-path
parsing and timeout-presentation repairs. The old failed review now visibly says
Review Incomplete. A fresh source-level Codex recovery/quiet pair passed on this
revision; see [paired evidence](evidence/LIVE_CODEX_PAIR_0EA2639_2026-09-13.md).
The fresh installed [OpenCode quiet check](evidence/NATIVE_0EA2639_QUIET_2026-09-13.md)
also passed: exact files, real Strands NOOP, zero corrections. Overall completion
remains uncertain for an unchecked unstructured requirement. Intermediate
OpenCode lifecycle display lag remains a known limitation.
Short resource samples are bounded evidence, not long-duration freeze clearance.
AgentCore is implemented and locally
tested, not AWS-deployed. Cursor is observe-only in this MVP. The formal
benchmark remains unfrozen, with no comparative productivity score claimed.

RC1 remains available with its original artifacts.
