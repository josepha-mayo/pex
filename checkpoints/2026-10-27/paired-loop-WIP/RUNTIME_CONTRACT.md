# Optional paid pilot runtime contract — default closed

## Interpreter and paths

Use exactly `/workspace/scratch/c62c151ada7d/pex-supervisor-model-only-GUARDED-WORKING-20261026-2051/.venv/bin/python` (Python3.12.14).
`runtime.py` adds its declared `PATHS`, then appends (never prepends)
`/tmp/pex-e2b-sdk-261/lib/python3.12/site-packages`. Existing frozen Strands dependencies
retain precedence. No venv installation/mutation is required. Exact resolved paths,
package versions and source hashes are in `RUNTIME_PREFLIGHT.json`; rerun preflight
after any code checkpoint or approval binding changes. This evidence is imports and
frozen-file identity, not a provider connection or real benchmark.

```bash
ROOT=/workspace/scratch/c62c151ada7d
PY="$ROOT/pex-supervisor-model-only-GUARDED-WORKING-20261026-2051/.venv/bin/python"
DRIVER="$ROOT/pex-paired-loop-WIP-20261027-1012/runtime.py"
"$PY" "$DRIVER" --check-runtime
```

The check reads no private config/keys, constructs no provider/VM clients, and makes
no model/resource calls. It initializes NoOp telemetry before importing Strands.
Check and launch MUST be separate fresh processes: reinitializing telemetry after
framework imports is intentionally refused.

## Frozen task

Package:
`/workspace/scratch/c62c151ada7d/pex-owncloud-recovered-baseline-20261026-2010/archived-packages/pex-benchmark-hardening-20261023-v2/pex-benchmark-hardening/pex_real_pilot`

Manifest SHA256:
`533c7e055167fe6a86c6ed8fed481605405fab96db45bc7dd60f9705fea3d019`.
Task `05_uncertain_commit`; no claim that this has been empirically shown difficult.
Five public files, INITIAL_PROMPT and protected evaluator hashes are verified without
executing candidate code. Hidden inputs stay out of generation/model context.

## Private driver config (exact field set, schema1)

- `schema`: integer1
- `approval_ref`: exact new owner approval, which must first be pinned into
  `pilot_nebius.APPROVAL` and `worker_funding.APPROVED_WORKER_REF`. Both remain closed.
- `expires_at`: timezone-aware ISO timestamp no later than2026-10-27T14:00:00+00:00;
  driver requires at least330seconds remaining.
- `source_sha256`: exact map from preflight `pilot_source_sha256` (including runtime.py)
- `nebius_key_path`, `nebius_key_sha256`: absolute private key path and SHA256
- `e2b_key_path`, `e2b_key_sha256`: absolute private key path and SHA256
- `supervisor_template_path`, `supervisor_template_sha256`: private JSON template and SHA256
- `package_path`: exact frozen package above
- `output_dir`: fresh nonexistent path, normally the root-approved
  `/workspace/scratch/c62c151ada7d/runtime-private/pex-pilot-20261027/run-01`
- `binary_path`: `/workspace/scratch/c62c151ada7d/opencode-qualification-20261027/install/node_modules/@opencode/cli-linux-x64/bin/opencode`
- `modules_path`: `/workspace/scratch/c62c151ada7d/opencode-qualification-20261027/mock/node_modules`

Private files0600, immediate parent0700, absolute non-symlink paths. Runtime independent
config SHA is supplied by root, not taken on trust from the config itself.

## Supervisor template (exact field set)

- `schema`:1
- `approval_ref`: `Sentinel_a6f9e81f1aa88191a915b10436a3cb06` (existing supervisor grant)
- `pilot_id`: `pex-paired-pilot-20261027-101349`
- `expires_at`: same bounded timestamp rule
- `endpoint`: `https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions`
- `model`: `nvidia/nemotron-3-super-120b-a12b`
- `budget_nano_usd`:250000000; `max_attempts`:12; `input_rate`:300; `output_rate`:900
- `pricing_provenance_sha256`: root's independently verified official pricing artifact hash
- `key_path`, `key_sha256`: private Nebius key identity
- `ledger_path`: overwritten by driver with output_dir/supervisor-pilot.sqlite
- `source_sha256`: exact preflight `supervisor_source_sha256` map
- `request_binding`: keys `goal_id`, `session_id`, `vendor_session_id`; overwritten by
  driver with the actual first PEX review's identities, then template bytes are hashed.

Original planner1200/verifier900 output and role-total limits are unchanged. One shared
supervisor ledger reserves4096-output worst-case envelope per attempt and only rebates
validated raw usage. Two worker arm ledgers share one SQLite file but have independent
$0.375 ceilings; total Nebius ceiling is$1, not$1 per component. E2B remains$0.10.

## Launch only after exact approval, final source bindings and root GO

```bash
umask 077
"$PY" "$DRIVER" --execute-approved-pilot \
  --config "$PRIVATE_CONFIG" --sha256 "$INDEPENDENT_CONFIG_SHA256" \
  > "$PRIVATE_CONTROLLER_STDOUT" 2> "$PRIVATE_CONTROLLER_STDERR"
```

This command is a contract, NOT an executed run or permission grant. Root must keep
stdout/stderr private; only output_dir/events.jsonl is recorder-facing. No same-process
preflight+launch. The source default remains closed until exact approval is pinned.
On termination root verifies pool cleanup before credential revocation. Raw CLI/SQLite
may contain provider reasoning and must never enter recording/source publication.
