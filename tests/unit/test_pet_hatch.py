from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from pex_bridge.pets import STARTERS
from pex_bridge.pets.hatch import (
    HatchAuthorizationError,
    HatchJob,
    HatchRegistry,
    authorize_hatch,
    hatch_prompt,
    run_hatch_job,
    slugify,
    write_generated,
)
from pex_bridge.pets.imagegen import HatchImageError, generate_png, probe_images_endpoint
from PIL import Image


def test_eight_starters_are_the_bound_fleet():
    assert [pet.id for pet in STARTERS] == [
        "pex",
        "ledger",
        "mesh",
        "nudge",
        "drift",
        "quiet",
        "ember",
        "von",
    ]


def test_slugify_pet_name():
    assert slugify("Ink Fox") == "ink-fox"
    assert slugify("  ") == "pet"


def test_hatch_prompt_forbids_atlas_grids():
    job = HatchJob(id="h1", pet_id="fox", display_name="Fox", description="plush fox")
    prompt = hatch_prompt(job, "base", 1, "canonical identity")
    assert "unverified base identity candidate only" in prompt
    assert "not an animation row or playable pet" in prompt
    with pytest.raises(ValueError, match="only one base candidate"):
        hatch_prompt(job, "idle", 6, "calm breathing")


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
        {
            "provider": "zen",
            "base_url": "https://example.test/v1",
            "api_key": "x",
            "model_id": "m",
            "timeout": 1,
        },
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


def test_generate_png_never_persists_raw_provider_error_body():
    class FakeResponse:
        status_code = 500
        text = "server echoed api_key=secret-must-not-appear"

        def json(self):
            return {}

    class FakeClient:
        def post(self, url, headers=None, json=None):
            return FakeResponse()

        def close(self):
            return None

    cfg = {
        "provider": "test",
        "base_url": "https://example.test/v1",
        "api_key": "secret-must-not-appear",
        "model_id": "image",
        "timeout": 1,
    }
    with pytest.raises(HatchImageError) as caught:
        generate_png("pet", client=FakeClient(), config=cfg)

    assert str(caught.value) == "image generate failed HTTP 500"
    assert "secret-must-not-appear" not in str(caught.value)


@pytest.mark.parametrize(
    "base_url",
    [
        "file:///tmp/images",
        "https://user:password@example.test/v1",
        "https://example.test/v1?api_key=secret",
        "https://example.test/v1#private",
    ],
)
def test_image_provider_configuration_rejects_unsafe_service_roots(base_url):
    cfg = {
        "provider": "test",
        "base_url": base_url,
        "api_key": "secret",
        "model_id": "image",
        "timeout": 1,
    }

    result = probe_images_endpoint(cfg, client=object())
    assert result["generation_ready"] is False
    assert "secret" not in str(result)
    with pytest.raises(HatchImageError, match="configuration is invalid"):
        generate_png("pet", client=object(), config=cfg)


def test_generate_png_bounds_stream_before_parsing():
    class Response:
        status_code = 200
        headers = {
            "content-type": "application/json",
            "content-length": str(36 * 1024 * 1024 + 1),
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self):
            raise AssertionError("declared oversized responses must not be read")

    class Client:
        def stream(self, method, url, headers=None, json=None):
            assert method == "POST"
            return Response()

    cfg = {
        "provider": "test",
        "base_url": "https://example.test/v1",
        "api_key": "secret",
        "model_id": "image",
        "timeout": 1,
    }
    with pytest.raises(HatchImageError, match="36 MiB"):
        generate_png("pet", client=Client(), config=cfg)


def test_generate_png_rejects_infinite_empty_chunk_shape():
    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self):
            yield from (b"" for _ in range(4097))

    class Client:
        def stream(self, method, url, headers=None, json=None):
            return Response()

    cfg = {
        "provider": "test",
        "base_url": "https://example.test/v1",
        "api_key": "secret",
        "model_id": "image",
        "timeout": 1,
    }
    with pytest.raises(HatchImageError, match="chunk safety bound"):
        generate_png("pet", client=Client(), config=cfg)


def test_generate_png_rejects_nonfinite_json_and_invalid_base64_shape():
    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self):
            yield b'{"data":[{"b64_json":123}],"cost":NaN}'

    class Client:
        def stream(self, method, url, headers=None, json=None):
            return Response()

    cfg = {
        "provider": "test",
        "base_url": "https://example.test/v1",
        "api_key": "secret",
        "model_id": "image",
        "timeout": 1,
    }
    with pytest.raises(HatchImageError, match="invalid JSON"):
        generate_png("pet", client=Client(), config=cfg)


