# WIP command-terminal bridge correction

Recovery05 created two verified VMs and completed both public setup sequences,
but both arms failed before CLI initialization. Its worker and supervisor
ledgers contain zero calls. Owned VM cleanup was confirmed. This is not an
inference benchmark result, task failure, score, or PEX-lift evidence.

The executed bridge unconditionally signaled a command after SDK `wait()` had
already acknowledged its end event. A signal response taking over the separate
one-second cleanup bound poisoned the bridge despite returning valid command
output. A direct regression and actual E2B 2.61 serializer mock reproduced this
fault before the fix (two failing tests). The live run did not retain the exact
signal exception, so timeout versus another transport exception is not proved.
SDK `kill()` returning `False` alone did not poison the old bridge.

The correction skips process signaling only after a validated terminal event,
including a nonzero `CommandExitException`. Unacknowledged commands still take
the bounded process-kill path and remain poisoned on uncertainty. Independent
owned-VM kill and stop confirmation are unchanged. Private diagnostics now
retain bounded exception **types** and scope-state flags, never raw exception
strings, command text, URLs, headers, output, or sandbox IDs.

Qualification: 42 focused authored tests passed, including actual CLI/SDK mock
composition, zero/nonzero terminal exits, delayed redundant signaling,
cancellation, wait/output-bound failures, cleanup errors, next-scope refusal,
and independent VM cleanup. These tests make no provider-cancellation guarantee.

The consumed gate remains closed. All eight historical full330s VM lifetime
bounds remain charged: 79,860,000 nanoUSD. Another fresh sequential pair would
peak at 138,682,500 nanoUSD, exceeding the approved 120,000,000 compute ceiling.
Provider liabilities remain 756,130,200 nanoUSD; no new model call was made.
No automatic retry, refund, top-up, alternate service, or model fallback.

## Subsequent recovery06 interruption and authoritative cleanup

Recovery06 received one execution control. A later **empty read-only output
poll** was rejected as if it were duplicate paid execution. The single permitted
read-only reconsideration returned unknown process ID. No second execution
control/create was sent. The host session disappeared without a terminal report;
this was not a proven provider denial. No causal link between the poll rejection
and host termination has been established. Its model ledgers remained empty.

Canonical management history later proved one exact-run baseline VM was created
and killed by the provider timeout; the genuine filtered active inventory was
empty. All nine creation events were accounted for, including the eight already
charged historical allocations. No cleanup DELETE or unrelated-resource action
was needed. The retained raw generic reservation was NOT refunded: cumulative
compute accounting remains 128,700,000 nanoUSD; provider liabilities remain
756,130,200 nanoUSD. The observed small physical lifetime over330s is retained as
an integrity note, not used as a billing-unit claim or credit.

A further existing-policy pair would peak at187,522,500 nanoUSD. The current
approved compute ceiling is140,000,000. Code now supports a prospective250m
immutable ledger/profile, but the dispatch gate remains None: this is **inactive
capability, not spending authority**.37 focused authored tests passed, including
closed-gate refusal and preservation of prior caps/reservations. A new exact
approval, independent literal Grant, fresh config and recording handshake remain
required. No actual inference success or supervisor benefit has been shown.

## Recovery07 local child-admission correction

Recovery07 completed both remote setups; the corrected command bridge remained
clean. Both arms then raised local `AdmissionRefused` before any model request.
Owned cleanup was confirmed and all costs were retained. The old run did not
retain its exact reason string. A production-local reproduction with the actual
CLI/configuration and current ordinary environment found the concrete defect:
ambient ALL_PROXY/all_proxy fallback aliases differ from HTTPS_PROXY, were
copied unnecessarily into the child, and the local guard correctly refused them.

The narrow projection now omits only those unused fallback aliases from the
child. Parent/global environment, pinned HTTPS_PROXY identity, approved CA path,
verification, endpoint and all mismatch/bypass refusals remain unchanged. Real
Bun1.4.4 TLS/CONNECT tests demonstrate HTTPS_PROXY precedence with distinct inert
ALL_PROXY aliases; CA/hostname failures still fail closed. No alternate proxy,
direct fallback, copied credentials/certificates or provider probe was introduced.

The same pure child-preparation function is now callable before any SDK/client,
claim or VM, and is rechecked in actual worker construction/execution. A local
preflight validates pinned files and runs the actual `opencode --version` command
(`opencode v2.1.4`) without inference. The trusted launcher must call it before
its claim/compute/client path; candidate preparation can run it without opening
credentials. Diagnostics retain allowlisted local reason codes, never raw errors.
66 focused tests passed, including actual CLI/SDK mock composition and five real
local Bun TLS/CONNECT cases. Actual-current-environment preflight also passed;
its original inherited-fallback projection reproduced the guard refusal. These
local results are not an inference success or supervisor benefit.
