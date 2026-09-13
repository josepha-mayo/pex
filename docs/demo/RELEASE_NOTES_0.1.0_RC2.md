# PEX 0.1.0 RC2 — Windows judge build

Draft release notes, not a published release. Built from
[32a0499](https://github.com/josepha-mayo/pex/commit/32a0499e4af7f4950c3bd3d27cdf5ee1762aa6b4).

This update adds a larger, crisp flat cat logo and shows recorded supervisor
provider, model, call count and token usage in Inspector when available. It
retains the two companions, Pex and Von, Zen BYOK, OpenCode and Codex App Server
support, and Strands supervision with local evidence verification.

Download `PEX_0.1.0_x64-setup.exe` for the recommended Windows installer, or use
the MSI alternative. These installers are unsigned.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| PEX_0.1.0_x64-setup.exe | 101672562 | `1e60c0ea6ac3f1da5a75b5764778c01400c5c0e40f27b100cafdaa87e4a25688` |
| PEX_0.1.0_x64_en-US.msi | 114479128 | `22c379d9318ad94b1fce6c4e5cdeb283908f94546ea8a231c17b70c53433b564` |

Both package inventories passed verification. The installed NSIS desktop hash
matched its receipt; Home, Inspector, Ask PEX and pet Hide were checked natively.
Inspector visibly shows the correct model and token usage for the retained live
review. Desktop checks passed 299 tests with one Windows symlink skip; the
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
acceptance test, not a pass. Source follow-up fixes Markdown-path parsing and
timeout presentation; those changes are not yet installed in this candidate.
Short resource samples are bounded evidence, not long-duration freeze clearance.
AgentCore is implemented and locally
tested, not AWS-deployed. Cursor is observe-only in this MVP. The formal
benchmark remains unfrozen, with no comparative productivity score claimed.

RC1 remains available with its original artifacts.
