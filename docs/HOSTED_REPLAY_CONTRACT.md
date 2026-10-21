# Restricted hosted replay: local API contract

Status: implemented and mock-tested locally; not deployed. **Real hosted replay
execution is unavailable.** This is a service boundary, not the hosted app.

`pex_bridge.hosted_replay.create_hosted_replay_app` constructs a separate FastAPI
app. It does not mount or import the bridge application, create its global store,
start adapters, expose operator routes, or open a listening socket. The default
runner is absent; every valid start request returns HTTP 503 with
`isolated_replay_runner_unavailable`. Catalogue inspection is not execution.

## Narrow HTTP surface

POST requests require the exact configured `Origin`. GET requests may omit it,
as normal same-origin browser fetches often do; an explicitly foreign Origin is
rejected for every method. Protected reads still require their bearer capability.
This is a same-origin design, not a permissive CORS proxy. Origin alone is not
authentication.

- `GET /api/replay/fixtures`: two explicitly allowlisted bundled fixtures, honest
  replay labels, and `execution_available` (false without a configured runner).
- `POST /api/replay/visitors`: empty body; issues a random ephemeral bearer
  capability. The server retains only its hash. No cookie or owner identity.
- `POST /api/replay/runs`: bearer required; exactly `fixture_id` and
  `idempotency_key`. Unknown fields, unknown fixtures, paths, inline fixtures,
  caller-selected goals, credentials and provider settings are not accepted.
- `GET /api/replay/runs/{run_id}`: bearer required; only the owning visitor can
  read it. Unknown and other visitors' runs both return 404. Expired bearer
  capabilities return 401.

The idempotency key is scoped to the visitor. Repeating it returns the same run
without executing twice; changing its fixture returns 409. Newly admitted starts
return 202 immediately and execute in an owned background
task, rather than holding a browser/proxy request open for the run duration.
Concurrent duplicate requests return the same run with 202. Clients poll the GET
run endpoint, which returns 200 with `running`, `completed`, or `failed` state.
Repeating a start after completion returns 200; repeating a failed start returns
503 with the same failure, never a second execution. The default unavailable
runner returns 503 before admission and never creates a background task.
`completed` describes replay execution, never acceptance verification or a live
worker. The status endpoint remains status-only. A separate ownership-protected
`GET /api/replay/runs/{run_id}/result` transports a bounded validated result when
the injected runner supplies one. Every run and catalogue fixture carries
`replay: true` and
`not_live_control: true`.

## Limits and isolation tested here

Defaults: 32 retained visitors, four runs per visitor lifetime, two concurrent
runs, 15-minute visitor lifetime, 30-second cooperative execution deadline and
2 KiB request bodies (including chunked bodies). Admission is serialized within
one process. Exhausted visitor-lifetime run quota returns 429 `visitor_run_limit`;
temporary concurrency pressure returns 429 `run_capacity`. Retrying an existing
idempotency key remains allowed after quota exhaustion. Quota-denied requests
are never queued or automatically retried with a new visitor identity.
Expired metadata is removed on the next authenticated or visitor
creation request; expiry is enforced before every protected read/start.
Execution deadlines also
respect remaining visitor lifetime. Late results are never readable with an expired
capability. There is no periodic reaper or persisted state.

The app owns a bounded task set independently of HTTP request lifetime. Lifespan
shutdown stops admission, cancels every outstanding task, drains runner teardown
and directory cleanup, then drops visitor state. This requires a long-lived ASGI
backend with lifespan support; it is not a durable queue and must not be placed
in an ephemeral frontend/serverless invocation. A frontend proxy can return each
short start/poll response independently of the runner deadline.

Each admitted run gets an unpredictable, separate directory with `pex-home` and
`workspace` subdirectories. These are removed after success, failure or timeout;
there are no retained receipt files or filesystem download endpoints. The injected runner
receives those paths and the server-selected fixture path. The service never
changes global `os.environ` to switch tenants. Tests use a stub that checks paths
and cancellation; **the stub does not run PEX or generate supervision evidence**.

## Required before any real execution or public deployment

