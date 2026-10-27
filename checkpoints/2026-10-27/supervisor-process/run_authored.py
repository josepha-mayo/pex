"""Fresh-process test entry. No production activation, provider or key input."""

from pathlib import Path

from process_adapter import initialize_process

if __name__ == "__main__":
    assert initialize_process() == {
        "trace": "NoOpTracerProvider",
        "metrics": "NoOpMeterProvider",
    }
    import pytest

    raise SystemExit(
        pytest.main(["-q", str(Path(__file__).with_name("test_process.py")), str(Path(__file__).with_name("test_pilot.py"))])
    )
