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

## Exploratory08 measured result and prospective correction

08 produced18 validated real worker responses (baseline10, PEX8), recorded in
current-run typed evidence. Supervisor calls were0; neither arm received a final
protected grade. Baseline exhausted its conservative cash reservation envelope,
not task acceptance:41,701,500 nanoUSD charged left less than319,488,000 required
for its next request. The PEX arm suffered a completed read-only SDK ConnectTimeout
while reading a public source file; the generic bridge then poisoned subsequent
tools and the public observation, preventing monitor review. Both owned VMs were
stopped. No benefit/task-success claim is supported by this incomplete comparison.

The narrow fix exempts ONLY a completed, non-cancelled read/list task with actual
httpx.ConnectTimeout. It returns a visible read error and does NOT auto-retry,
reset another poison flag, change route, or permit pending/mutating uncertainty.
Commands, writes, create and unfinished/cancelled tasks remain fail-closed.
45 focused tests, including actual SDK serialization plus subsequent successful
read and mutation/cancellation poison, passed.

The next independently frozen allocation is375m nanoUSD per worker and separate
350m supervisor overhead. Legacy worker ceiling and per-call reserves remain
unchanged; only the NEW supervisor ledger supports its exact historical659,514,900
seed plus350m fresh allowance. Old ledgers cannot reopen under changed limits.
With all806,031,900 prior provider liabilities retained, its prospective ceiling
is1,906,031,900 (under$2). Nine focused accounting/composition tests passed. This
is not new spend authority or a guarantee of all12requests under any token usage.


## Exploratory09 incomplete controller lifecycle

09 produced12 validated baseline worker HTTP200 responses (96,440 input and
15,183 output tokens), charged47,151,600 nanoUSD. No PEX worker or supervisor
ledger rows were present at the final local observation. No final protected grade,
exact candidate export or controller report was persisted, so this is not a
completed comparison and does not establish task failure, success or PEX benefit.

The already-dispatched manager session later returned Unknown process id without
terminal output. The cause is unproven; a read-only poll denial does
not establish why the process ended. In particular, per-exec isolated /proc absence
cannot prove that another invocation's controller is absent. The append-only
private correction preserves that qualification rather than rewriting evidence.
Canonical authoritative history/active reads after manager-session absence found
only its baseline creation, a provider killed event, and empty filtered active
inventory. All raw ledgers remain unchanged, including its uncertain second-create
reservation; no automatic accounting release or billing inference was made.

The consumed09 gate is closed. No replacement, old-claim replay, alternate route
or new resource was started. A stable native-terminal design must first qualify
its own ordinary environment without importing another runtime's proxy values;
that design is not yet an admitted run or an inference result.

## Prospective private per-arm recovery evidence

The closed composition now publishes exact validated candidate-export bytes and
actual grade reports privately, including inconclusive reports without invented
scores. Each arm's status, phase receipts, immutable selected wire-receipt rows
and owned cleanup result are fsynced and atomically published before another
sandbox prepare/create. These are explicitly partial-pair artifacts, never a
standalone complete comparison or PEX-benefit assertion. They do not enter model
context, change task/grade inputs, extend budgets, replay an arm, or alter routes.
A publication failure prevents starting the next arm; owned cleanup still runs.

62 focused authored tests plus10 subtests passed. The actual CLI/SDK-serializer
mock-wire regression raises a simulated controller interruption at second create
and proves the completed baseline's exact captured bytes, scripted grade,12 wire
receipts and confirmed release were already persisted, despite no global report
or PEX-arm artifact. Scripted scores are not live results. Separate atomic-write
tests cover privacy, complete publication, nonreplacement and fsync failure.
The one720-second stdlib continuity fixture also completed with72 durable progress
records and a real exit marker, without network, keys or early PTY polling. That
fixture does not establish the cause of09 termination, future network/SDK process
stability, or any model/provider permission. No further paid run was started by
this change; the source dispatch gate remains None.
