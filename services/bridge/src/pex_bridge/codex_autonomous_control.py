"""Explicit operator opt-in for the private shared-Codex correction path."""

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from pex_bridge.adapters.codex_shared_adapter import CodexSharedAdapter
from pex_bridge.store import OperatorEffectConflictError


class AutonomousCorrectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    enabled: bool
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")
    expected_control_revision: int = Field(ge=0, le=2**63 - 1)
    expected_goal_id: str = Field(min_length=1, max_length=512)
    expected_goal_intent_revision: int = Field(ge=0, le=2**63 - 1)
    expected_goal_intent_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_project_binding: str = Field(min_length=1, max_length=512)
    expected_workspace_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_subscription_authorization_id: str = Field(min_length=1, max_length=512)
    expected_connection_generation: int = Field(ge=1, le=2**63 - 1)


def register_autonomous_correction_routes(app, state, require_operator_token) -> None:
    @app.get("/v1/sessions/{session_id}/autonomous-corrections")
    async def status(session_id: str, _: object = Depends(require_operator_token)):
        result = await state.store.get_autonomous_correction_grant_status(session_id)
        adapter = state.adapters.for_session(session_id)
        connected = isinstance(adapter, CodexSharedAdapter) and adapter._connected()
        return {
            **result,
            "connected": connected,
            "effective_enabled": result.get("enabled") is True and connected,
            "delivery_proven": False,
        }

    @app.patch("/v1/sessions/{session_id}/autonomous-corrections")
    async def update(
        session_id: str,
        body: AutonomousCorrectionUpdate,
        _: object = Depends(require_operator_token),
    ):
        # This opt-in changes local standing authority only. It never sends a
        # message, changes worker approval policy, or rewrites observation consent.
        adapter = state.adapters.for_session(session_id)
        if body.enabled and not (
            isinstance(adapter, CodexSharedAdapter) and adapter._connected()
        ):
            raise HTTPException(
                409, "Reconnect the selected Codex session before enabling corrections.",
            )
        try:
            return await state.store.set_session_autonomous_corrections(
                session_id, **body.model_dump(),
                principal_id="local_bridge_operator", actor_assurance="bridge_bearer",
            )
        except LookupError as exc:
            raise HTTPException(404, "The selected session or goal is unavailable.") from exc
        except OperatorEffectConflictError as exc:
            raise HTTPException(
                409, "This operation key belongs to a different control change.",
            ) from exc
        except (ValueError, OSError) as exc:
            raise HTTPException(
                409, "Control scope changed; reload and review before retrying.",
            ) from exc
