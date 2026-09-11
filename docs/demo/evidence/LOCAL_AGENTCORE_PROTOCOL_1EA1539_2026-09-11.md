# Current PEX AgentCore-compatible local protocol smoke — 11 September 2026

Source: `1ea1539430595a1ed67bb8598e38c3e1a73cffaa`. Product runtime is unchanged
from verified package source `c3cc44c7fd23c8b5268acaa926e20face9f0bc25`.
The exercised `runtime.py` SHA-256 is
`23d5c4b6047b01dc8c2120dc7e0d36248e7e8ba2703b72c5c634134d203d9533`,
which matches the frozen runtime file recorded in the package receipt.

## Procedure

The real `pex_supervisor.runtime` entrypoint started in its explicit
deterministic-only `local_http` mode on unused loopback port 18080. No ambient
model was loaded. The smoke requested `GET /ping`, posted the documented
versioned envelope to `POST /invocations`, asserted response/session binding,
then sent Ctrl+C only to that owned server session.

## Result

Both requests returned `200 OK`. All assertions passed:

```json
{
  "action": "NOOP",
  "action_session": "smoke",
  "diagnosis": "deterministic_triage_no_supervisor_model",
  "invocation_id_matches": true,
  "model_configured": false,
  "ping_status": "Healthy",
  "schema_version": 1,
  "service": "pex-supervisor",
  "used_llm": false
}
```

Uvicorn logged application shutdown complete and finished its exact process.
Afterward, process 5780 was absent and port 18080 had no listener.

## Claim boundary

This proves the current packaged product's AgentCore-compatible HTTP protocol
starts locally, accepts the strict versioned invocation envelope, returns a
typed session-bound action, and shuts down cleanly. It does not prove an AWS
Bedrock AgentCore Runtime deployment, Runtime ARN, IAM/model access, ARM64
container execution, or paid model invocation. AgentCore remains an
implemented and offline-tested optional deploy target.
