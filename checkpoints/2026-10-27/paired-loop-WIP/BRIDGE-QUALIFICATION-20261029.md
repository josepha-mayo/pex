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