def test_generate_png_rejects_duplicate_json_keys():
    class Response:
        status_code = 200
        headers = {"content-type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self):
            yield b'{"data":[],"data":[{"b64_json":"spoofed"}]}'

    class Client:
        def stream(self, method, url, headers=None, json=None):
            return Response()

    cfg = {
        "provider": "test",
        "base_url": "https://example.test/v1",
        "api_key": "secret",
        "model_id": "image",
        "timeout": 1,
    }
    with pytest.raises(HatchImageError, match="invalid JSON"):
        generate_png("pet", client=Client(), config=cfg)


def test_generate_png_bounds_prompt_and_size_before_network():
    cfg = {
        "provider": "test",
        "base_url": "https://example.test/v1",
        "api_key": "secret",
        "model_id": "image",
        "timeout": 1,
    }
    with pytest.raises(HatchImageError, match="32 KiB"):
        generate_png("x" * 32_769, client=object(), config=cfg)
    with pytest.raises(HatchImageError, match="unsupported image size"):
        generate_png("pet", size="99999x99999", client=object(), config=cfg)


def test_hatch_registry_roundtrip(tmp_path: Path):
    registry = HatchRegistry(tmp_path)
    job = HatchJob(id="hatch_1", pet_id="fox", display_name="Fox", description="plush fox")
    registry.create(job)
    loaded = HatchRegistry(tmp_path).get("hatch_1")
    assert loaded is not None
    assert loaded.display_name == "Fox"
    assert loaded.jobs_total == 1
    assert loaded.status == "needs_authorization"


def test_hatch_registry_refuses_duplicate_job_ids(tmp_path: Path):
    registry = HatchRegistry(tmp_path)
    job = HatchJob(id="hatch_1", pet_id="fox", display_name="Fox", description="fox")
    registry.create(job)
    with pytest.raises(ValueError, match="already exists"):
        registry.create(job)


def test_legacy_registry_admission_is_fail_closed(tmp_path: Path):
    registry = HatchRegistry(tmp_path)
    first = HatchJob(id="hatch_1", pet_id="fox", display_name="Fox", description="fox")
    with pytest.raises(HatchAuthorizationError, match="bound hatch authorization"):
        registry.create_if_idle(first)
    with pytest.raises(HatchAuthorizationError, match="bound hatch authorization"):
        registry.create_if_idle(
            HatchJob(id="hatch_2", pet_id="owl", display_name="Owl", description="owl")
        )
    assert registry.list_jobs() == []


def test_hatch_registry_rejects_persisted_path_escape_and_bounds_records(tmp_path: Path):
    (tmp_path / "bad.json").write_text(
        '{"id":"../escape","pet_id":"fox","display_name":"Fox",'
        '"description":"fox","status":"running"}',
        encoding="utf-8",
    )
    (tmp_path / "huge.json").write_bytes(b"{" + b"x" * 65_536)

    registry = HatchRegistry(tmp_path)

    jobs = registry.list_jobs()
    assert len(jobs) == 2
    assert all(job.pet_id == "legacy-corrupt" for job in jobs)
    assert not (tmp_path.parent / "escape.json").exists()
    with pytest.raises(ValueError, match="invalid hatch job id"):
        registry._path("../escape")


@pytest.mark.parametrize(
    "record",
    [
        (
            '{"id":"hatch_1","id":"hatch_2","pet_id":"fox",'
            '"display_name":"Fox","description":"fox"}'
        ),
        (
            '{"id":"hatch_1","pet_id":"fox","display_name":"Fox",'
            '"description":"fox","jobs_complete":NaN}'
        ),
        (
            '{"id":"hatch_1","pet_id":"fox","display_name":"Fox",'
            '"description":"fox","unexpected":true}'
        ),
    ],
)
def test_hatch_registry_rejects_ambiguous_or_unknown_persisted_fields(
    tmp_path: Path, record: str
):
    (tmp_path / "hatch_1.json").write_text(record, encoding="utf-8")

    jobs = HatchRegistry(tmp_path).list_jobs()
    assert len(jobs) == 1
    assert jobs[0].pet_id == "legacy-corrupt"


def test_generated_art_is_validated_and_normalized_to_png(tmp_path: Path):
    source = Image.new("RGB", (32, 24), (1, 2, 3))
    encoded = BytesIO()
    source.save(encoded, format="JPEG")

    path = write_generated(tmp_path, "idle", encoded.getvalue())

    with Image.open(path) as saved:
        assert saved.format == "PNG"
        assert saved.mode == "RGBA"


def test_generated_art_rejects_non_image_bytes(tmp_path: Path):
    with pytest.raises(HatchImageError, match="invalid or unsafe"):
        write_generated(tmp_path, "idle", b"<html>not an image</html>")


def test_generated_art_rejects_path_escape_name(tmp_path: Path):
    source = Image.new("RGB", (8, 8), (1, 2, 3))
    encoded = BytesIO()
    source.save(encoded, format="PNG")
    with pytest.raises(HatchImageError, match="name is invalid"):
        write_generated(tmp_path, "../escape", encoded.getvalue())
    assert not (tmp_path.parent / "escape.png").exists()


def _authorized_job(registry, job, cfg, *, key):
    if len(key) < 16:
        key = f"hatch-test-key-{key}"
    authorization = authorize_hatch(
        job,
        principal="operator:test",
        idempotency_key=key,
        config=cfg,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    return registry.create_or_replay(job, authorization)


def _hatch_test_config():
    return {
        "provider": "test",
        "base_url": "https://example.test/v1",
        "api_key": "secret",
        "model_id": "image",
        "timeout": 1,
    }


def test_unexpected_hatch_failure_is_uncertain_without_provider_detail(
    tmp_path, monkeypatch
):
    registry = HatchRegistry(tmp_path)
    cfg = _hatch_test_config()
    job = HatchJob(
        id="hatch_failure", pet_id="fox", display_name="Fox", description="fox"
    )
    _authorized_job(registry, job, cfg, key="failure")

    def fail_generation(*_args, **_kwargs):
        raise OSError("sensitive provider response")

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", fail_generation)

    result = run_hatch_job(registry, job.id, config=cfg)
    persisted = HatchRegistry(tmp_path).get(job.id)
    assert result.status == "delivery_uncertain"
    assert persisted is not None and persisted.status == "delivery_uncertain"
    assert "sensitive provider response" not in (result.error or "")


def test_hatch_does_not_generate_without_bound_runtime_provider(tmp_path, monkeypatch):
    registry = HatchRegistry(tmp_path)
    cfg = _hatch_test_config()
    job = HatchJob(
        id="hatch_not_ready", pet_id="fox", display_name="Fox", description="fox"
    )
    _authorized_job(registry, job, cfg, key="not-ready")
    monkeypatch.setattr("pex_bridge.pets.hatch.hatch_image_config", lambda: None)

    def must_not_generate(*_args, **_kwargs):
        raise AssertionError("generation must not start")

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", must_not_generate)
    result = run_hatch_job(registry, job.id)

    assert result.status == "queued"
    assert result.jobs_complete == 0
    assert "no call was made" in (result.error or "")


def test_hatch_claim_prevents_duplicate_billable_sequence(tmp_path, monkeypatch):
    registry = HatchRegistry(tmp_path)
    cfg = _hatch_test_config()
    job = HatchJob(
        id="hatch_once", pet_id="fox", display_name="Fox", description="fox"
    )
    _authorized_job(registry, job, cfg, key="once")
    source = Image.new("RGB", (8, 8), (1, 2, 3))
    encoded = BytesIO()
    source.save(encoded, format="PNG")
    calls = 0

    def generate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return encoded.getvalue()

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", generate)

    first = run_hatch_job(registry, job.id, config=cfg)
    second = run_hatch_job(registry, job.id, config=cfg)

    assert first.status == "awaiting_assembly_qa"
    assert second.status == "awaiting_assembly_qa"
    assert calls == 1
    assert first.jobs_complete == first.jobs_total == 1


def test_hatch_claim_fails_unacknowledged_job_without_provider_io(
    tmp_path, monkeypatch
):
    registry = HatchRegistry(tmp_path)
    registry.create(
        HatchJob(id="hatch_no_ack", pet_id="fox", display_name="Fox", description="fox")
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("unacknowledged hatch must not touch the image provider")

    monkeypatch.setattr("pex_bridge.pets.hatch.hatch_image_config", forbidden)
    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", forbidden)

    result = run_hatch_job(registry, "hatch_no_ack")

    assert result.status == "needs_authorization"
    assert result.jobs_complete == 0
    assert "boolean charge acknowledgement" in (result.error or "")
