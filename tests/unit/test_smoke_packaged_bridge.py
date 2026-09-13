from __future__ import annotations

import hashlib
import hmac
from urllib.parse import parse_qs, urlparse

import pytest

from scripts import smoke_packaged_bridge as smoke


class _RunningProcess:
    pid = 123
    returncode = None

    @staticmethod
    def poll() -> None:
        return None


def test_soak_bridge_records_authenticated_health_and_resource_slope(monkeypatch) -> None:
    clock = iter((0.0, 0.0, 1.0, 2.0, 2.1))
    samples = iter(
        (
            {"working_set_bytes": 100, "private_bytes": 80, "cpu_100ns": 10},
            {"working_set_bytes": 120, "private_bytes": 90, "cpu_100ns": 20},
            {"working_set_bytes": 95, "private_bytes": 70, "cpu_100ns": 30},
        )
    )

    def read_json(url: str, *, token: str | None = None) -> dict[str, object]:
        if url.endswith("/v1/supervisor"):
            assert token == "secret"
            return {"max_dispatches_per_session": 3}
        challenge = parse_qs(urlparse(url).query)["challenge"][0]
        proof = hmac.new(b"secret", challenge.encode(), hashlib.sha256).hexdigest()
        return {
            "ok": True,
            "service": "pex-bridge",
            "challenge": challenge,
            "proof": proof,
        }

    monkeypatch.setattr(smoke.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(smoke, "_read_json", read_json)
    monkeypatch.setattr(smoke, "_process_sample", lambda _pid: next(samples))

    result = smoke._soak_bridge(
        port=4010,
        token="secret",
        process=_RunningProcess(),  # type: ignore[arg-type]
        seconds=2.0,
        interval=1.0,
    )

    assert result == {
        "requested_seconds": 2.0,
        "observed_seconds": 2.1,
        "sample_interval_seconds": 1.0,
        "samples": 3,
        "identity_checks": 3,
        "settings_checks": 1,
        "peak_working_set_bytes": 120,
        "peak_private_bytes": 90,
        "working_set_delta_bytes": -5,
        "private_delta_bytes": -10,
        "cpu_seconds": 2e-06,
    }


def test_soak_bridge_fails_when_owned_process_exits() -> None:
    class ExitedProcess:
        pid = 123
        returncode = 7

        @staticmethod
        def poll() -> int:
            return 7

    with pytest.raises(RuntimeError, match="exited during soak with 7"):
        smoke._soak_bridge(
            port=4010,
            token="secret",
            process=ExitedProcess(),  # type: ignore[arg-type]
            seconds=1.0,
            interval=1.0,
        )
