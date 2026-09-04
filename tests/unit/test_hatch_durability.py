from __future__ import annotations

import json
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path

import pytest
from pex_bridge.pets.hatch import (
    HatchAuthorization,
    HatchAuthorizationError,
    HatchConflictError,
    HatchJob,
    HatchRegistry,
    authorize_hatch,
    run_hatch_job,
    write_candidate_receipt,
    write_generated,
)
from pex_bridge.pets.hatch_store import _assert_existing_regular_file
from pex_bridge.pets.imagegen import HatchImageError
from PIL import Image

BASE_TIME = datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_transient_sqlite_sidecar_absence_is_safe_but_non_files_fail_closed(
    tmp_path: Path,
) -> None:
    vanished = tmp_path / "hatch.sqlite3-wal"
    _assert_existing_regular_file(vanished, label="hatch database path")

    database = tmp_path / "hatch.sqlite3"
    database.write_bytes(b"")
    _assert_existing_regular_file(database, label="hatch database path")

    unsafe = tmp_path / "hatch.sqlite3-shm"
    unsafe.mkdir()
    with pytest.raises(HatchAuthorizationError, match="database path is unsafe"):
        _assert_existing_regular_file(unsafe, label="hatch database path")


def _config(
    *,
    provider: str = "test-provider",
    endpoint: str = "https://images.example.test/v1",
    model: str = "image-v1",
    secret: str = "test-secret",
    timeout: float = 10.0,
) -> dict[str, object]:
    return {
        "provider": provider,
        "base_url": endpoint,
        "model_id": model,
        "api_key": secret,
        "timeout": timeout,
    }


def _job(job_id: str = "hatch_1", *, description: str = "small plush fox") -> HatchJob:
    return HatchJob(
        id=job_id,
        pet_id="fox",
        display_name="Fox",
        description=description,
        style_preset="plush",
        pet_notes=description,
    )


def _authorization(
    job: HatchJob,
    *,
    key: str = "request-1",
    config: dict[str, object] | None = None,
    issued: datetime = BASE_TIME,
    expires: datetime | None = None,
    acknowledge: bool = False,
    prior_job_id: str | None = None,
    prior_effect_id: str | None = None,
):
    if len(key) < 16:
        key = f"hatch-test-key-{key}"
    return authorize_hatch(
        job,
        principal="operator:test",
        idempotency_key=key,
        config=config or _config(),
        issued_at=issued,
        expires_at=expires or issued + timedelta(minutes=10),
        acknowledge_possible_duplicate=acknowledge,
        duplicate_risk_job_id=prior_job_id,
        duplicate_risk_effect_id=prior_effect_id,
    )


def _png_bytes() -> bytes:
    image = Image.new("RGB", (32, 24), (10, 20, 30))
    encoded = BytesIO()
    image.save(encoded, format="PNG")
    image.close()
    return encoded.getvalue()


def test_create_or_replay_binds_request_provider_and_authorization(tmp_path: Path):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job()
    authorization = _authorization(job)

    created = registry.create_or_replay(job, authorization)
    replay = registry.create_or_replay(_job("another_id"), authorization)

    assert created.id == "hatch_1"
    assert replay.id == created.id
    assert created.jobs_total == 1
    assert created.effect_status == "reserved"
    assert created.spritesheet is None

    changed_job = _job("changed", description="different fox")
    changed_auth = _authorization(changed_job)
    with pytest.raises(HatchConflictError, match="idempotency key"):
        registry.create_or_replay(changed_job, changed_auth)

    changed_provider = _config(endpoint="https://other.example.test/v1")
    provider_auth = _authorization(_job("provider_changed"), config=changed_provider)
    with pytest.raises(HatchConflictError, match="idempotency key"):
        registry.create_or_replay(_job("provider_changed"), provider_auth)


def test_hatch_authorization_contract_cannot_expand_beyond_one_provider_call():
    authorization = _authorization(_job())
    assert authorization.max_calls == 1
    expanded = authorization.model_dump(mode="json")
    expanded["max_calls"] = 2

    with pytest.raises(ValueError, match="1"):
        HatchAuthorization.model_validate(expanded)


