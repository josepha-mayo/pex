# WIP clean-room asyncpool benchmark

Inspired by the real cancellation/dual-limit bug class documented at
https://github.com/aio-libs/aiohttp/issues/9670 . This is an independently authored
stdlib implementation task, not an aiohttp patch or copied implementation.

Public worker input: `public/` only. The reference and independent acceptance
suite are evaluator-only; never include them in model context or upload them to
a worker-accessible workspace while a worker is active. Reference and mutants
are authored qualification artifacts, NOT model-generated baselines/corrections.

`qualify.py` runs only the bundled AUTHOR-REFERENCE and deliberately altered
AUTHOR-REFERENCE mutants locally. It must not be repurposed to execute untrusted
worker candidates on the controller. Actual candidates still require approved
isolated execution. `heldout/run_grade.py` belongs after worker revocation there.

Freeze manifest/task/check hashes and equal worker budgets before each real
comparison. Report all attempts, monitor overhead and infrastructure timeouts.
The existing monitor can inspect captured public tests and immutable source but
cannot independently execute a newly invented check. No benchmark score, live
model success, exclusive monitor advantage or PEX benefit is claimed by this
package. Stockroom results and evidence do not apply to these new bytes.

No live adapter or provider/VM admission is enabled by this package.
