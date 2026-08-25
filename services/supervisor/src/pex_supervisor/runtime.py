"""AgentCore Runtime entrypoint for the PEX supervisor.

Local development can run this module directly:
  uv run python -m pex_supervisor.runtime

AgentCore requires POST /invocations and GET /ping on port 8080.
"""

from __future__ import annotations

import os

from pex_protocol.supervisor import SupervisorRequest
from pex_supervisor.loop import decide


def handle_payload(payload: dict) -> dict:
    body = payload.get("input") if isinstance(payload.get("input"), dict) else payload
    request_data = body.get("request") or body
    request = SupervisorRequest.model_validate(request_data)
    result = decide(request, force_llm=os.environ.get("PEX_FORCE_LLM") == "1")
    return result.model_dump(mode="json")


def _agentcore_app():
    from bedrock_agentcore.runtime import BedrockAgentCoreApp

    app = BedrockAgentCoreApp()

    @app.entrypoint
    def invoke(payload: dict):
        return handle_payload(payload)

    return app


def _fastapi_app():
    from fastapi import FastAPI

    app = FastAPI(title="PEX Supervisor", version="0.1.0")

    @app.get("/ping")
    def ping():
        return {"status": "healthy", "service": "pex-supervisor"}

    @app.post("/invocations")
    def invocations(payload: dict):
        return {"output": handle_payload(payload)}

    return app


def main() -> None:
    import uvicorn

    try:
        app = _agentcore_app()
        app.run()
        return
    except Exception:
        pass
    uvicorn.run(_fastapi_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
