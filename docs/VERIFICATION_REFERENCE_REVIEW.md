# Verification reference binding — 6 September 2026

## Retained live failure, not a successful NOOP

Clean source `ee459f874a3a9c6e999a46ff18c6d0cfa2db1869`, existing dedicated bridge
7433 / PID3172 / session41691, `pex-live-ee459f8/build/shared-demo-home-07`.
The already configured local origin was reused without restart/rebinding.
New independently operated worker `01a07789-dc34-72e1-a282-2778ea86ac2c`
existed before PEX attached, in `pex-live-demo/workspace/shared-code-20260906-08`.
Warm-up `01a07789-dcbd-7690-bfc0-bbf1f787ca5b`; controlled implementation turn
`01a0778b-653f-7cb3-97ca-86db8182fe7b`; goal
`goal_c41934c071d24f06ba690e16bf467928`. Requested Spark, explicit on-request,
workspace-write, no-network. Operator checked the existing bridge's exact
`muse-spark-1.3-contributor-free` backend before goal/grant. No UI input.

The worker implemented the function correctly, only read `normalizer.py` through
shell and edited that file, then honestly said tests were not run. PEX independently
inspected workspace and recent events, recorded uncertain verification with a
bridge-minted PYTEST probe, and invoked real Strands plus verifier. Its original
durable planner decision was REQUEST_VERIFICATION with `{kind, probe_id}` exactly
matching the offered probe. The bridge required a full probe object and replaced
the request with NOOP / `verification_probe_not_bridge_minted`. No corrective or
verification message reached the worker. This is a failed behavior gate, not
successful restraint or completed verification.

Root inspected the original planner effect through SQLite read-only URI with
ignored `build/audit_run08_planner.py`. Do not infer the original proposal from
the final replacement NOOP's empty payload. Independently, an actual
`_action_from_proposal` roundtrip redacts canonical probe cwd/project values to
`<workspace>`, so requiring an unredacted full echo is also a reproducible mismatch.

Explicit revoke and detach succeeded; worker remained idle with two completed
turns and no errors. Terminal capture:
`pex-live-ee459f8/build/shared-demo-client-receipts-08/capture-20260906T162956835983Z.json`,
SHA-256 `8C2E869C40BFE45B924BFC88E9996CC46DE506592F90B59957ADC1EFAF76E6F2`.
Root later ran public pytest independently: 4 passed in 0.02s. That result was
not supplied to PEX and does not repair its failed evidence loop. Public test
hash stayed `3E45678C54AF0AA4B8D8E5EA918DE66B1B50380A709BAC1A013B23BB8E10A3A5`.

## Repair contract

The model selects an offered probe, not its authority. New
`services/bridge/src/pex_bridge/verification_actions.py` resolves only an exact
current `{probe_id, kind}` reference or exact canonical/redacted full echo.
The current local immutable probe supplies workspace, goal, session, event,
targets and bounds. Conflicting fields, missing references, foreign identities
and extra execution controls are rejected. No mutation of the original durable
model decision occurs. Every worker message is regenerated from the canonical
probe: correct reference IDs do not authorize unrelated model-supplied prose or
commands. Independent review caught that initial text-preservation gap; regression
tests now cover both reference/full-probe forms. The prompt documents the contract.

Policy, standing grant, workspace authority, delivery certainty, and actual
execution matching remain separate later gates. Semantic NOOP is never promoted
to verification. Protected `services/supervisor/src/pex_supervisor/loop.py` remains
untouched. This does not implement independent sandbox test execution: the
request goes to the existing worker, and PEX must observe a matching real result.

## Verification scope

Initial five-file gate passed 195 tests in 208.45s with strict thread warnings;
it predates the final canonical-text hardening. Final unit/supervisor/evidence
gate: 66 passed in 4.24s, including 33 binding tests. Independent final review
approved the production diff after the text repair; its strict focused gate
passed 10 tests (89 deselected), including an actual parser/pipeline/adapter
hostile-text case. Root inspected that assertion against the actual inbox.
Ruff and scoped diff checks passed. These are overlapping targeted gates, not
a new whole-suite result. Fresh clean-source and live replay remain open.
Do not replay a mutation against run-08 merely because its earlier result failed.
