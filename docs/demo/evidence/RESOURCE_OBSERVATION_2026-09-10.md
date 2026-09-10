# Thirty-minute packaged resource observation

**Completed, exit 0:** 180 sequential samples, 1801.14 measured seconds.
The desktop binary matches package `06c6b73` (product `97e84d4`): SHA-256
`26b10e96b175a3c3e5a175e3dcb1963c10177d77fcdc513d93d0a4f9be16cdd2`.

Sampling ran from 10:16:53.799 UTC to 10:47:14.506 UTC on 10 September 2026.
Elapsed wall time includes enumeration gaps; CPU percentages use the measured
intervals only. The same PEX root PID/start-time identity was checked before
and after every sample. No application input, model invocation or process
termination was issued by this observation.

| Measurement | Result |
| --- | --- |
| Samples retained | 180 of 180 |
| Measured interval total | 1801.14 seconds |
| Attributed CPU time | 31.026 seconds |
| Average CPU, one-core denominator | 1.72% |
| Summed private memory range | 342.4–347.5 MiB |
| Attributed surviving processes per sample | 11 |

This is ancestry-based, read-only attribution. Processes must survive an
interval with the same start time to contribute. Brief-lived processes and
time between intervals are not counted; this is not whole-PC CPU usage.

## Visibility and responsiveness

PEX was **minimized at the post-observation inspection**. Visibility was not
sampled during the intervals, and other PC activity was not controlled.
Consequently this must not be called a foreground-animation or active-worker
stress test, nor compared causally to the earlier visible-UI resource numbers.

After sampling, Windows reported the same process responsive. Computer use
restored only PEX, displayed Settings → Connections, returned Home, selected
the recorded OpenCode proof session and opened Inspector. All navigation
responded. Inspector initially showed pending canonical reads, then completed
refresh and displayed one of three review dispatches remaining, with two
reserved. No worker follow-up, setting mutation or new proof was submitted.
The recorded worker text and historical NOOP are not a newly executed recovery.
PEX was left open on Inspector; the desktop overlay remained hidden.

## Retained evidence and limits

Local receipt with every aggregate sample:
`build/pex-resource-30min-06c6b73-20260910.json`.
SHA-256: `273471dad7d3c1ab671dc97a5a04f874f86757497cd6420dfeea6d15861ef823`.
The sample sequence and CPU/time/minimum/maximum totals were independently
recomputed from all 180 records before writing the receipt.

This strengthens bounded background-resource and post-observation navigation
evidence. It does **not** prove a fresh Windows-user installation, long-running
foreground workload stability, causal resolution of the old whole-PC freeze,
formal benchmark results, cloud deployment, recording or submission.
