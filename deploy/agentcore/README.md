# PEX supervisor — AgentCore Runtime image

Local policy stays on the bridge. This image only runs the Strands supervisor
(`/invocations`, `/ping`) so AgentCore cannot bypass approvals.

Build from the repo root:

```bash
docker build -f deploy/agentcore/Dockerfile -t pex-supervisor .
```

Run locally the same way AgentCore will:

```bash
docker run --rm -p 8080:8080 pex-supervisor
curl http://127.0.0.1:8080/ping
```

Deploy (after AWS CLI + Bedrock/AgentCore access in the chosen region):

```bash
# Region is not assumed. Confirm AgentCore availability before using eu-north-1.
agentcore deploy --name pex-supervisor --region <verified-region>
```

The cloud supervisor proposes typed actions. The local bridge still executes them.
