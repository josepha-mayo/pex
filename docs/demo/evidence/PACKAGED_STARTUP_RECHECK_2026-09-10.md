# Packaged startup recheck — 10 September 2026

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
