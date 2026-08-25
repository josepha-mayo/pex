import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "benchmarks"))
import boundary  # noqa: E402


def test_four_arm_forbids_treatment_suffix():
    boundary.forbids_treatment_suffix(boundary.four_arm_source())


def test_supervisor_loop_has_no_task_id_branches():
    root = Path(__file__).resolve().parents[2]
    boundary.supervisor_has_no_task_id_branches(
        root / "services" / "supervisor" / "src" / "pex_supervisor" / "loop.py"
    )
    boundary.supervisor_has_no_task_id_branches(
        root / "services" / "supervisor" / "src" / "pex_supervisor" / "planner.py"
    )
    boundary.supervisor_has_no_task_id_branches(root / "benchmarks" / "pex_attach.py")


def test_pex_attach_does_not_import_hidden_evaluator():
    text = (Path(__file__).resolve().parents[2] / "benchmarks" / "pex_attach.py").read_text(
        encoding="utf-8"
    )
    assert "import evaluator" not in text
    assert "from evaluator" not in text
    assert "metadata.yaml" not in text
    assert "Handoff fact" not in text
    assert "from pex_supervisor" not in text
    assert "import pex_supervisor" not in text

    process = (
        Path(__file__).resolve().parents[2] / "benchmarks" / "pex_supervisor_process.py"
    ).read_text(encoding="utf-8")
    assert "import evaluator" not in process
    assert "from evaluator" not in process


def test_workspace_observer_skips_hidden_evaluator(tmp_path):
    from pex_supervisor.workspace import snapshot

    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "evaluator.py").write_text("SECRET = 1\n", encoding="utf-8")
    (tmp_path / "metadata.yaml").write_text("stressor: planted\n", encoding="utf-8")
    seen = snapshot(tmp_path, run_pytest=False)
    assert "ok.py" in seen["files"]
    assert "evaluator.py" not in seen["files"]
    assert "metadata.yaml" not in seen["files"]


def test_supervisor_verification_never_executes_workspace_code(tmp_path):
    from pex_supervisor.workspace import snapshot

    escaped = tmp_path.parent / "workspace_test_executed.txt"
    (tmp_path / "test_malicious.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(escaped)!r}).write_text('executed')\n",
        encoding="utf-8",
    )
    seen = snapshot(tmp_path, run_pytest=True)
    assert seen["pytest"]["skipped"] is True
    assert not escaped.exists()


def test_runtime_boundary_rejects_prompt_changes_and_oracle_messages():
    task = "pexbench_001_premature_stop"
    prompt = boundary.public_prompt(task)
    boundary.assert_public_prompt(task, prompt)
    try:
        boundary.assert_public_prompt(task, prompt + "\nrun tests")
    except AssertionError:
        pass
    else:
        raise AssertionError("mutated treatment prompt was accepted")

    try:
        boundary.assert_public_intervention("read evaluator.py")
    except AssertionError:
        pass
    else:
        raise AssertionError("private evaluator intervention was accepted")
