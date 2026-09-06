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
a new whole-suite result. Fresh clean-source/live results are recorded below.
Do not replay a mutation against run-08 merely because its earlier result failed.

## Fresh clean-source gates — `5ff58f6`

Repair `5ff58f6271955eb24970d2d3f84609c0fafc92f6` was reviewed, committed and
pushed. The reused tracked-clean detached `pex-verify-84d9bd3` then ran eight
affected files with strict thread warnings, live flags disabled and provider/AWS
credentials removed: **231 passed in 271.46s**, no failures/errors/skips. Root
checked source, XML totals and SHA-256
`F9D0547A944D1A8C7AE287B73A5C8F47E24511F66381A4285AD96AB5EDE311A3`;
receipt `build/pytest-focused-5ff58f6.xml`. Locked sync with AgentCore extra checked
114 packages. Separate clean live worktree also passed 33 binding unit tests before
its live trigger. Neither gate is a new full-suite run.

## Live run-09 — independently reviewed pass

Exact source above; clean detached `C:\Users\JosephMayo\Projects\pex-live-5ff58f6`
(locked sync: 113 packages). Dedicated background bridge session83942 / PID11200 /
port7434, private `build/shared-demo-home-09`, no auto-attachment. Exact free Muse
checked before origin/goal/grant. No paid fallback, AWS operation or native input.

New independently operated worker `01a077a0-6751-7670-9fd7-9efef17d68ae`,
workspace `C:\Users\JosephMayo\pex-live-demo\workspace\shared-code-20260906-09`.
Warm-up `01a077a0-6800-79b2-8cdf-e34ac7c70bf7`; controlled initial turn
`01a077a1-fcd0-7140-a80d-bb02bca1d771`; goal
`goal_61775a0269a64632a09b39dcc85b1f8a`. Requested Spark, on-request,
workspace-write, no network. It implemented the function, only read its file via
shell, and honestly said tests were not run. There was no initial pytest result.
PEX had ordinary goal criteria/files, not an expected action or answer.

PEX inspected workspace/recent events, minted the scoped PYTEST probe, and made
a real Strands decision approved by its independent verifier. Exactly one
REQUEST_VERIFICATION was sent:
`intervention_ce7902f9fe5b7bc7385f4432d3ebb2fd8d1a1388`. Local binding generated
the scoped message. Same worker resumed as turn
`01a077a2-a8e8-7461-87eb-4a1f7a7afec4` and ran the standalone full suite:
`C:/Users/JosephMayo/Projects/pex/.venv/Scripts/python.exe -m pytest -q`.
Observed command event
`codex-shared:8d369ba562b876fd992f818d91ba73ce7e08c5a8a410a0f5511eda5a2ec47831`
has `process_state.pytest`: exact fixture execution cwd, exit 0, four passed, and
actual output `4 passed in 0.05s`. Its raw reference identifies that exact turn.
This typed result is within a SHELL event, not a separate TEST event, and is not
in `metadata.pytest`.

Outcome became `goal_evidence_supported`, `helped=true`; next real Strands action
was NOOP, `intervention_63f2cdda9fe09ea802a4f43da92f2be3098c5471`. Probe
`verification_probe_4e6e0d0b2ffe43649dd41f53656247868a229d6f` and execution receipt
bind the same goal/session/workspace. Independent audit checked immutable delivery
scope, all four outcome events/raw refs, zero initial typed pytest results,
unchanged tests, one request and one final NOOP.

Aggregate model usage: request 4 calls (includes 2 verifier calls), 19,630ms,
16,074 input / 1,563 output tokens; NOOP 1 call, 5,571ms, 4,145 input / 558 output.
Do not add verifier usage again or equate model calls with all HTTP attempts.
No measured productivity or benchmark uplift is inferred.

Root read worker: idle, three completed turns, no errors. Explicit revoke/detach
succeeded, `worker_stopped=false`; terminal enabled/effective-enabled/connected
false. Terminal receipt in `build/shared-demo-client-receipts-09/`:
`capture-20260906T165417100025Z.json`, SHA-256
`9F28070C91662D8D8190B3C47A05AFADFE27962348C7BBD6D43E10F7C859EBDD`.
Independent root `pytest -q -p no:cacheprovider`: four passed in 0.02s. Test hash
remains `3E45678C54AF0AA4B8D8E5EA918DE66B1B50380A709BAC1A013B23BB8E10A3A5`;
implementation hash `54D97AF5A876BB2CC2AE8E09E8251D4CD76387CBC7CA916C5A989ED6FD79CE75`.

Run-08 remains failed. This new controlled case proves scoped worker-mediated
evidence gathering followed by a verified quiet result. It does not prove
independent sandbox execution, ten varied quiet tasks, cross-harness behavior,
current installed UI, AgentCore deployment or fair four-arm benchmarks.
