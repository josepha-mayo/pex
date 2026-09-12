# Installed runtime evidence for package 79d4d18

Observed on 12 September 2026 against the exact unsigned NSIS candidate in
`build/release-candidate-79d4d18/PEX_0.1.0_x64-setup.exe`.

## Candidate and installation

- NSIS SHA-256 before installation:
  `e76389632460030d5f7aae5089ec9ced04b9c378c3b2256c3bf31fd9bc2dcd74`.
- The silent installer registered PEX 0.1.0 for the current user and installed
  `pex-desktop.exe`, `pex-bridge.exe`, `pex-cursor-hook.exe` and
  `pex-cursor-observe.exe` under the expected per-user locations.
- No PEX process or port 7420 listener existed before launch.

## Launch and bridge ownership

- First installed launch created one `pex-desktop.exe` and one child
  `pex-bridge.exe --host 127.0.0.1 --port 7420`.
- The first frozen-bridge trace reached `ready` in 15.297 seconds.
- `/health/live` returned HTTP 200 with the canonical PEX bridge identity.
- An unauthenticated privileged `/health` read returned HTTP 401 as required.
- A normal main-window close message exited the desktop, its owned bridge and
  the port 7420 listener in 2.976 seconds. Nothing survived.
- Reopen created exactly one bridge and one listener. Its trace reached `ready`
  in 7.703 seconds and the desktop remained responsive.

## BYOK configuration boundary

The installed profile reports provider `zen`, model
`muse-spark-1.3-contributor-free`, `api_key` authentication, an explicit
three-dispatch session limit, credential source `secret_store`, and a nonempty
secret reference. The key was not read, printed or copied. The immutable
packaged-settings receipt independently records authenticated identity and
settings reads with the same first catalog model and cap, with zero provider,
worker or AWS calls.

## Bounded stability probes

Across six foreground-idle samples over 25 seconds:

- desktop working set stayed at 35.5 MB and CPU stayed at 1.19 seconds;
- bridge working set stayed between 141.5 and 141.6 MB;
- bridge CPU rose from 16.64 to 16.83 seconds;
- every owned process remained responsive.

The live installed bridge then served 100 sequential `/health/live` requests:
100 succeeded, mean latency was 11.53 ms, p95 was 20.54 ms, bridge working-set
growth was 0.12 MB and CPU growth was 0.25 seconds.

## Honest acceptance boundary

This clears installation, bridge startup, authentication rejection, ordinary
owned-process cleanup, reopen and bounded runtime stability. It does **not**
clear visual/native interaction acceptance: the current Codex computer-control
runtime exposed browser surfaces only (`apps: []`) and could not bind the PEX
window. Home/Inspector/Deck/Settings layout, pet transparency and movement,
message dismissal, hide/restore, keyboard reachability and live OpenCode UI
attachment still require direct observation on this exact installed candidate.
No provider call, AWS deployment, release publication or submission occurred.