@pytest.mark.parametrize(
    "key",
    ["short", " leading-key-0001", "invalid key 0001", "x" * 129],
)
def test_hatch_authorization_rejects_unbounded_idempotency_keys(key: str):
    with pytest.raises(HatchAuthorizationError, match="idempotency_key"):
        authorize_hatch(
            _job(),
            principal="operator:test",
            idempotency_key=key,
            config=_config(),
            issued_at=BASE_TIME,
            expires_at=BASE_TIME + timedelta(minutes=10),
        )


def test_legacy_boolean_only_create_if_idle_is_fail_closed(tmp_path: Path, monkeypatch):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("legacy admission must not call the provider")

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", forbidden)
    with pytest.raises(HatchAuthorizationError, match="bound hatch authorization"):
        registry.create_if_idle(
            _job().model_copy(update={"paid_generation_acknowledged": True})
        )
    assert registry.list_jobs() == []


def test_two_registry_instances_create_and_dispatch_once(tmp_path: Path, monkeypatch):
    first = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    second = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job()
    authorization = _authorization(job)

    with ThreadPoolExecutor(max_workers=2) as pool:
        created = list(
            pool.map(
                lambda registry: registry.create_or_replay(job, authorization),
                [first, second],
            )
        )
    assert {item.id for item in created} == {job.id}

    calls = 0
    calls_lock = threading.Lock()
    started = threading.Event()
    release = threading.Event()

    def generate(*_args, **_kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        started.set()
        assert release.wait(timeout=3)
        return _png_bytes()

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", generate)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_one = pool.submit(run_hatch_job, first, job.id, config=_config())
        assert started.wait(timeout=3)
        future_two = pool.submit(run_hatch_job, second, job.id, config=_config())
        release.set()
        results = [future_one.result(timeout=5), future_two.result(timeout=5)]

    assert calls == 1
    assert {item.status for item in results} == {"awaiting_assembly_qa"}
    effect = first.get_effect(job.id)
    assert effect is not None
    assert effect.state == "delivered"
    assert effect.attempt_count == 1


def test_global_billable_dispatch_is_serialized(tmp_path: Path):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    first = _job("hatch_first")
    second = _job("hatch_second", description="small plush owl")
    second = second.model_copy(
        update={"pet_id": "owl", "display_name": "Owl", "pet_notes": "small plush owl"}
    )
    registry.create_or_replay(first, _authorization(first, key="first"))
    registry.create_or_replay(second, _authorization(second, key="second"))

    first_claim = registry.claim_for_dispatch(first.id, _config())
    second_claim = registry.claim_for_dispatch(second.id, _config())

    assert first_claim.claimed is True
    assert second_claim.claimed is False
    assert second_claim.reason == "global_dispatch_busy"
    second_effect = registry.get_effect(second.id)
    assert second_effect is not None
    assert second_effect.state == "reserved"
    assert second_effect.attempt_count == 0


def test_uncertain_retry_requires_exact_prior_effect_acknowledgement(
    tmp_path: Path, monkeypatch
):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    original = _job("hatch_uncertain")
    registry.create_or_replay(original, _authorization(original, key="original"))

    def fail_after_dispatch(*_args, **_kwargs):
        raise HatchImageError("transport outcome is not proof of no delivery")

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", fail_after_dispatch)
    uncertain = run_hatch_job(registry, original.id, config=_config())
    assert uncertain.status == "delivery_uncertain"
    assert uncertain.effect_id is not None

    retry = _job("hatch_retry")
    with pytest.raises(HatchAuthorizationError, match="exact uncertain effect"):
        registry.create_or_replay(retry, _authorization(retry, key="retry"))

    wrong = _authorization(
        retry,
        key="retry-wrong",
        acknowledge=True,
        prior_job_id=original.id,
        prior_effect_id=f"effect_{'0' * 64}",
    )
    with pytest.raises(HatchAuthorizationError, match="exact uncertain effect"):
        registry.create_or_replay(retry, wrong)

    exact = _authorization(
        retry,
        key="retry-exact",
        acknowledge=True,
        prior_job_id=original.id,
        prior_effect_id=uncertain.effect_id,
    )
    admitted = registry.create_or_replay(retry, exact)
    assert admitted.effect_status == "reserved"
    assert admitted.possible_duplicate_acknowledged is True


def test_pre_admitted_retry_is_rechecked_if_prior_dispatch_becomes_uncertain(
    tmp_path: Path,
):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    first = _job("pre_admitted_first")
    second = _job("pre_admitted_second")
    registry.create_or_replay(first, _authorization(first, key="pre-first"))
    registry.create_or_replay(second, _authorization(second, key="pre-second"))

    first_claim = registry.claim_for_dispatch(first.id, _config())
    assert first_claim.effect is not None
    assert first_claim.effect.dispatch_token is not None
    registry.finalize_uncertain(
        first.id,
        dispatch_token=first_claim.effect.dispatch_token,
        error_code="simulated_uncertain",
    )

    second_claim = registry.claim_for_dispatch(second.id, _config())
    second_effect = registry.get_effect(second.id)
    assert second_claim.claimed is False
    assert second_effect is not None
    assert second_effect.state == "skipped"
    assert second_effect.attempt_count == 0


def test_authorization_expiry_blocks_before_provider_io(tmp_path: Path, monkeypatch):
    clock = [BASE_TIME]
    registry = HatchRegistry(tmp_path, clock=lambda: clock[0])
    job = _job("hatch_expiry")
    authorization = _authorization(job, expires=BASE_TIME + timedelta(seconds=5))
    registry.create_or_replay(job, authorization)
    clock[0] = BASE_TIME + timedelta(seconds=6)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("expired authorization must not call the provider")

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", forbidden)
    result = run_hatch_job(registry, job.id, config=_config())
    effect = registry.get_effect(job.id)

    assert result.status == "needs_authorization"
    assert effect is not None
    assert effect.state == "skipped"
    assert effect.attempt_count == 0

    expired_job = _job("already_expired")
    expired = _authorization(
        expired_job,
        key="expired",
        issued=BASE_TIME,
        expires=BASE_TIME + timedelta(seconds=1),
    )
    with pytest.raises(HatchAuthorizationError, match="expired"):
        registry.create_or_replay(expired_job, expired)


def test_provider_mismatch_blocks_and_secret_is_never_persisted(
    tmp_path: Path, monkeypatch
):
    secret = "CANARY-HATCH-SECRET-MUST-NOT-PERSIST"
    authorized_config = _config(secret=secret)
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job("hatch_provider")
    authorization = _authorization(job, config=authorized_config)
    registry.create_or_replay(job, authorization)

    assert secret not in repr(authorization)
    assert secret not in authorization.model_dump_json()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("mismatched provider must not generate")

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", forbidden)
    mismatch = _config(endpoint="https://other.example.test/v1", secret="other")
    result = run_hatch_job(registry, job.id, config=mismatch)
    effect = registry.get_effect(job.id)

    assert result.status == "queued"
    assert "mismatch" in (result.error or "")
    assert effect is not None
    assert effect.state == "reserved"
    assert effect.attempt_count == 0
    for database_file in tmp_path.glob("hatch.sqlite3*"):
        assert secret.encode() not in database_file.read_bytes()


def test_dispatch_deadline_is_conservative_and_late_finalizer_loses_cas(tmp_path: Path):
    clock = [BASE_TIME]
    registry = HatchRegistry(tmp_path, clock=lambda: clock[0])
    job = _job("hatch_deadline")
    registry.create_or_replay(job, _authorization(job))
    claim = registry.claim_for_dispatch(job.id, _config(timeout=120.0))
    assert claim.claimed is True
    assert claim.effect is not None
    assert claim.effect.dispatch_token is not None
    deadline = datetime.fromisoformat(
        claim.effect.dispatch_deadline_at.replace("Z", "+00:00")
    )
    assert deadline > BASE_TIME + timedelta(seconds=120)

    clock[0] = deadline - timedelta(seconds=1)
    still_live = HatchRegistry(tmp_path, clock=lambda: clock[0])
    assert still_live.get_effect(job.id).state == "dispatching"  # type: ignore[union-attr]

    clock[0] = deadline + timedelta(seconds=1)
    recovered = HatchRegistry(tmp_path, clock=lambda: clock[0])
    assert recovered.get_effect(job.id).state == "delivery_uncertain"  # type: ignore[union-attr]

    late = registry.finalize_delivered(
        job.id,
        dispatch_token=claim.effect.dispatch_token,
    )
    assert late.status == "delivery_uncertain"
    assert recovered.get_effect(job.id).state == "delivery_uncertain"  # type: ignore[union-attr]


def test_restart_reconciles_valid_local_base_without_provider_call(tmp_path: Path):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job("hatch_reconcile")
    registry.create_or_replay(job, _authorization(job))
    claim = registry.claim_for_dispatch(job.id, _config())
    assert claim.claimed is True and claim.effect is not None

    asset = write_generated(tmp_path / job.id, "base", _png_bytes())
    write_candidate_receipt(registry, claim.job, claim.effect, asset)
    reference = tmp_path / job.id / "references" / "canonical-base.png"

    restarted = HatchRegistry(tmp_path, clock=lambda: BASE_TIME + timedelta(seconds=1))
    result = restarted.get(job.id)
    effect = restarted.get_effect(job.id)

    assert result is not None
    assert result.status == "awaiting_assembly_qa"
    assert result.jobs_complete == 1
    assert effect is not None
    assert effect.state == "delivered"
    assert reference.read_bytes() == asset.read_bytes()


def test_cancellation_before_and_after_dispatch_is_conservative(tmp_path: Path):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    before = _job("hatch_cancel_before")
    registry.create_or_replay(before, _authorization(before, key="before"))
    before_result = registry.cancel(before.id)
    before_effect = registry.get_effect(before.id)
    assert before_result.status == "interrupted"
    assert before_effect is not None
    assert before_effect.state == "skipped"
    assert before_effect.attempt_count == 0

    after = _job("hatch_cancel_after")
    registry.create_or_replay(after, _authorization(after, key="after"))
    claim = registry.claim_for_dispatch(after.id, _config())
    assert claim.effect is not None and claim.effect.dispatch_token is not None
    after_result = registry.cancel(after.id)
    assert after_result.status == "delivery_uncertain"
    late = registry.finalize_delivered(
        after.id,
        dispatch_token=claim.effect.dispatch_token,
    )
    assert late.status == "delivery_uncertain"


def test_base_generation_is_one_call_and_never_claims_playable_pet(
    tmp_path: Path, monkeypatch
):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job("hatch_once")
    registry.create_or_replay(job, _authorization(job))
    calls = 0

    def generate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return _png_bytes()

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", generate)
    first = run_hatch_job(registry, job.id, config=_config())
    second = run_hatch_job(registry, job.id, config=_config())

    assert calls == 1
    assert first.status == second.status == "awaiting_assembly_qa"
    assert first.jobs_complete == first.jobs_total == 1
    assert first.spritesheet is None
    receipt = json.loads(
        (tmp_path / job.id / "candidate-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["playable_pet"] is False
    assert receipt["qa_status"] == "awaiting_grounded_assembly_and_independent_qa"


def test_post_dispatch_baseexception_is_uncertain_and_not_replayed(
    tmp_path: Path, monkeypatch
):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job("hatch_cancelled_thread")
    registry.create_or_replay(job, _authorization(job))
    calls = 0

    def cancelled(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise KeyboardInterrupt

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", cancelled)
    with pytest.raises(KeyboardInterrupt):
        run_hatch_job(registry, job.id, config=_config())
    result = registry.get(job.id)
    assert result is not None
    assert result.status == "delivery_uncertain"

    replay = run_hatch_job(registry, job.id, config=_config())
    assert replay.status == "delivery_uncertain"
    assert calls == 1


def test_legacy_json_migration_is_visible_unverified_and_zero_call(tmp_path: Path):
    (tmp_path / "legacy_running.json").write_text(
        json.dumps(
            {
                "id": "legacy_running",
                "pet_id": "fox",
                "display_name": "Fox",
                "description": "fox",
                "status": "running",
                "jobs_complete": 2,
                "jobs_total": 13,
                "paid_generation_acknowledged": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "legacy_complete.json").write_text(
        json.dumps(
            {
                "id": "legacy_complete",
                "pet_id": "owl",
                "display_name": "Owl",
                "description": "owl",
                "status": "complete",
                "jobs_complete": 13,
                "jobs_total": 13,
                "spritesheet": "unsafe/legacy.webp",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "corrupt.json").write_text(
        '{"id":"corrupt","id":"duplicate","secret":"must-not-surface"}',
        encoding="utf-8",
    )

    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    running = registry.get("legacy_running")
    complete = registry.get("legacy_complete")
    corrupt = [job for job in registry.list_jobs() if job.pet_id == "legacy-corrupt"]

    assert running is not None and running.status == "needs_authorization"
    assert complete is not None and complete.status == "awaiting_assembly_qa"
    assert complete.jobs_total == 1
    assert complete.spritesheet is None
    assert len(corrupt) == 1
    assert "must-not-surface" not in json.dumps(corrupt[0].public())
    audit = registry.legacy_import_audit()
    assert len(audit) == 3
    assert {item["outcome"] for item in audit} == {
        "imported_unverified",
        "corrupt_visible",
    }


def test_concurrent_fresh_authorization_timing_replays_logical_request(tmp_path: Path):
    first_registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    second_registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    first_job = _job("fresh_auth_first")
    second_job = _job("fresh_auth_second")
    first_auth = _authorization(first_job, key="logical-retry", issued=BASE_TIME)
    second_auth = _authorization(
        second_job,
        key="logical-retry",
        issued=BASE_TIME + timedelta(seconds=1),
    )
    assert first_auth.authorization_id != second_auth.authorization_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(first_registry.create_or_replay, first_job, first_auth),
            pool.submit(second_registry.create_or_replay, second_job, second_auth),
        ]
        results = [future.result(timeout=5) for future in futures]

    assert results[0].id == results[1].id
    assert len(first_registry.list_jobs()) == 1


def test_authorization_lifetime_and_server_not_before_are_bounded(tmp_path: Path):
    job = _job("time_bounds")
    with pytest.raises(ValueError, match="15 minute maximum"):
        _authorization(
            job,
            issued=BASE_TIME,
            expires=BASE_TIME + timedelta(minutes=16),
        )

    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    future = _authorization(
        job,
        issued=BASE_TIME + timedelta(seconds=31),
        expires=BASE_TIME + timedelta(minutes=10),
    )
    with pytest.raises(HatchAuthorizationError, match="not yet valid"):
        registry.create_or_replay(job, future)

    within_skew = _job("time_bounds_within_skew")
    accepted = registry.create_or_replay(
        within_skew,
        _authorization(
            within_skew,
            key="within-skew",
            issued=BASE_TIME + timedelta(seconds=30),
            expires=BASE_TIME + timedelta(minutes=10),
        ),
    )
    assert accepted.effect_status == "reserved"


def test_asset_without_receipt_never_reconciles_and_expires_uncertain(tmp_path: Path):
    clock = [BASE_TIME]
    registry = HatchRegistry(tmp_path, clock=lambda: clock[0])
    job = _job("asset_without_receipt")
    registry.create_or_replay(job, _authorization(job))
    claim = registry.claim_for_dispatch(job.id, _config())
    assert claim.claimed is True and claim.effect is not None
    write_generated(tmp_path / job.id, "base", _png_bytes())

    clock[0] = BASE_TIME + timedelta(seconds=1)
    restarted = HatchRegistry(tmp_path, clock=lambda: clock[0])
    assert restarted.get_effect(job.id).state == "dispatching"  # type: ignore[union-attr]
    assert restarted.get(job.id).status == "running"  # type: ignore[union-attr]

    deadline = datetime.fromisoformat(
        claim.effect.dispatch_deadline_at.replace("Z", "+00:00")
    )
    clock[0] = deadline + timedelta(seconds=1)
    expired = HatchRegistry(tmp_path, clock=lambda: clock[0])
    assert expired.get_effect(job.id).state == "delivery_uncertain"  # type: ignore[union-attr]


def test_receipt_mismatch_blocks_finalize_and_reconciliation(tmp_path: Path):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job("receipt_mismatch")
    registry.create_or_replay(job, _authorization(job))
    claim = registry.claim_for_dispatch(job.id, _config())
    assert claim.claimed is True and claim.effect is not None
    assert claim.effect.dispatch_token is not None
    asset = write_generated(tmp_path / job.id, "base", _png_bytes())
    receipt_path = write_candidate_receipt(registry, claim.job, claim.effect, asset)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["request_fingerprint"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(HatchConflictError, match="exact provenance"):
        registry.finalize_delivered(
            job.id, dispatch_token=claim.effect.dispatch_token
        )
    restarted = HatchRegistry(tmp_path, clock=lambda: BASE_TIME + timedelta(seconds=1))
    assert restarted.get_effect(job.id).state == "dispatching"  # type: ignore[union-attr]


def test_preplanted_asset_blocks_dispatch_before_provider_call(tmp_path: Path, monkeypatch):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job("preplanted_asset")
    registry.create_or_replay(job, _authorization(job))
    write_generated(tmp_path / job.id, "base", _png_bytes())

    def forbidden(*_args, **_kwargs):
        raise AssertionError("preplanted artifact must block provider dispatch")

    monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", forbidden)
    result = run_hatch_job(registry, job.id, config=_config())
    effect = registry.get_effect(job.id)
    assert result.status == "queued"
    assert "pre-existing" in (result.error or "")
    assert effect is not None and effect.attempt_count == 0


def test_symlinked_job_parent_blocks_all_artifact_writes(tmp_path: Path, monkeypatch):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job("symlink_parent")
    registry.create_or_replay(job, _authorization(job))
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    try:
        try:
            (tmp_path / job.id).symlink_to(outside, target_is_directory=True)
        except OSError:
            created = subprocess.run(
                [
                    "cmd",
                    "/c",
                    "mklink",
                    "/J",
                    str(tmp_path / job.id),
                    str(outside),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if created.returncode != 0:
                pytest.skip("directory link creation is unavailable on this host")

        def forbidden(*_args, **_kwargs):
            raise AssertionError("symlinked artifact parent must block provider dispatch")

        monkeypatch.setattr("pex_bridge.pets.hatch.generate_png", forbidden)
        result = run_hatch_job(registry, job.id, config=_config())
        effect = registry.get_effect(job.id)
        assert result.status == "queued"
        assert effect is not None and effect.attempt_count == 0
        assert list(outside.iterdir()) == []
    finally:
        if (tmp_path / job.id).is_symlink():
            (tmp_path / job.id).unlink()
        elif (tmp_path / job.id).is_junction():
            (tmp_path / job.id).rmdir()
        outside.rmdir()


def test_wrong_dispatch_token_is_an_explicit_conflict(tmp_path: Path):
    registry = HatchRegistry(tmp_path, clock=lambda: BASE_TIME)
    job = _job("wrong_token")
    registry.create_or_replay(job, _authorization(job))
    claim = registry.claim_for_dispatch(job.id, _config())
    assert claim.claimed is True

    with pytest.raises(HatchConflictError, match="token does not match"):
        registry.finalize_delivered(job.id, dispatch_token="wrong-token")
    with pytest.raises(HatchConflictError, match="token does not match"):
        registry.finalize_uncertain(
            job.id, dispatch_token="wrong-token", error_code="test"
        )
    effect = registry.get_effect(job.id)
    assert effect is not None and effect.state == "dispatching"
