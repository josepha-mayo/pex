# Packaged startup recheck — 10 September 2026

## Later verified result

The unpacked runtime repair at `be67a91` opened the native desktop without
Retry. Trace `ready` was 5.109 seconds after Python entry, excluding prior
process launch. A bare release Cargo build initially produced a blank development
URL; rebuilding with `tauri/custom-protocol` corrected that mistake. Both
companions were transparent; dismissing the bubble and hiding the pet worked
independently. Von was restored as the selection, with the overlay hidden.

Product `dbc141a` was subsequently rebuilt using `npm run tauri -- build`, exit
0, producing MSI and NSIS. The native selected-session Ask regression also
passed. Verifier `d1da140` checked both bundles with no blockers, including all
2,375 bridge runtime files and exactly two pets. The first verifier run failed
on temporary-directory cleanup (EPERM); the verifier now records cleanup errors
instead of throwing before writing its receipt. The subsequent run exited 0.

Receipt: `build/package-d1da140-20260910.json`.
SHA-256: `6394c80025cbdf7ebc05742c3e7e2b995b8f9e0aeb033c2c3009885f8d0ee97d`.

These results do not prove prolonged stability, installation on a fresh Windows
profile, publisher identity (installers are unsigned), or complete submission
readiness. The original failed attempts below remain evidence.

The user explicitly resumed PEX-only computer checks. Existing two-pet package
`4de1db8` was tested before rebuilding. No unrelated app was closed and no live
model call was made.

## Observed failures

- The first computer-control launch request timed out with no PEX window or
  process subsequently found. It was not counted as a native startup result.
- A single retry of that launch opened PEX. Desktop process start was 18:00:10
  Lagos; its bridge process appeared at 18:00:36. The native window reported the
  bounded bridge identity timeout. No startup trace was present at that point.
- One native **Retry bridge** also timed out. Its bootloader process started at
  18:03:27 and Python payload process at 18:04:00. The fixed-phase trace reached
  `app_import_ready` at 11.031 seconds after Python entry and `routes_ready` at
  16.000 seconds. It did not reach `store_begin`. These offsets exclude extraction
  and Python runtime initialization before the trace begins.
- PEX was closed normally with its own title-bar Close button. No recursive
  process cleanup or security-setting change was used.

## Isolated packaging measurement

Executing the packaged `pex-bridge.exe --help` took **68.92 seconds**, exit 0,
measured with a PowerShell Stopwatch. This path exits at argument parsing,
before app imports, database recovery, server startup or model configuration.
The elapsed time includes process launch, one-file extraction/runtime startup,
printing help and normal exit/cleanup; it is not solely extraction time.

The existing PyInstaller package inventory lists 2,389 entries totaling
144,234,067 bytes of source payload files, including its compressed Python module
archive. This is not installed RAM usage or a claim that every byte is extracted.

These observations establish a packaging/runtime-startup bottleneck under the
current machine conditions. They do not identify antivirus as the cause or prove
that the earlier database-recovery repair resolves this failure. The native
60-second deadline and identity/authentication checks remain unchanged.

## Experiment in progress

An isolated `--onedir` build was attempted under `build/startup-unpacked`, using the
same bridge entry point and package collection flags. This experiment is only
for startup measurement; it intentionally does not stage the pet assets and is
not an installer/release candidate. It exited 1 while `collect_all('keyring')`
was running: PyInstaller reported `SubprocessDiedError` after its isolated child
raised `OSError: [Errno 9] Bad file descriptor`. No unpacked performance result
is claimed. The canonical `4de1db8` executables and installers are unchanged.

The keyring `collect_submodules` step subsequently passed in isolation (28
modules). One retry of the same unpacked build is in progress. A machine-level
snapshot reported 12 logical processors at 100% load and 37,055,648 KiB free
physical memory. The timings above are therefore loaded-machine observations,
not a portable startup benchmark or evidence of RAM exhaustion. No unrelated
process was stopped or reprioritized.

## Follow-up offline checks

At source `0b005db`, the desktop suite includes runtime-tree integrity checks:
283 passed, one explicit Windows EPERM symlink-fixture skip, exit 0 in 106.34s.

`python -m pytest tests/unit/test_bridge_main_watchdog.py tests/unit/test_startup_trace.py -q`
returned 19 passed and one failed in 32.28s. The failure was the bootloader-parent
case waiting five seconds for its child to print `ready`, before terminating
either owned sentinel. An isolated rerun of that exact case passed in 21.75s,
exit 0, without code changes. Retain the initial failure: the rerun does not
prove a cause or clear packaged startup. No unrelated process was terminated.
