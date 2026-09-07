"""Cold validation must not fan out full atlas decoding under concurrent reads."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier, Event, Lock

import pex_bridge.pets as pets
import pytest


@pytest.mark.parametrize("same_path", [True, False])
def test_cold_pet_validation_is_single_flight_and_bounded(tmp_path, monkeypatch, same_path):
    paths = [tmp_path / f"sheet-{index}.webp" for index in range(4)]
    for path in paths:
        path.write_bytes(b"fixture")
    entered = Event()
    repeated = Event()
    release = Event()
    guard = Lock()
    start = Barrier(4)
    active = 0
    calls = 0

    @contextmanager
    def fake_open(_path):
        yield object()

    def validate(_image):
        nonlocal active, calls
        with guard:
            active += 1
            calls += 1
            if active > (1 if same_path else pets.MAX_CONCURRENT_SHEET_VALIDATIONS):
                repeated.set()
        entered.set()
        try:
            assert release.wait(2)
        finally:
            with guard:
                active -= 1

    monkeypatch.setattr(pets.Image, "open", fake_open)
    monkeypatch.setattr(pets, "validate_codex_v2_atlas", validate)

    def inspect(index):
        start.wait(timeout=2)
        path = paths[0] if same_path else paths[index]
        return pets._valid_v2_sheet(str(path), 7, 1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(inspect, index) for index in range(4)]
        try:
            assert entered.wait(1)
            concurrent = repeated.wait(0.05)
        finally:
            release.set()
        results = [future.result(timeout=2) for future in futures]
    assert not concurrent, "cold requests exceeded the bounded decode concurrency"
    assert sum(results) == (4 if same_path else pets.MAX_CONCURRENT_SHEET_VALIDATIONS)
    assert calls == (1 if same_path else pets.MAX_CONCURRENT_SHEET_VALIDATIONS)
    if not same_path:
        # Busy is not permanently cached as invalid.
        assert all(pets._valid_v2_sheet(str(path), 7, 1) for path in paths)
        assert calls == 4


def test_pet_validation_cache_still_invalidates_changed_file_metadata(tmp_path, monkeypatch):
    path = tmp_path / "sheet.webp"
    path.write_bytes(b"fixture")
    calls = []

    @contextmanager
    def fake_open(_path):
        calls.append(str(_path))
        yield object()

    monkeypatch.setattr(pets.Image, "open", fake_open)
    monkeypatch.setattr(pets, "validate_codex_v2_atlas", lambda _image: None)
    assert pets._valid_v2_sheet(str(path), 7, 1)
    assert pets._valid_v2_sheet(str(path), 7, 1)
    assert pets._valid_v2_sheet(str(path), 8, 2)
    assert len(calls) == 2


def test_cached_pet_is_not_blocked_by_unrelated_cold_validation(tmp_path, monkeypatch):
    hot = tmp_path / "hot.webp"
    cold = tmp_path / "cold.webp"
    for path in (hot, cold):
        path.write_bytes(b"fixture")
    entered = Event()
    release = Event()

    @contextmanager
    def fake_open(path):
        yield path

    def validate(path):
        if path == cold:
            entered.set()
            assert release.wait(2)

    monkeypatch.setattr(pets.Image, "open", fake_open)
    monkeypatch.setattr(pets, "validate_codex_v2_atlas", validate)
    assert pets._valid_v2_sheet(str(hot), 7, 1)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(pets._valid_v2_sheet, str(cold), 7, 1)
        try:
            assert entered.wait(1)
            cached = pool.submit(pets._valid_v2_sheet, str(hot), 7, 1)
            assert cached.result(timeout=0.1)
        finally:
            release.set()
        assert pending.result(timeout=2)


def test_duplicate_slow_validation_wait_is_bounded_and_does_not_cache_busy(tmp_path, monkeypatch):
    path = tmp_path / "slow.webp"
    path.write_bytes(b"fixture")
    entered = Event()
    release = Event()

    def decode(*_args):
        entered.set()
        assert release.wait(2)
        return True

    monkeypatch.setattr(pets, "_decode_valid_v2_sheet", decode)
    monkeypatch.setattr(pets, "SHEET_VALIDATION_WAIT_SECONDS", 0.02)
    with ThreadPoolExecutor(max_workers=2) as pool:
        owner = pool.submit(pets._valid_v2_sheet, str(path), 7, 1)
        try:
            assert entered.wait(1)
            duplicate = pool.submit(pets._valid_v2_sheet, str(path), 7, 1)
            assert duplicate.result(timeout=0.2) is False
        finally:
            release.set()
        assert owner.result(timeout=2) is True
    assert pets._valid_v2_sheet(str(path), 7, 1) is True


def test_unexpected_validation_error_releases_its_inflight_slot(tmp_path, monkeypatch):
    path = str(tmp_path / "failed.webp")

    def failed(*_args):
        raise RuntimeError("fixture failure")

    monkeypatch.setattr(pets, "_decode_valid_v2_sheet", failed)
    with pytest.raises(RuntimeError, match="fixture failure"):
        pets._valid_v2_sheet(path, 7, 1)
    assert (path, 7, 1) not in pets._SHEET_IN_FLIGHT
    monkeypatch.setattr(pets, "_decode_valid_v2_sheet", lambda *_args: True)
    assert pets._valid_v2_sheet(path, 7, 1) is True
