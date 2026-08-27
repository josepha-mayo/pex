from __future__ import annotations

from pathlib import Path

from pex_bridge.pets import STARTERS
from pex_bridge.pets.hatch import HatchJob, HatchRegistry, hatch_prompt, slugify
from pex_bridge.pets.imagegen import HatchImageError, generate_png, probe_images_endpoint


def test_seven_starters_are_distinct_species():
    assert len(STARTERS) == 7
    assert len({pet.species for pet in STARTERS}) == 7


def test_slugify_pet_name():
    assert slugify("Ink Fox") == "ink-fox"
    assert slugify("  ") == "pet"


def test_hatch_prompt_forbids_atlas_grids():
    job = HatchJob(id="h1", pet_id="fox", display_name="Fox", description="plush fox")
    prompt = hatch_prompt(job, "idle", 6, "calm breathing")
    assert "SINGLE horizontal animation strip" in prompt
    assert "8x11" in prompt


def test_images_probe_404_is_text_only(monkeypatch):
    class FakeResponse:
        status_code = 404

    class FakeClient:
        def get(self, url, headers=None):
            assert url.endswith("/images/generations")
            return FakeResponse()

        def close(self):
            return None

    result = probe_images_endpoint(
        {"provider": "zen", "base_url": "https://example.test/v1", "api_key": "x", "model_id": "m", "timeout": 1},
        client=FakeClient(),
    )
    assert result["ok"] is False
    assert result["has_image_endpoint"] is False
    assert "no /images/generations" in result["reason"]


def test_generate_png_404_is_honest():
    class FakeResponse:
        status_code = 404
        text = "not found"

        def json(self):
            return {}

    class FakeClient:
        def post(self, url, headers=None, json=None):
            return FakeResponse()

        def close(self):
            return None

    def fake_config():
        return {
            "provider": "zen",
            "base_url": "https://example.test/v1",
            "api_key": "secret-must-not-appear",
            "model_id": "gpt-image-1",
            "timeout": 1,
        }

    import pex_bridge.pets.imagegen as imagegen

    imagegen_orig = imagegen.hatch_image_config
    imagegen.hatch_image_config = fake_config
    try:
        try:
            generate_png("a pet", client=FakeClient())
            raise AssertionError("expected HatchImageError")
        except HatchImageError as exc:
            message = str(exc)
            assert "text-only" in message or "no /images/generations" in message
            assert "secret-must-not-appear" not in message
    finally:
        imagegen.hatch_image_config = imagegen_orig


def test_hatch_registry_roundtrip(tmp_path: Path):
    registry = HatchRegistry(tmp_path)
    job = HatchJob(id="hatch_1", pet_id="fox", display_name="Fox", description="plush fox")
    registry.create(job)
    loaded = HatchRegistry(tmp_path).get("hatch_1")
    assert loaded is not None
    assert loaded.display_name == "Fox"
    assert loaded.jobs_total == 13
