"""Live Nebius ConTree sandbox execution of the public pytest path.

Gated by ``PEX_LIVE_CONTREE=1`` plus real credentials
(``PEX_CONTREE_API_KEY``/``NEBIUS_API_KEY`` and
``PEX_CONTREE_PROJECT``/``NEBIUS_PROJECT_ID``). This exercises the actual
Token Factory Sandboxes API: file dedup, isolated argv spawn, disposable
network-off VM, and operation polling. Requires Nebius Sandboxes beta access.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from pex_bridge.contree import EXECUTOR, contree_config, run_public_pytest_contree

from tests.contract.live_gate import require_live_authorization

pytestmark = pytest.mark.live_contree


def _manifest(root: Path, files: dict[str, str]) -> list[dict]:
    rows = []
    for relative, text in files.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode()
        path.write_bytes(data)
        rows.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    return rows


@pytest.fixture
def _live_contree():
    require_live_authorization("PEX_LIVE_CONTREE")
    config = contree_config()
    missing = config.missing_reasons()
    if missing:
        pytest.skip(f"contree credentials not configured: {'; '.join(missing)}")
    return config


def test_live_contree_runs_public_pytest_in_a_disposable_vm(tmp_path: Path, _live_contree):
    manifest = _manifest(
        tmp_path,
        {
            "app.py": "def add(a, b):\n    return a + b\n",
            "test_app.py": (
                "from app import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
            ),
        },
    )
    result = run_public_pytest_contree(
        tmp_path,
        manifest,
        ["test_app.py"],
        deadline=time.monotonic() + 600,
    )
    assert result["executor"] == EXECUTOR
    assert result.get("error_type") is None, result.get("error")
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert result["timed_out"] is False
    assert "1 passed" in result["output"]
    sandbox = result.get("sandbox") or {}
    assert sandbox.get("operation_uuid")
    assert sandbox.get("instance_uuid")
    assert sandbox.get("image") == _live_contree.image


def test_live_contree_reports_a_real_test_failure_not_infra_error(
    tmp_path: Path, _live_contree
):
    manifest = _manifest(
        tmp_path,
        {"test_fail.py": "def test_fails():\n    assert False\n"},
    )
    result = run_public_pytest_contree(
        tmp_path,
        manifest,
        ["test_fail.py"],
        deadline=time.monotonic() + 600,
    )
    # A failing test is evidence, never an infrastructure error_type.
    assert result.get("error_type") is None
    assert result["ok"] is False
    assert result["exit_code"] != 0
    assert result["timed_out"] is False
