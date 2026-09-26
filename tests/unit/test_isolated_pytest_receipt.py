import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pex_protocol.isolated_pytest import EXECUTOR, isolated_pytest_argv, isolated_pytest_display

from benchmarks.pex_supervisor_process import _controller_verification


@pytest.mark.skipif(sys.platform != "linux", reason="Linux namespace command contract")
@pytest.mark.parametrize("mutation", [None, "argv", "command", "executor", "digest"])
def test_child_binds_isolated_receipt_to_command_and_snapshot(monkeypatch, mutation):
    monkeypatch.setenv("PEX_SUPERVISOR_DISABLE", "1")
    result = {"ok": True, "exit_code": 0, "output": "1 passed"}
    observation = {
        "files": ["test_public.py"], "public_workspace_sha256": "a" * 64,
        "public_test_integrity": {"intact": True, "expected_sha256": "b" * 64,
                                  "observed_sha256": "b" * 64},
        "pytest": result,
        "controller_verification": {
            "owner": "benchmark_controller", "kind": "pytest", "executor": EXECUTOR,
            "invocation_scope": "targeted", "relative_targets": ["test_public.py"],
            "command": isolated_pytest_display(sys.executable, ["test_public.py"]),
            "result": deepcopy(result),
            "provenance": {
                "public_workspace_sha256": "a" * 64, "public_test_sha256": "b" * 64,
                "workspace_stable_during_verification": True,
                "executed_argv": isolated_pytest_argv(sys.executable, ["test_public.py"]),
            },
        },
    }
    receipt = observation["controller_verification"]
    if mutation == "argv":
        receipt["provenance"]["executed_argv"].remove("-I")
    elif mutation == "command":
        receipt["command"] = "host-python -m pytest test_public.py"
    elif mutation == "executor":
        receipt["executor"] = "host"
    elif mutation == "digest":
        receipt["provenance"]["public_workspace_sha256"] = "c" * 64
    if mutation is not None:
        with pytest.raises(ValueError):
            _controller_verification(observation, Path("/workspace"))
    else:
        accepted = _controller_verification(observation, Path("/workspace"))
        assert accepted["provenance"]["executed_argv"] == receipt["provenance"]["executed_argv"]
