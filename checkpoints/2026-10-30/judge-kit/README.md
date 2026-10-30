# PEX judge kit — recorded evidence, not a live runner

Open `index.html` directly. No install, backend, network calls or credentials.
Use the tabs and filters; expand records to inspect sanitized counts, dates,
source references and hash subjects. Source links navigate only when clicked.

## Optional reproducible local test

Requires Python 3.11+; original author qualification used Python 3.12.14.
From this folder run:

    python3 wirepool/qualify.py

This executes only authored reference, starter and mutant code with stdlib
subprocess tests, writing local logs under wirepool/evidence. It never invokes
models, providers, workers, or an untrusted generated candidate. The authored
reference passed 8 public + 8 protected checks; all 10 authored mutants were
rejected. This is NOT a real PEX comparison or a quality-lift result.

## Honest scope

Asyncpool 13: baseline 8/8; PEX worker 8 calls; 2 real supervisor responses;
invalid final schema rejected; no verifier approval, correction or final PEX
grade. The linked protocol repair commit is subsequent source, NOT the run's
executed source. Its offline tests do not retroactively change the run.

Wirepool 04: 3 real settled baseline calls, interrupted before grading or monitor.
No comparison. Source/config identity is included as a hash, not private bytes.

Live inference needs approved credentials and isolated execution, frozen budgets,
actual runtime qualification, independent source review and real capture. The
latest Vercel qualification returned HTTP 402 fair-use resource block. No live
Vercel runtime or new PEX benefit has been verified. No credentials are required
or requested for this kit. The architecture diagram is illustrative.

No raw provider content, hidden reasoning, tool arguments, credentials, runtime
databases, browser state, screenshots or audio are included. Task/reference/check
sources were already published in the existing review branch. Publicly available
heldout checks are withheld from benchmark model context, not secret material.
