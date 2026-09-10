from __future__ import annotations


from fastapi.testclient import TestClient
from pex_bridge import app as bridge_app
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pets.hatch import HatchRegistry
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store

_OPERATOR_TOKEN = "hatch-operator-test-token-0123456789abcdef"
_HEADERS = {"Authorization": f"Bearer {_OPERATOR_TOKEN}"}


def _configure_operator_app(tmp_path, *, require_auth: bool = True) -> TestClient:
    settings = (
        Settings(
            require_auth=True,
            token=_OPERATOR_TOKEN,
            home=tmp_path,
            codex_attach=False,
        )
        if require_auth
        else Settings.for_test(
            require_auth=False,
            home=tmp_path,
            codex_attach=False,
        )
    )
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    bridge_app.state.settings = settings
    bridge_app.state.token = _OPERATOR_TOKEN if require_auth else None
    bridge_app.state.store = store
    bridge_app.state.adapters = adapters
    bridge_app.state.bus = bus
    bridge_app.state.pipeline = Pipeline(store, adapters, bus, settings)
    bridge_app.state.hatch = HatchRegistry(settings.data_dir / "hatch")
    bridge_app.state.background_tasks = set()
    bridge_app.state.hatch_tasks = {}
    return TestClient(
        bridge_app.create_app(),
        base_url="http://127.0.0.1",
        headers=_HEADERS,
    )


def _request(*, notes: str = "ink navy, cream belly") -> dict[str, object]:
    return {
        "display_name": "Nori",
        "description": "A small plush fox",
        "style_preset": "plush",
        "pet_notes": notes,
        "idempotency_key": "hatch-base-api-replay-0001",
        "confirm_one_base_candidate_call": True,
    }


def test_two_pet_mvp_rejects_generation_even_with_a_provider(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("two-pet MVP must not resolve a provider or generate art")

    monkeypatch.setattr("pex_bridge.pets.imagegen.hatch_image_config", forbidden)
    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", forbidden)
    with _configure_operator_app(tmp_path) as client:
        for _ in range(2):
            response = client.post("/v1/pets/hatch", json=_request())
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "hatch_disabled_for_mvp"
        assert client.get("/v1/pets/hatch/capability").json()["generation_ready"] is False
        assert client.get("/v1/pets/hatch").json() == {"jobs": []}
        assert not bridge_app.state.hatch_tasks


def test_hatch_operator_requires_exact_confirmation_and_bound_provider(
    tmp_path,
    monkeypatch,
):
    config_resolutions = 0

    def no_config():
        nonlocal config_resolutions
        config_resolutions += 1
        return None

    monkeypatch.setattr("pex_bridge.pets.imagegen.hatch_image_config", no_config)

    def forbidden_provider_call(*_args, **_kwargs):
        raise AssertionError("validation or provider binding failure must not dispatch")

    monkeypatch.setattr(
        "pex_bridge.pets.hatch.generate_png",
        forbidden_provider_call,
    )

    with _configure_operator_app(tmp_path) as client:
        unauthorized = client.post(
            "/v1/pets/hatch",
            headers={"Authorization": "Bearer wrong-token"},
            json=_request(),
        )
        assert unauthorized.status_code == 401
        assert config_resolutions == 0

        false_confirmation = _request()
        false_confirmation["confirm_one_base_candidate_call"] = False
        assert (
            client.post("/v1/pets/hatch", json=false_confirmation).status_code == 422
        )
        assert config_resolutions == 0

        legacy_confirmation = _request()
        legacy_confirmation.pop("confirm_one_base_candidate_call")
        legacy_confirmation["confirm_potential_image_charges"] = True
        assert client.post("/v1/pets/hatch", json=legacy_confirmation).status_code == 422
        assert config_resolutions == 0

        short_key = _request()
        short_key["idempotency_key"] = "too-short"
        assert client.post("/v1/pets/hatch", json=short_key).status_code == 422
        assert config_resolutions == 0

        invalid_style = _request()
        invalid_style["style_preset"] = "server-must-not-trust-ui"
        assert client.post("/v1/pets/hatch", json=invalid_style).status_code == 422

        control_notes = _request()
        control_notes["pet_notes"] = "unsafe\nnotes"
        assert client.post("/v1/pets/hatch", json=control_notes).status_code == 422
        assert config_resolutions == 0

        unavailable = client.post("/v1/pets/hatch", json=_request())
        assert unavailable.status_code == 409, unavailable.text
        assert unavailable.json()["detail"] == {
            "code": "hatch_disabled_for_mvp",
            "message": (
                "This MVP supports Pex and Von only; image generation is disabled."
            ),
        }
        assert config_resolutions == 0
        assert client.get("/v1/pets/hatch").json() == {"jobs": []}


def test_hatch_operator_route_is_closed_when_bridge_auth_is_disabled(
    tmp_path,
    monkeypatch,
):
    def forbidden_config_resolution():
        raise AssertionError("no-auth mode must be rejected before provider resolution")

    monkeypatch.setattr(
        "pex_bridge.pets.imagegen.hatch_image_config",
        forbidden_config_resolution,
    )

    with _configure_operator_app(tmp_path, require_auth=False) as client:
        response = client.post("/v1/pets/hatch", json=_request())
        assert response.status_code == 403
        assert response.json()["detail"] == (
            "operator mutations require bridge authentication"
        )
        assert client.get("/v1/pets/hatch").json() == {"jobs": []}
