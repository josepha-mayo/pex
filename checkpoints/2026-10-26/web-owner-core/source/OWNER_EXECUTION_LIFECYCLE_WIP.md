# Owner execution lifecycle projection — WIP, authored verification only

The existing budget/infrastructure/cleanup summary remains intact. A separate
contract gap was reproduced: a recorded platform denial or unresolved create
was previously reduced to generic unavailable evidence.

The explicitly configured, server-owned redacted event stream now accepts
`platform_denied` and `create_outcome_uncertain`. Its optional typed `lifecycle`
projection keeps execution denial, allocation uncertainty and cleanup uncertainty
independent. It never imports runtime databases, private reports, raw errors,
sandbox IDs, credentials, grades or monetary amounts. Existing event streams keep
their original response shape unless these new lifecycle events are present.

The owner UI explains that denial is not a task failure, a sandbox allocation may
exist, cleanup can remain unconfirmed, and uncertainty is not an automatic refund
or retry authorization. Unknown worker counts remain null/not reported, not zero.
Contradictory resumed work/success after unresolved denial/allocation fails closed.
Valid goals and sessions remain visible; failed refresh still clears cached rows.
No resource action or retry button is introduced.

The `.authored.events.jsonl` fixture and companion `.authored.json` workspace in
`apps/desktop/tests/fixtures/ownerDeniedCreate*` are synthetic. A backend test checks
the real event projection against that same browser fixture, which the built-owner
DOM regression renders. They are not exports or reinterpretations of any real run.

Verification on the final production source bytes:
- Full desktop `npm test`: 491 passed, including TypeScript/build and owner DOM.
- After adding the shared fixture: all 38 owner tests passed again.
- Owner backend family: 84 passed with the existing frozen Python environment.
- Changed Python files: Ruff lint and format checks passed.

This is code/test qualification, not deployment, real inference, authenticated
provider cleanup proof, or a measured PEX benefit. Actual runtime pair facts and
closed execution gates are unchanged. The application does not automatically
publish a private interrupted run into an owner event stream; an operator must
explicitly configure an appropriate redacted, server-owned source.
