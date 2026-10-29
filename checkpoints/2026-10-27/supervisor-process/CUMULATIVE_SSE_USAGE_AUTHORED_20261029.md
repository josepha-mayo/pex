# Cumulative SSE accounting parser — authored qualification

Supports bounded monotonic per-choice cumulative usage without treating interim
counters as settlement authority. Every non-null usage record is validated for
integer bounds, sums, stable prompt count, monotonic completion/details, and
consistent previously observed prompt details. A finish-frame usage count freezes
those observed counters. Final cache-detail fields may first appear in the receipt.

Settlement still requires one exact-model/same-id stream, one finished choice,
exactly one distinct empty-choices usage record after finish, and [DONE]. Truncated,
conflicting, duplicated, after-finish or after-terminal data retains the complete
reservation. Legacy final-only usage remains supported. No budget, price, model,
request admission, approval, or ledger migration behavior is changed.

Fresh local focused qualification: **72 authored tests passed**. The new structural
fixture is hand-authored with synthetic counts/reasoning text; it is not a provider
response, inference benchmark, cost-saving claim, or evidence of a successful task.
No raw requests/responses, private diagnostic artifacts, credentials, or databases
are included. Historical diagnostic ledgers remain unchanged.
