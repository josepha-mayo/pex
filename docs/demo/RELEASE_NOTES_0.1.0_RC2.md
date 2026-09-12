# PEX 0.1.0 RC2 — Windows judge build

Built from [103f4ec](https://github.com/josepha-mayo/pex/commit/103f4ecddd72e1fc68dafac4fa4c2d17003c4263).

This update adds a larger, crisp flat cat logo and shows recorded supervisor
provider, model, call count and token usage in Inspector when available. It
retains the two companions, Pex and Von, Zen BYOK, OpenCode and Codex App Server
support, and Strands supervision with local evidence verification.

Download `PEX_0.1.0_x64-setup.exe` for the recommended Windows installer, or use
the MSI alternative. These installers are unsigned.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| PEX_0.1.0_x64-setup.exe | 101668055 | `4d48119e560423c00ecca6c4f764936b9c983b26d892f96c31f302b58cb45efd` |
| PEX_0.1.0_x64_en-US.msi | 114483224 | `ac9f6505a486ce989e10f9114e29a016b9e9a8e1788bb58e5c3d851ebbb44cdc` |

Both package inventories passed verification. The installed NSIS desktop hash
matched its receipt; Home and Inspector were visually checked, and ordinary
close removed the desktop and its bridge listener. Desktop checks passed 295
tests with one Windows symlink skip; packaged bridge lifetime checks passed 3/3.

Follow the [judge guide](https://github.com/josepha-mayo/pex/blob/main/docs/JUDGE_TESTING.md)
and [recording setup](https://github.com/josepha-mayo/pex/blob/main/docs/demo/SECOND_LAPTOP_ACCEPTANCE.md).
Supply your own supervisor key; credentials are not bundled.

The retained live OpenCode demonstrations show one same-session correction for
a controlled incomplete stop and no follow-ups for correct completion. The
supervisor and adapter code is unchanged since those demonstrations; they were
not rerun through this installed binary. AgentCore is implemented and locally
tested, not AWS-deployed. Cursor is observe-only in this MVP. The formal
benchmark remains unfrozen, with no comparative productivity score claimed.

RC1 remains available with its original artifacts.
