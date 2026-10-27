# Usage-schema observability — WIP live qualification

A real synthetic supervisor diagnostic returned HTTP 200 with the expected
response identity, but the usage shape was refused. Its full reservation remains
charged conservatively; no valid token usage or successful supervisor result was
claimed. The earlier receipt did not retain the rejected usage field shape.

Receipts now preserve at most 32 canonical field names and primitive type labels,
without values, token counters, nested content, model text or HTTP headers.
Secret-bearing objects are redacted completely. Missing/list/oversized objects
are represented by bounded markers. This aids diagnosis without logging secrets.

Accounting validation is NOT relaxed: unknown fields and missing counters still
refuse, and uncertain reservations are never refunded. Tests use authored HTTP
responses only. This does not establish the live provider's rejected schema or
fix interoperability; a subsequent authorized run must supply fresh evidence.

Nested diagnostic successor: only canonical names and primitive type labels in the two standard usage detail dictionaries are retained, bounded to32 fields each and one level. No values or arbitrary nested payloads. Actual cache-partition retry reached HTTP200 but refused invalid_usage_details; retained liability is USD0.4311126 including original workers and prior supervisor reservations, not an invoice. No paired benchmark or VM dispatch.
