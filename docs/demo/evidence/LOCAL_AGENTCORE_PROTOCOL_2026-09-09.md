# PEX local AgentCore protocol smoke — 9 September 2026

This receipt is bound to the exact clean source used to build the retained installers:
`9966a602be7ed700844979e5fac2e2669cdb8823`.

## Procedure

The real `pex_supervisor.runtime` entrypoint was started in its documented explicit
`local_http` mode on `127.0.0.1:18080`. The smoke then:

1. requested `GET /ping`;
2. posted a versioned PEX supervisor envelope to `POST /invocations`;
3. checked the HTTP statuses, schema version, invocation identity, action/session binding,
   and model-use flag; and
4. sent Ctrl+C to the exact server session and observed normal application shutdown.

## Result

```json
{
  "action_session_id": "package-smoke",
  "action_type": "NOOP",
  "diagnosis": "deterministic_triage_no_supervisor_model",
  "invocation_id_matches": true,
  "invocation_status": 200,
  "ping": {
    "model_configured": false,
    "service": "pex-supervisor",
    "status": "Healthy"
  },
  "ping_status": 200,
  "schema_version": 1,
  "source": "9966a602be7ed700844979e5fac2e2669cdb8823",
  "used_llm": false
}
```

All assertions passed. The Uvicorn process logged both requests as `200 OK`, then logged
application shutdown complete and finished the owned server process.

## Claim boundary

This proves that the packaged-source AgentCore-compatible HTTP protocol starts locally,
accepts the strict versioned invocation envelope, returns a typed session-bound action, and
shuts down cleanly. Local mode deliberately forces deterministic triage and does not load a
model from ambient credentials.

It does **not** prove an AWS Bedrock AgentCore Runtime deployment, Runtime ARN, IAM access,
ARM64 container execution, or paid model invocation. Those claims remain blocked by the
no-card-charge boundary and the current read-only deployment preflight.
