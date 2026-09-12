# PEX 0.1.0 RC2 — Windows judge build

Draft release notes, not a published release. Built from
[949cb47](https://github.com/josepha-mayo/pex/commit/949cb47d32cb5ef3ee6080953eee270637c5632c).

This update adds a larger, crisp flat cat logo and shows recorded supervisor
provider, model, call count and token usage in Inspector when available. It
retains the two companions, Pex and Von, Zen BYOK, OpenCode and Codex App Server
support, and Strands supervision with local evidence verification.

Download `PEX_0.1.0_x64-setup.exe` for the recommended Windows installer, or use
the MSI alternative. These installers are unsigned.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| PEX_0.1.0_x64-setup.exe | 101671108 | `dc0ad2979f218bd11acc778f449a1656b2a42fdd2fbcceee9ee0657617b451d0` |
| PEX_0.1.0_x64_en-US.msi | 114479128 | `11b29b7b66cf627c3b9e675c2120ea97396ae4efe07a82165ab78b5ba2c37e9e` |

Both package inventories passed verification. The installed NSIS desktop hash
matched its receipt; Home, Inspector, Ask PEX and pet Hide were checked natively.
Inspector visibly shows the correct model and token usage for the retained live
review. Desktop checks passed 297 tests with one Windows symlink skip; the
packaged authenticated settings smoke passed with zero provider calls.

Follow the [judge guide](https://github.com/josepha-mayo/pex/blob/main/docs/JUDGE_TESTING.md)
and [recording setup](https://github.com/josepha-mayo/pex/blob/main/docs/demo/SECOND_LAPTOP_ACCEPTANCE.md).
Supply your own supervisor key; credentials are not bundled.

The retained live OpenCode demonstrations show one same-session correction for
a controlled incomplete stop and no follow-ups for correct completion. A fresh
installed `103f4ec` recovery also passed, exposing the UI receipt-mapping bug
fixed in this build. The supervisor and adapter code is unchanged; the repaired
UI was tested against that retained receipt, not a second new worker run.
Short resource samples are bounded evidence, not long-duration freeze clearance.
AgentCore is implemented and locally
tested, not AWS-deployed. Cursor is observe-only in this MVP. The formal
benchmark remains unfrozen, with no comparative productivity score claimed.

RC1 remains available with its original artifacts.