An actual runner must launch a disposable, credential-free process/container with
its own PEX_HOME, database, workspace and remapped session/goal identities. It must
run the real deterministic PEX pipeline without adapter discovery, owner config,
provider calls or live workers. It must kill and reap the entire process tree
before returning, including cancellation. CPU, memory, disk, process, network and
hard wall-clock limits need enforcement outside Python: `asyncio.timeout` cannot
stop blocking code or a runner that suppresses cancellation. This module is not a
sandbox and must not be used with an untrusted or in-process bridge-global runner.

Real runner integration must verify isolated evidence and verdicts, cancellation,
resource exhaustion, expiry cleanup and crash recovery. Neither a fixture lookup
nor the stub's `completed` return is such verification. Cleanup errors or a server
crash can leave a directory; a real deployment requires an independent reaper.

Hosting additionally needs approved infrastructure/cost limits, TLS, protected
service-to-runner authentication, trusted immutable fixture packaging, edge abuse
and request-time limits, and durable/shared admission if multiple processes are
used. Anonymous visitor issuance is bounded storage, not a distributed rate limit;
a client can exhaust available slots or spoof Origin outside a browser. Keep
capabilities out of logs and browser URLs. No production UI integration, deployment,
security certification, or resource enforcement is claimed here.

## Local verification

From the repository root, using an already prepared environment:

    mkdir -p build/hosted-replay-home
    PEX_HOME="$PWD/build/hosted-replay-home" ../pex-venv/bin/python -m pytest -q tests/unit/test_hosted_replay.py --basetemp=build/hosted-replay-tests
    ../pex-venv/bin/ruff check services/bridge/src/pex_bridge/hosted_replay.py tests/unit/test_hosted_replay.py
    ../pex-venv/bin/ruff format --check services/bridge/src/pex_bridge/hosted_replay.py tests/unit/test_hosted_replay.py

For a normal synced workspace, use `uv run python -m pytest` with the same test
path and workspace-local `--basetemp`. The sibling environment path above records
the exact environment used for this local check, not a shipping prerequisite.

## Separate local job increment

`docs/REPLAY_JOB_CONTRACT.md` describes a real deterministic replay job tested
locally for both curated fixtures. It is intended to execute inside an externally
secured sandbox, not to provide that sandbox. It is not wired as an executable
public runner: default hosted starts still return 503. The GET
run status contract remains unchanged; a separate result endpoint now accepts
only the job's validated bounded result schema from an injected runner.

## Bounded result transport

An injected trusted runner may return `ReplayJobResult` from `pex_bridge.replay_job`
or the supported `"completed"` status-only sentinel. The service revalidates model
fields, requires exact true replay labels, matches fixture identity to the admitted
run, rejects unknown completion/verification status labels, and enforces the
16 KiB serialized byte cap. It stores only immutable encoded JSON, never the mutable runner model or arbitrary runner dictionaries. Invalid,
mismatched or oversized results become sanitized failed runs with no result body.
The normal visitor/run caps bound retained result bytes to 2 MiB per process at
these defaults, plus a bounded number of in-flight expired runs awaiting teardown.

`GET /api/replay/runs/{run_id}/result` uses the same bearer ownership and expiry
checks as status:

- 200: direct `pex.replay-job.v1` result JSON; no envelope or raw filesystem data.
- 202 with `detail: result_pending`: run still executing.
- 409 with `detail: run_failed`: failed run; no arbitrary exception text.
- 404 with `detail: result_unavailable`: completed status-only runner.
- 404 with `detail: run_not_found`: unknown or another visitor's run.
- 401: missing, invalid or expired visitor capability.

Responses are not cacheable. Expiration removes the owner lookup, so late results
cannot be retrieved. Unit HTTP transport tests use schema-valid test doubles, not pipeline evidence.
A separate test-only subprocess adapter now exercises both real fixture jobs
through ASGI start/poll/result and foreign-visitor denial; its timeout tests also
verify subprocess reaping and directory cleanup. The adapter exists only in
`tests/e2e/test_hosted_replay_job.py`, never in the public service. No process runner, sandbox, public backend or deployment is enabled
by this transport increment.
