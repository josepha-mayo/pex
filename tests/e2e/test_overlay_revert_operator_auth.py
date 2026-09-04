from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.app import create_app, state
from pex_bridge.config import Settings

_OPERATOR_TOKEN = "overlay-revert-operator-token-0123456789"
_IDEMPOTENCY_KEY = "overlay-revert-request-0001"


def _receipt(
    *,
    code: str = "overlay_reverted",
    operation_state: str = "delivered",
    ok: bool = True,
    replayed: bool = False,
) -> dict:
    return {
        "ok": ok,
        "code": code,
        "state": operation_state,
        "replayed": replayed,
        "receipt": {
            "operation_id": "ovop_revert_auth",
            "state": operation_state,
            "version": 2,
            "reserved_at": "2026-08-31T10:00:00+00:00",
            "dispatch_started_at": "2026-08-31T10:00:01+00:00",
            "finished_at": "2026-08-31T10:00:02+00:00",
            "result": {"code": code, "mode": "adapter"},
            "private_path": "C:/must-not-leak",
        },
        "private_path": "C:/must-not-leak",
    }


@pytest.mark.asyncio
async def test_overlay_revert_requires_operator_auth_and_strict_body_before_executor_call(
    tmp_path,
    monkeypatch,
):
    calls: list[tuple[str | None, dict]] = []

    async def revert_overlay_receipt(overlay_id: str | None = None, **kwargs) -> dict:
        calls.append((overlay_id, kwargs))
        return _receipt()

    monkeypatch.setattr(
        state,
        "pipeline",
        SimpleNamespace(
            executor=SimpleNamespace(revert_overlay_receipt=revert_overlay_receipt),
        ),
    )
    app = create_app()

    monkeypatch.setattr(
        state,
        "settings",
        Settings.for_test(require_auth=False, home=tmp_path, codex_attach=False),
    )
    monkeypatch.setattr(state, "token", None)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as client:
        denied = await client.post("/v1/overlays/ovl_auth/revert")

        assert denied.status_code == 403
        assert denied.json()["detail"] == (
            "operator mutations require bridge authentication"
        )
        assert calls == []

        monkeypatch.setattr(
            state,
            "settings",
            Settings(
                require_auth=True,
                token=_OPERATOR_TOKEN,
                home=tmp_path,
                codex_attach=False,
            ),
        )
        monkeypatch.setattr(state, "token", _OPERATOR_TOKEN)
        headers = {"Authorization": f"Bearer {_OPERATOR_TOKEN}"}
        invalid = await client.post(
            "/v1/overlays/ovl_auth/revert",
            headers=headers,
            json={"idempotency_key": "short", "unexpected": True},
        )
        assert invalid.status_code == 422
        assert calls == []

        authorized = await client.post(
            "/v1/overlays/ovl_auth/revert",
            headers=headers,
            json={"idempotency_key": _IDEMPOTENCY_KEY},
        )

    assert authorized.status_code == 200
    assert authorized.json() == {
        "ok": True,
        "code": "overlay_reverted",
        "state": "delivered",
        "replayed": False,
        "receipt": {
            "operation_id": "ovop_revert_auth",
            "state": "delivered",
            "version": 2,
            "reserved_at": "2026-08-31T10:00:00+00:00",
            "dispatch_started_at": "2026-08-31T10:00:01+00:00",
            "finished_at": "2026-08-31T10:00:02+00:00",
            "result": {"code": "overlay_reverted", "mode": "adapter"},
        },
    }
    assert calls == [
        (
            "ovl_auth",
            {
                "authorized_by": "local_bridge_operator",
                "idempotency_key": _IDEMPOTENCY_KEY,
                "reason": "user_requested",
            },
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overlay_id", "result", "expected_status"),
    [
        (
            "ovl_dispatching",
            _receipt(
                code="overlay_revert_in_progress",
                operation_state="dispatching",
                ok=False,
            ),
            202,
        ),
        (
            "ovl_failed",
            _receipt(
                code="overlay_revert_failed",
                operation_state="failed",
                ok=False,
            ),
            409,
        ),
        (
            "ovl_uncertain",
            _receipt(
                code="overlay_revert_delivery_uncertain",
                operation_state="delivery_uncertain",
                ok=False,
            ),
            502,
        ),
        (
            "ovl_missing",
            {
                "ok": False,
                "code": "overlay_not_found",
                "state": "not_found",
                "replayed": False,
                "receipt": None,
            },
            404,
        ),
    ],
)
async def test_overlay_revert_maps_canonical_receipt_state(
    tmp_path,
    monkeypatch,
    overlay_id,
    result,
    expected_status,
):
    revert = AsyncMock(return_value=result)
    monkeypatch.setattr(
        state,
        "pipeline",
        SimpleNamespace(executor=SimpleNamespace(revert_overlay_receipt=revert)),
    )
    monkeypatch.setattr(
        state,
        "settings",
        Settings(
            require_auth=True,
            token=_OPERATOR_TOKEN,
            home=tmp_path,
            codex_attach=False,
        ),
    )
    monkeypatch.setattr(state, "token", _OPERATOR_TOKEN)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://127.0.0.1",
        headers={"Authorization": f"Bearer {_OPERATOR_TOKEN}"},
    ) as client:
        response = await client.post(
            f"/v1/overlays/{overlay_id}/revert",
            json={"idempotency_key": _IDEMPOTENCY_KEY},
        )

    assert response.status_code == expected_status
    assert response.json()["code"] == result["code"]
    assert set(response.json()) == {"ok", "code", "state", "replayed", "receipt"}
    revert.assert_awaited_once()
