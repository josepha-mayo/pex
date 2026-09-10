# Live saved-Zen supervisor probe — 10 September 2026

Source: `4329978`, clean worktree. Python command exited 0. No worker attached,
no native UI launched, no process terminated, no AWS resource deployed.

Before invocation, a read-only control-file check reported all three booleans true:
saved choice present, exact free Zen route, OS-vault-backed credential source.
The runtime loaded the secret itself; the value and vault reference were not
printed or copied into source, environment variables or this receipt.

The execution guard required all of:

- provider `zen`;
- model `muse-spark-1.3-contributor-free`;
- base URL `https://opencode.ai/zen/v1`;
- authentication `api_key`, credential source `secret_store`.

[Official Zen documentation](https://opencode.ai/docs/zen/) was checked on this
date and lists this exact model as free on the Responses endpoint. No paid-model
fallback was selected. This is not an account billing statement or future pricing
guarantee. Plain Muse Spark 1.3 is a different, paid model.

Production `_activate_supervisor_choice` loaded the saved choice, then the existing
`test_live_supervisor_inference_is_auditable` function ran directly (not as a pytest
suite), with its explicit `PEX_LIVE_SUPERVISOR=1` gate and expected provider/model/API
set for that command only. All assertions completed:

- `used_llm is True`;
- inference status `completed`;
- runtime `strands-agents` and nonempty runtime version;
- at least one model call;
- nonempty local invocation ID with `pexinv_` prefix;
- provider/model exactly as guarded above, generation API `responses`;
- action in the typed allowed decision set;
- no fabricated provider request ID.

Terminal output:

```text
PASS: saved free Zen vault configuration -> real Strands inference -> typed auditable decision; no worker attached
```

The probe uses a synthetic stopped session and a synthetic goal. It does not
establish correct real-task NOOP/intervention, same-worker continuation, useful
outcome, UI interaction, AgentCore deployment, or benchmark performance. The full
decision payload was not retained; this receipt records the executed assertion
contract, not a complete intervention audit trail. Do not count it as a benchmark
case or claim the visible MVP journey is complete.
