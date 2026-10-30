# Public contract to independent oracle mapping

| Protected group | Already-public obligations | Main observations |
|---|---|---|
| 01 codec | §1 arbitrary fragmentation, grammar, null/nested/empty values, limits, encoder byte lengths | Literal wire bytes; every two-chunk split; NEED_MORE; values/exceptions |
| 02 pipeline | §2 error values; §4 ordered one-send pipeline, full drain, first error, return_exceptions, reuse | Literal command payload and replies; creation/write counts; subsequent response |
| 03 cancellation | §2 close on any BaseException; §4 no shielding/replay/stale reply | Events at accepted send and incomplete header/body/trailer/pipeline; close before new request; no active I/O |
| 04 waiter cancellation | §3 queued/assigned/factory-token cancellation, healthy handoff reuse, cancellation precedence | Cancel before recipient resumption; same Connection identity; next waiter progress |
| 05 factories | §3 in-progress reservations, factory exception/cancel cleanup, late factory after shutdown, no factory cancellation | Factory entry events and active count; original exception identity; returned transport close |
| 06 FIFO/close | §3 no barging, idempotent release, assigned healthy connection shutdown semantics | New arrival pre-readied before handoff recipient; lease ordering and identity; closing behavior |
| 07 failures | §1 malformed frame; §2 EOF/error/BaseException close, persistent decoder, no replay | Sentinel BaseException (not SystemExit), literal coalesced frames, write/close counts |
| 08 concurrent clients | §4 shared-pool ownership, queued cancellation has no send/other-lease close, eager validation/empty pipeline | Two clients gated on individual replies; unchanged counts for invalid/empty work |

Public tests exercise eight readable examples across the same four specification
sections. The protected suite differs in data/schedules, not secret requirements.
No exact exception message is required except text provided verbatim by server
error replies; no transport-private fields are accessed by implementation code.
Lease constructors/private pool state are never used by the oracle.
