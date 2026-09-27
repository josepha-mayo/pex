import json

import pytest

from benchmarks import evaluator


def test_required_boundary_failure_never_runs_candidate(tmp_path, monkeypatch):
    seed = evaluator.seed_workspace("pexbench_001_premature_stop", tmp_path)

    def refuse(*args):
        raise RuntimeError("boundary unavailable")

    def forbidden(*args, **kwargs):
        pytest.fail("candidate executed after failed boundary validation")

    monkeypatch.setattr(evaluator.linux_sandbox, "_prefix", refuse)
    monkeypatch.setattr(evaluator, "_pytest", forbidden)
    monkeypatch.setattr(evaluator, "_hidden_check", forbidden)
    with pytest.raises(RuntimeError, match="boundary unavailable"):
        evaluator.evaluate("pexbench_001_premature_stop", tmp_path, seed,
                           require_linux_sandbox=True)


def test_required_evaluation_routes_both_checks_to_boundary(tmp_path, monkeypatch):
    seed = evaluator.seed_workspace("pexbench_001_premature_stop", tmp_path)
    calls = []
    monkeypatch.setattr(evaluator.linux_sandbox, "_prefix", lambda root: calls.append("preflight"))

    def check(*args, **kwargs):
        assert kwargs == {"require_linux_sandbox": True}
        calls.append("check")
        return True, "controlled test result"

    monkeypatch.setattr(evaluator, "_pytest", check)
    monkeypatch.setattr(evaluator, "_hidden_check", check)
    evaluator.evaluate("pexbench_001_premature_stop", tmp_path, seed,
                       require_linux_sandbox=True)
    assert calls == ["preflight", "check", "check"]


def test_required_commands_ignore_optional_environment_switch(tmp_path, monkeypatch):
    calls = []

    def forbidden():
        pytest.fail("explicit requirement consulted optional environment switch")

    monkeypatch.setattr(evaluator.linux_sandbox, "enabled", forbidden)
    monkeypatch.setattr(evaluator.linux_sandbox, "public_pytest_command",
                        lambda *args: ["isolated-public"])
    monkeypatch.setattr(evaluator.linux_sandbox, "hidden_command",
                        lambda *args: ["isolated-hidden"])

    def run(command, **kwargs):
        calls.append(command)
        response = json.dumps({"returned": True, "value": "expected"})
        return 0, "PEX_HIDDEN_RESULT=" + response, False, False

    monkeypatch.setattr(evaluator, "_run_bounded", run)
    assert evaluator._run_pytest(tmp_path, ["test_public.py"],
                                 require_linux_sandbox=True)[0]
    assert evaluator._hidden_check(tmp_path, {
        "module": "candidate", "function": "candidate",
        "hidden_cases": [{"args": [], "expected": "expected"}],
    }, require_linux_sandbox=True)[0]
    assert calls == [["isolated-public"], ["isolated-hidden"]]


@pytest.mark.parametrize("flag", [None, 0, 1, "linux-bwrap"])
def test_isolation_requirement_rejects_ambiguous_values(tmp_path, flag):
    with pytest.raises(ValueError, match="must be boolean"):
        evaluator.evaluate("unused", tmp_path, require_linux_sandbox=flag)
