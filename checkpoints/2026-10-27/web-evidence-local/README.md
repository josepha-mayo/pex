# Local owner evidence composition (WIP, not deployed)

This isolated candidate serves actual configured paired-controller JSONL through
PEX's existing authenticated read-only owner page. It does not start a bridge,
worker, model, sandbox, recorder or provider. No runtime owner files were changed.

The paired runtime has no bridge workspace Store database. `OwnerEvidenceReader`
therefore explicitly supplies empty workspace lists plus the bounded existing
metadata projection; it does **not** create fake sessions/goals or a fake database.
The page labels the absent workspace and warns that configured models do not
establish completed inference or verified PEX benefit. Controller metadata is not
independent inference verification. Supervisor overhead is not counted.

## Composition

- `serve_owner_evidence.py`: exact static build allowlist + four existing auth/API
  routes on `https://127.0.0.1:7443/`; direct TLS, proxy headers disabled, no CORS.
- `OwnerSessions`: separate random owner secret, secure host-only HttpOnly cookie,
  origin/host checks, CSRF-protected logout, existing expiry and revocation.
- `OwnerEvidenceReader`: explicit absolute JSONL only. It never reads reports,
  private decisions, funding ledgers or hidden tests; allowlisted metadata only.
- Existing event reader rejects final symlinks, partial/corrupt/oversized files.
- Static paths are never mapped to arbitrary filesystem locations. No caching.
- Private owner secret is loaded from an owner-controlled mode-0600 regular file.
- `local-private/` is never a publication input. It contains local test TLS keys
  and an independently generated owner secret, not provider credentials.

## Runnable path in this cloud executor

From this directory, with existing dependencies (no installation/network needed):

```sh
PY=../pex-supervisor-model-only-GUARDED-WORKING-20261026-2051/.venv/bin/python
"$PY" serve_owner_evidence.py \
  --events /workspace/scratch/c62c151ada7d/runtime-private/pex-pilot-20261027/run-01/events.jsonl \
  --owner-secret-file local-private/owner.secret \
  --tls-cert local-private/cert.pem --tls-key local-private/key.pem --port 7443
```

Open **https://127.0.0.1:7443/** in the same execution environment, trust only the
explicit local test certificate, and enter the separately provisioned local owner
secret. Do not put secrets in URLs or logs. The local test certificate expires in
two days; replace it for later local QA. This is not public hosting or a production
TLS configuration. No background server is left running by qualification.

For a fresh reconstruction, copy the owner source tree dependencies and built
`apps/desktop/dist-owner` to this candidate's `dist-owner`; replace the app's
`owner.html` with this candidate's source `owner.html` before `npm run build:owner`.
The inherited JS/CSS are unchanged. The launcher expects services/packages next
to itself and accepts only explicit files. A real browser outside this executor
cannot reach its loopback without a separately authorized transport.

## Qualification, 2026-10-27

- 72 Python unittest cases pass: 69 inherited auth/HTTP/workspace/evidence + 3 new
  composition tests. New cases cover auth-before-read, mutable file refresh,
  hidden-field omission, corrupt-file fail-closed, exact routes, HTTPS/host/origin,
  logout revocation, event symlink rejection and owner-secret permissions.
- Ruff check and format check pass for all five new/changed Python files.
- `check_tls.py`: real loopback TLS with certificate verification, unauthenticated
  401, successful owner login, actual run-01 file read passed. Server is terminated
  after test. Output: baseline 10 calls/natural_stop; PEX 10/infrastructure_error;
  paired_terminal true means both arms stopped, **not success**. No grades shown.
- `browser_check.cjs` is authored but **not passed**: headless Chromium startup
  failed at sandbox socket creation (`Operation not permitted`). No retry after
  this permission failure, native browser focus, screenshots or video recording.
- Frontend JS/CSS reused from prior owner build; no new browser/visual claim,
  no general lift claim, no provider call, no deployed/public URL.

Run scoped tests:

```sh
PYTHONPATH=services/bridge/src:packages/protocol/src:services/supervisor/src:tests/unit \
 "$PY" -m unittest -q test_local_evidence test_web_owner_auth test_web_owner_http \
 test_web_owner_workspace test_web_owner_evidence
"$PY" check_tls.py
```

The optional `check_tls.py --browser` is intended only for an execution environment
where Chromium is allowed; it is not a workaround for this executor's denial.
