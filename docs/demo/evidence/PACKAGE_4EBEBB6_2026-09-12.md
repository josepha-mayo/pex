# Agent-harness MVP release candidate

Source commit: `4ebebb6577029e7370f0e67d58bf35512cf9dfec`.

The repository was clean and equal to `origin/main` before the release build.
Rust 1.97.1 (`x86_64-pc-windows-msvc`) and two Cargo jobs were pinned. The
known optional Strands Cedar-extra warning appeared; PEX does not invoke that
optional handler. PyInstaller, the production Vite build, optimized Rust link,
WiX MSI and NSIS generation all completed with exit 0.

## Product change in this candidate

Home now presents OpenCode and Codex as the primary agent harnesses even before
the first live worker is connected, labels whether canonical local state is
still being checked, renders the companion at a readable scale, and uses a
stronger but restrained panel/background hierarchy. It retains exactly Pex and
Von. The provider, credential, worker-control, Strands, AgentCore and policy
paths were not changed.

The complete desktop contract suite passed 292 with one intentional Windows
symlink skip, and the production frontend build passed 71 modules. A fresh
1280x720 production preview was inspected: the harness labels, checking state,
transparent Pex asset, metric labels, first-run guidance and settings route were
all visible without horizontal overflow. This is rendered-browser corroboration,
not installed native-window interaction acceptance.

## Installer artifacts

- MSI: `build/release-candidate-4ebebb6/PEX_0.1.0_x64_en-US.msi`
  - 114,495,512 bytes
  - SHA-256 `c9501786e5edd0f9fbda97be17b7891477a5c56d8d80aa5903297e32eba0c8ed`
- NSIS: `build/release-candidate-4ebebb6/PEX_0.1.0_x64-setup.exe`
  - 101,675,193 bytes
  - SHA-256 `f92805c7a8f27c901a108fd7488dd0dd5343d4424ff9815538755ca962511635`
- Packaged bridge executable:
  - 34,459,515 bytes
  - SHA-256 `d034ae01928067c0ab652a5598c33ef0c87ff5a02a768b9e6d649c8f8a779661`

## Exclusive package verification

`npm --prefix apps/desktop run verify:package -- --receipt
build/pex-package-receipt-4ebebb6.json` completed with exit 0,
`release_ready:true` and zero blockers. The receipt binds source commit
`4ebebb6577029e7370f0e67d58bf35512cf9dfec`, release-input SHA-256
`349946667912bd2619c66dd929b4ae02af81cf9ef15cab4e07fc3324c2dbd203`,
sidecar-input SHA-256
`15773c7f0cb130609d5240de99141cdaa19f448b0684fe82e77d2fceec0bc0a3`
and canonical desktop SHA-256
`d44f35282b938314b60c8c25e80f1aea92d9f88e6fe6eebfbe37c0e7ccbbea63`.
The 1,546,513-byte receipt has SHA-256
`986f52279454da6163d1455a5cb17c780c97eb9ec9984a2fe9940639ea15b030`.

## Packaged bridge checks

The headless packaged-settings smoke passed authenticated supervisor read and
bridge identity, returned Zen `muse-spark-1.3-contributor-free` first, retained
the three-dispatch default, attached no worker, made zero provider calls and
used no cloud reasoning. Its 429-byte receipt has SHA-256
`bdf6ad6ddac1ab96be80c5d3298f013a850816ff567daa0ec9c40669ae7779fe`.

The opt-in frozen-bridge lifetime contract then passed 3/3 in 27.12 seconds.
It covers both bootloader termination paths and the standalone bundle inventory,
which returned exactly Pex and Von.

## Claim boundary

This is the newest installable, internally verified candidate. It does not prove
installed native overlay interaction, long-duration leak freedom, a fresh-machine
install, a frozen comparative benchmark, or an AWS AgentCore deployment. Live
OpenCode/Zen/Strands recovery and quiet behavior remain established by the
separate current-source behavioral pair because product code from that source
through this candidate is unchanged outside the Home presentation and read-only
resource observer.
