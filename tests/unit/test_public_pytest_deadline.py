import time
from tempfile import TemporaryDirectory

import pytest
from pex_bridge.observe import _run_public_pytest


@pytest.mark.parametrize("deadline", [True, float("nan"), float("inf")])
def test_invalid_public_test_deadline_is_rejected_before_dispatch(tmp_path, deadline):
    with pytest.raises(ValueError, match="finite"):
        _run_public_pytest(tmp_path, [], "", deadline=deadline)


def test_expired_public_test_budget_does_not_start_a_process(tmp_path, monkeypatch):
    import pex_bridge.observe as observe

    monkeypatch.setattr(observe.subprocess, "Popen", lambda *a, **k: pytest.fail("dispatched"))
    with pytest.raises(TimeoutError, match="before dispatch"):
        _run_public_pytest(tmp_path, [], "", deadline=time.perf_counter() - 1)


def test_public_test_runtime_respects_short_shared_budget(tmp_path):
    (tmp_path / "test_public.py").write_text(
        "import time\ndef test_slow():\n    time.sleep(10)\n", encoding="utf-8",
    )
    started = time.perf_counter()
    with TemporaryDirectory() as cache:
        result = _run_public_pytest(
            tmp_path, ["test_public.py"], cache, deadline=started + 1,
        )
    assert result["timed_out"] is True
    assert result["ok"] is False
    assert "timed out after" in result["output"]
    assert time.perf_counter() - started < 5
