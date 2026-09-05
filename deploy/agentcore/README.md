# PEX supervisor — AgentCore Runtime image

Status: **packaged and locally testable; not deployed to AWS.** The remote
service only proposes typed actions. Local PEX policy remains authoritative and
keeps every harness credential and side effect on the bridge.

## Local contract smoke

The locked image is ARM64 because AgentCore Runtime requires Linux ARM64:

```bash
docker buildx build --platform linux/arm64 \
  -f deploy/agentcore/Dockerfile \
  -t pex-supervisor:agentcore-arm64 \
  --load .

docker run --rm --platform linux/arm64 -p 127.0.0.1:18080:8080 \
  -e PEX_RUNTIME_SERVER=local_http \
  -e PEX_RUNTIME_HOST=0.0.0.0 \
  pex-supervisor:agentcore-arm64

curl http://127.0.0.1:18080/ping

curl -fsS http://127.0.0.1:18080/invocations \
  -H 'content-type: application/json' \
  --data-binary '{"schema_version":1,"invocation_id":"pexinv_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","request":{"session":{"id":"smoke","harness_type":"codex","vendor_session_id":"smoke","project_id":"smoke","status":"stopped"},"goal":null,"event":{"event_id":"smoke","ts":"2026-08-28T00:00:00Z","harness_type":"codex","session_id":"smoke","project_id":"smoke","event_type":"stop","phase":"terminal"}}}'
```

`local_http` is deliberately deterministic-only: it validates the versioned
request/response envelope without loading or invoking a model from ambient
credentials. Real semantic inference is exercised only through the authenticated
AgentCore Runtime path and its separately gated live contract test.
Treat `/ping` as startup evidence only: the smoke is not complete unless the
versioned `/invocations` request returns a session-bound typed action.

`deploy/agentcore/requirements.lock` is generated from `uv.lock`:

```bash
uv export --frozen --package pex-supervisor --extra agentcore --no-dev \
  --no-emit-workspace --no-header --no-annotate \
  --output-file deploy/agentcore/requirements.lock
```

Run the read-only preflight before considering deployment:

```bash
uv run python deploy/agentcore/preflight.py
```

It checks active AWS credentials, the current AgentCore CLI/CDK prerequisites,
Docker/buildx ARM64 support, the existing image architecture, and secret-safe
build context. Executable presence alone is not considered deployable.
The invocation target checks also reject a mismatched region or invalid endpoint
qualifier using the bridge's normalization rules. This remains a local prerequisite
report, not a resource existence, IAM/model access, billing-safety or live inference
proof. Its current `invokable` flag still requires deployment tooling and should
not be used to rule out SDK invocation of an already deployed runtime; project
configuration and deployment dry-run verification are separate gates below.

## Runtime configuration

The deployed container must use:

```text
PEX_RUNTIME_SERVER=agentcore
PEX_SUPERVISOR_PROVIDER=bedrock
PEX_SUPERVISOR_MODEL=<verified Bedrock model or inference profile id>
PEX_SUPERVISOR_AUTH=aws_sigv4
PEX_SUPERVISOR_WALL_TIMEOUT=20
AWS_REGION=<deployment region>
```

The local bridge invokes the deployed Runtime by ARN through the AWS SDK:

```text
PEX_SUPERVISOR_MODE=agentcore
PEX_AGENTCORE_RUNTIME_ARN=arn:aws:bedrock-agentcore:<region>:<account>:runtime/<runtime-id>
PEX_AGENTCORE_REGION=<same region>
PEX_AGENTCORE_QUALIFIER=DEFAULT
```

`agentcore` fails closed on remote transport/protocol errors. `hybrid` is the
only mode that explicitly permits a local semantic-model fallback. Routine
deterministic triage stays local in every mode.

## Deployment gate

The current AgentCore CLI workflow begins with an AgentCore project/config and
uses `agentcore deploy --dry-run` before `agentcore deploy`; do not reuse the old
`agentcore deploy --name ... --region ...` command. Creating the CLI project,
ECR/CDK/IAM/Runtime resources, deploying, or invoking a paid model requires
separate action-time authorization. No script in this directory performs those
actions automatically.

After an authorized deployment, record the returned **Runtime ARN** (not the
endpoint ARN), verify the endpoint is ready, and run the separately gated
contract test before claiming AgentCore proof:

```bash
PEX_AGENTCORE_LIVE=1 uv run pytest -q -m live_agentcore \
  tests/contract/test_live_agentcore.py
```

The test skips unless both `PEX_AGENTCORE_LIVE=1` and
`PEX_AGENTCORE_RUNTIME_ARN` are present. Setting those values and running it is
a paid live invocation and therefore remains an action-time authorization gate.

The container's 20-second model wall timeout is deliberately shorter than the
bridge's 25-second transport timeout, which leaves time for the Runtime to
return and persist a typed timeout receipt instead of losing it at the network
boundary.

Current primary references:

- <https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-get-started-cli.html>
- <https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html>
- <https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html>
