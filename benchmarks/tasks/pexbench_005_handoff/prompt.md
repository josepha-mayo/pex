A previous maintenance session left a concise, public `HANDOFF.md` beside the code. Implement `event_mapper.map_event(payload)` from that contract; do not invent top-level field names or rely on an unavailable transcript.

Acceptance criteria:

- read identifiers from the nested `event` object and the nested `result` object;
- return exactly the keys `id`, `kind`, and `ok`;
- coerce `event.id` to a string;
- trim and lowercase `event.type`;
- set `ok` only for the case-insensitive statuses `ok` and `success` on `result.status`;
- drop any other keys; and
- raise `KeyError` when `event` is missing.

Treat `HANDOFF.md` as the durable contract and run the tests before finishing.
