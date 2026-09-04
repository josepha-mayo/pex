from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

from fastapi.testclient import TestClient
from pex_bridge import app as bridge_app
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pets.hatch import HatchRegistry
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store
from PIL import Image

_OPERATOR_TOKEN = "hatch-operator-test-token-0123456789abcdef"
_HEADERS = {"Authorization": f"Bearer {_OPERATOR_TOKEN}"}
_CONFIG = {
    "provider": "test",
    "base_url": "https://images.example.test/v1",
    "api_key": "test-secret",
    "model_id": "test-image-model",
    "timeout": 1,
}


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


def _png_bytes() -> bytes:
    encoded = BytesIO()
    Image.new("RGB", (16, 16), (8, 20, 44)).save(encoded, format="PNG")
    return encoded.getvalue()


def test_hatch_operator_exact_replay_schedules_one_provider_call(
    tmp_path,
    monkeypatch,
):
    generation_started = threading.Event()
    release_generation = threading.Event()
    calls = 0

    def generate_png(*_args, **kwargs):
        nonlocal calls
        assert kwargs["config"] is _CONFIG
        calls += 1
        generation_started.set()
        assert release_generation.wait(timeout=5)
        return _png_bytes()

    monkeypatch.setattr(bridge_app, "hatch_image_config", lambda: _CONFIG)
    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", generate_png)

    with _configure_operator_app(tmp_path) as client:
        barrier = threading.Barrier(3)

        def post_same_request():
            barrier.wait(timeout=2)
            return client.post("/v1/pets/hatch", json=_request())

        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(post_same_request) for _ in range(2)]
            barrier.wait(timeout=2)
            responses = [future.result(timeout=3) for future in pending]

        assert all(response.status_code == 200 for response in responses), [
            response.text for response in responses
        ]
        first_job = responses[0].json()
        assert responses[1].json()["id"] == first_job["id"]
        assert first_job["effect_status"] in {"reserved", "dispatching"}
        assert first_job["jobs_total"] == 1
        assert first_job["spritesheet"] is None
        assert generation_started.wait(timeout=2)

        replay = client.post("/v1/pets/hatch", json=_request())
        assert replay.status_code == 200, replay.text
        assert replay.json()["id"] == first_job["id"]
        assert calls == 1

        conflict = client.post(
            "/v1/pets/hatch",
            json=_request(notes="changed body under the same key"),
        )
        assert conflict.status_code == 409, conflict.text
        assert conflict.json()["detail"]["code"] == "hatch_idempotency_conflict"
        assert calls == 1

        release_generation.set()
        deadline = time.monotonic() + 3
        completed = None
        while time.monotonic() < deadline:
            completed = client.get(f"/v1/pets/hatch/{first_job['id']}")
            assert completed.status_code == 200, completed.text
            if completed.json()["status"] == "awaiting_assembly_qa":
                break
            time.sleep(0.01)
        assert completed is not None
        assert completed.json()["status"] == "awaiting_assembly_qa"
        assert completed.json()["jobs_complete"] == 1
        assert completed.json()["spritesheet"] is None

        completed_replay = client.post("/v1/pets/hatch", json=_request())
        assert completed_replay.status_code == 200, completed_replay.text
        assert completed_replay.json() == completed.json()
        assert calls == 1

        listed = client.get("/v1/pets/hatch")
        assert listed.status_code == 200
        assert [job["id"] for job in listed.json()["jobs"]] == [first_job["id"]]


def test_hatch_operator_requires_exact_confirmation_and_bound_provider(
    tmp_path,
    monkeypatch,
):
    config_resolutions = 0

    def no_config():
        nonlocal config_resolutions
        config_resolutions += 1
        return None

    monkeypatch.setattr(bridge_app, "hatch_image_config", no_config)

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
            "code": "hatch_provider_unavailable",
            "message": (
                "No authorized image provider configuration is available; "
                "no call was made."
            ),
        }
        assert config_resolutions == 1
        assert client.get("/v1/pets/hatch").json() == {"jobs": []}


def test_hatch_operator_route_is_closed_when_bridge_auth_is_disabled(
    tmp_path,
    monkeypatch,
):
    def forbidden_config_resolution():
        raise AssertionError("no-auth mode must be rejected before provider resolution")

    monkeypatch.setattr(
        bridge_app,
        "hatch_image_config",
        forbidden_config_resolution,
    )

    with _configure_operator_app(tmp_path, require_auth=False) as client:
        response = client.post("/v1/pets/hatch", json=_request())
        assert response.status_code == 403
        assert response.json()["detail"] == (
            "operator mutations require bridge authentication"
        )
        assert client.get("/v1/pets/hatch").json() == {"jobs": []}
