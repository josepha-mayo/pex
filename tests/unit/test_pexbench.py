import importlib.util
import json
from pathlib import Path

import pytest


def _runner():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "runner.py"
    spec = importlib.util.spec_from_file_location("pexbench_runner", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_append_immutable_requires_success(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError):
        runner.append_immutable("run1", {"arm": "cursor"})


def test_presentation_arms_require_live_flag(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="live"):
        runner.append_immutable(
            "run1",
            {"arm": "codex_pex", "task": "pexbench_001_premature_stop", "success": True},
        )


def test_immutable_results_refuse_duplicate_arm_task(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    row = {
        "arm": "codex",
        "task": "pexbench_001_premature_stop",
        "success": False,
        "live": False,
        "not_a_presentation_arm": True,
    }
    runner.append_immutable("run1", row)
    with pytest.raises(ValueError, match="immutable result already exists"):
        runner.append_immutable("run1", row)


def test_synthetic_smoke_is_labeled_not_presentation(tmp_path):
    runner = _runner()
    path = tmp_path / "synthetic_smoke.jsonl"
    runner.write_synthetic_smoke(path, success=True, human_interventions=0)
    row = json.loads(path.read_text(encoding="utf-8"))
    assert row["arm"] == "synthetic_pex"
    assert row["not_a_presentation_arm"] is True
    assert row["success"] is True


def _four_arm():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "four_arm.py"
    spec = importlib.util.spec_from_file_location("pexbench_four_arm", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _evaluator():
    path = Path(__file__).resolve().parents[2] / "benchmarks" / "evaluator.py"
    spec = importlib.util.spec_from_file_location("pexbench_evaluator", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_evaluator_rejects_empty_premature_stop(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, seed)
    assert result["success"] is False


def test_evaluator_accepts_synthetic_completion(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_001_premature_stop", tmp_path)
    extra = ev.complete_synthetic("pexbench_001_premature_stop", tmp_path)
    extra.update(seed)
    result = ev.evaluate("pexbench_001_premature_stop", tmp_path, extra)
    assert result["success"] is True


def test_drift_fails_if_legacy_is_rewritten(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_002_drift", tmp_path)
    extra = ev.complete_synthetic("pexbench_002_drift", tmp_path)
    extra.update(seed)
    (tmp_path / "unrelated_legacy.py").write_text("VALUE = 0\n", encoding="utf-8")
    result = ev.evaluate("pexbench_002_drift", tmp_path, extra)
    assert result["success"] is False
    assert any("changed" in r for r in result["reasons"])


def test_handoff_scores_final_workspace_not_stuffed_prompt(tmp_path):
    ev = _evaluator()
    seed = ev.seed_workspace("pexbench_005_handoff", tmp_path)
    result = ev.evaluate("pexbench_005_handoff", tmp_path, seed)
    assert result["success"] is False
    extra = ev.complete_synthetic("pexbench_005_handoff", tmp_path)
    extra.update(seed)
    passed = ev.evaluate("pexbench_005_handoff", tmp_path, extra)
    assert passed["success"] is True


def test_freeze_refuses_without_live_presentation_rows(tmp_path, monkeypatch):
    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)
    blockers = four.freeze_blockers()
    assert blockers
    assert any("cursor/" in b for b in blockers)
    assert any("codex/" in b for b in blockers)
    result = four.try_freeze()
    assert result["frozen"] is False
    assert result["wrote"] is False


async def test_cursor_live_arm_never_spawns_a_window():
    four = _four_arm()
    with pytest.raises(RuntimeError, match="do not spawn another Cursor"):
        await four.run_live("cursor", "pexbench_001_premature_stop", "nope")
    with pytest.raises(RuntimeError, match="do not spawn another Cursor"):
        await four.run_live("cursor_pex", "pexbench_001_premature_stop", "nope")


async def test_cursor_stop_payload_wrong_cwd_still_refuses_spawn(tmp_path, monkeypatch):
    four = _four_arm()
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    with pytest.raises(RuntimeError, match="do not spawn another Cursor"):
        await four.run_live(
            "cursor",
            "pexbench_001_premature_stop",
            "wrong_cwd",
            workspace_root=tmp_path / "ws",
            stop_payload={"cwd": str(tmp_path / "somewhere-else"), "completion": "done"},
        )


async def test_cursor_matching_stop_payload_writes_hooks_row(tmp_path, monkeypatch):
    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    workspace_root = tmp_path / "ws"
    expected = four.isolated_workspace(
        "this_cursor", "cursor", "pexbench_001_premature_stop", workspace_root
    )
    result = await four.run_live(
        "cursor",
        "pexbench_001_premature_stop",
        "this_cursor",
        workspace_root=workspace_root,
        stop_payload={"cwd": str(expected), "completion": "I am done."},
    )
    assert result["transport_kind"] == "cursor_hooks"
    assert result["live"] is True
    assert result["not_a_presentation_arm"] is False
    assert result["pex"] is None
    assert result["success"] is False
    row = json.loads((tmp_path / "results" / "this_cursor.jsonl").read_text(encoding="utf-8"))
    assert row["transport_evidence"]["hooks_path"] == str(hooks)
    assert row["agent_messages"] == ["I am done."]


async def test_cursor_record_does_not_clobber_worker_files(tmp_path, monkeypatch):
    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    workspace_root = tmp_path / "ws"
    expected = four.isolated_workspace(
        "no_clobber", "cursor", "pexbench_003_permission_spam", workspace_root
    )
    four.evaluator.seed_workspace("pexbench_003_permission_spam", expected)
    (expected / "math_utils.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    result = await four.run_live(
        "cursor",
        "pexbench_003_permission_spam",
        "no_clobber",
        workspace_root=workspace_root,
        stop_payload={"cwd": str(expected), "completion": "pytest passed"},
    )
    assert "return a + b" in (expected / "math_utils.py").read_text(encoding="utf-8")
    assert result["success"] is True
    assert result["live"] is True


async def test_cursor_wait_reads_matching_stop_drop(tmp_path, monkeypatch):
    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path / "results")
    hooks = tmp_path / "hooks.json"
    hooks.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(four, "cursor_hooks_path", lambda: hooks)
    drop = tmp_path / "stops"
    drop.mkdir()
    monkeypatch.setattr(four, "cursor_stop_drop_dir", lambda: drop)
    monkeypatch.setattr(
        "pex_bridge.adapters.desktop.running_image_names",
        lambda: {"Cursor.exe"},
    )
    workspace_root = tmp_path / "ws"
    expected = four.isolated_workspace(
        "wait_drop", "cursor", "pexbench_001_premature_stop", workspace_root
    )
    (drop / "stop.json").write_text(
        json.dumps(
            {
                "cwd": str(expected),
                "completion": "stopped from drop",
                "hook_event_name": "stop",
            }
        ),
        encoding="utf-8",
    )
    result = await four.run_live(
        "cursor",
        "pexbench_001_premature_stop",
        "wait_drop",
        workspace_root=workspace_root,
        wait_cursor_stop=True,
        turn_timeout=2,
    )
    assert result["transport_kind"] == "cursor_hooks"
    assert result["agent_messages"] == ["stopped from drop"]
    assert result["live"] is True


def test_runner_rejects_spoofed_cursor_live_transport(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="hooks.json"):
        runner.append_immutable(
            "spoof_cursor",
            {
                "arm": "cursor",
                "task": "task",
                "success": True,
                "live": True,
                "pair_id": "pair",
                "prompt_sha256": "p",
                "seed_manifest_sha256": "s",
                "worker_config_sha256": "w",
                "worker_model": "model",
                "harness_identity_sha256": "h",
                "transport_kind": "test_double",
                "transport_evidence": {},
            },
        )


async def test_codex_isolated_thread_is_not_an_existing_id():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport, IsolatedThreadError

    adapter = CodexAdapter(CodexAppServerTransport())
    session = await adapter.start_isolated_thread("C:/tmp/pexbench")
    assert session.vendor_session_id != "thr_demo"
    assert session.metadata["isolated"] is True
    assert Path(session.cwd).resolve() == Path("C:/tmp/pexbench").resolve()

    class Reuse(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "thread/start":
                return {"thread": {"id": "thr_demo", "cwd": (params or {}).get("cwd")}}
            return await super().request(method, params)

    with pytest.raises(IsolatedThreadError, match="already existed"):
        await CodexAdapter(Reuse()).start_isolated_thread("C:/tmp/pexbench")


def test_codex_isolated_approval_never_allows_outside_workspace(tmp_path):
    from pex_bridge.adapters.codex import CodexAdapter
    from pex_protocol.enums import HarnessType
    from pex_protocol.session import HarnessSession

    session = HarnessSession(
        id="codex:test",
        harness_type=HarnessType.CODEX,
        vendor_session_id="test",
        cwd=str(tmp_path),
    )
    inside = {
        "method": "item/commandExecution/requestApproval",
        "params": {"cwd": str(tmp_path), "command": "pytest -q"},
    }
    outside = {
        "method": "item/permissions/requestApproval",
        "params": {"permissions": {"writableRoots": [str(tmp_path.parent)]}},
    }
    assert CodexAdapter._isolated_approval_decision(session, inside) == "allow"
    assert CodexAdapter._isolated_approval_decision(session, outside) == "deny"
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {"method": "item/commandExecution/requestApproval", "params": {"command": "pytest"}},
        )
        == "deny"
    )
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {
                "method": "item/fileChange/requestApproval",
                "params": {"changes": [{"path": str(tmp_path.parent / "secret.py")}]},
            },
        )
        == "deny"
    )
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {
                "method": "item/commandExecution/requestApproval",
                "params": {"cwd": "rel", "threadId": "other"},
            },
        )
        == "deny"
    )
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {
                "method": "item/commandExecution/requestApproval",
                "params": {"cwd": "inside_rel", "command": "pytest -q"},
            },
        )
        == "allow"
    )
    assert (
        CodexAdapter._isolated_approval_decision(
            session,
            {
                "method": "item/fileChange/requestApproval",
                "params": {"changes": [{"path": "local.py"}]},
            },
        )
        == "allow"
    )


async def test_codex_isolated_thread_refuses_cwd_mismatch():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport, IsolatedThreadError

    class WrongCwd(CodexAppServerTransport):
        async def request(self, method, params=None):
            if method == "thread/start":
                return {"thread": {"id": "thr_mismatch", "cwd": "C:/not/the/workspace"}}
            return await super().request(method, params)

    with pytest.raises(IsolatedThreadError, match="does not match"):
        await CodexAdapter(WrongCwd()).start_isolated_thread("C:/tmp/pexbench")


async def test_codex_isolated_thread_never_calls_resume():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport

    class Spy(CodexAppServerTransport):
        def __init__(self) -> None:
            super().__init__()
            self.methods: list[str] = []

        async def request(self, method, params=None):
            self.methods.append(method)
            return await super().request(method, params)

    transport = Spy()
    await CodexAdapter(transport).start_isolated_thread("C:/tmp/pexbench")
    assert "thread/start" in transport.methods
    assert "thread/resume" not in transport.methods


async def test_wait_for_turn_collects_item_notifications_not_empty_items():
    from pex_bridge.adapters.codex import CodexAdapter, CodexAppServerTransport

    class ItemsOnWire(CodexAppServerTransport):
        async def request(self, method, params=None):
            result = await super().request(method, params)
            if method == "turn/start":
                self.notifications.insert(
                    0,
                    {
                        "method": "item/completed",
                        "params": {
                            "threadId": (params or {}).get("threadId"),
                            "item": {"type": "agentMessage", "text": "should I run pytest?"},
                        },
                    },
                )
            return result

    adapter = CodexAdapter(ItemsOnWire())
    session = await adapter.start_isolated_thread("C:/tmp/pexbench")
    started = await adapter.start_turn(session, "do the task")
    turn = await adapter.wait_for_turn_completion(session, started["turn"]["id"])
    assert turn.get("items") == []
    assert adapter.isolated_agent_messages == ["should I run pytest?"]


async def test_paired_arms_share_prompt_hash_and_refuse_handoff_stuffing(tmp_path, monkeypatch):
    from pex_bridge.adapters.codex import CodexAppServerTransport

    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)

    baseline = await four.run_live(
        "codex",
        "pexbench_005_handoff",
        "handoff_baseline",
        transport=CodexAppServerTransport(),
        workspace_root=tmp_path / "ws-base",
    )
    treatment = await four.run_live(
        "codex_pex",
        "pexbench_005_handoff",
        "handoff_treatment",
        transport=CodexAppServerTransport(),
        workspace_root=tmp_path / "ws-treat",
    )
    assert baseline["prompt_sha256"] == treatment["prompt_sha256"]
    assert baseline["seed_manifest_sha256"] == treatment["seed_manifest_sha256"]
    assert baseline["worker_config_sha256"] == treatment["worker_config_sha256"]
    assert baseline["harness_identity_sha256"] == treatment["harness_identity_sha256"]
    assert baseline["pex"] is None
    assert treatment["pex"] is not None
    assert "audits" in treatment["pex"]
    sent = treatment.get("agent_messages")
    assert sent is not None
    joined = " ".join(str(x) for x in (baseline.get("agent_messages") or []))
    assert "schema.json is the source of truth" not in joined
    for message in treatment["pex"]["outgoing_messages"]:
        four.boundary.assert_public_intervention(message)


def test_isolated_workspace_is_opaque(tmp_path):
    four = _four_arm()
    path = four.isolated_workspace("run", "codex", "pexbench_001_premature_stop", tmp_path)
    assert path.is_dir()
    assert path.is_absolute()
    assert "premature_stop" not in str(path)
    assert path.name.startswith("ws_")


async def test_codex_test_double_is_never_labeled_live(tmp_path, monkeypatch):
    from pex_bridge.adapters.codex import CodexAppServerTransport

    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)
    result = await four.run_live(
        "codex",
        "pexbench_001_premature_stop",
        "iso_codex",
        transport=CodexAppServerTransport(),
        workspace_root=tmp_path / "ws",
    )
    assert result["live"] is False
    assert result["not_a_presentation_arm"] is True
    assert result["transport_kind"] == "test_double"
    assert result["isolated"] is True
    assert result["thread_id"] != "thr_demo"
    assert result["success"] is False
    assert result["pex"] is None
    row = json.loads((tmp_path / "iso_codex.jsonl").read_text(encoding="utf-8"))
    assert row["live"] is False
    assert row["arm"] == "codex"
    blockers = four.freeze_blockers()
    assert any("cursor/" in b for b in blockers)
    assert any("codex_pex/" in b for b in blockers)


async def test_treatment_arm_attaches_supervisor_without_better_prompt(tmp_path, monkeypatch):
    from pex_bridge.adapters.codex import CodexAppServerTransport

    four = _four_arm()
    monkeypatch.setattr(four.runner, "RESULTS", tmp_path)
    result = await four.run_live(
        "codex_pex",
        "pexbench_001_premature_stop",
        "iso_pex",
        transport=CodexAppServerTransport(),
        workspace_root=tmp_path / "ws",
    )
    assert result["live"] is False
    assert result["not_a_presentation_arm"] is True
    assert result["pex"] is not None
    assert result["pex"]["audits"]
    assert result["pex"]["supervisor_process_isolated"] is True
    prompt = (Path(result["cwd"]) / "TASK.md").read_text(encoding="utf-8")
    assert "Do not stop until pytest passes" not in prompt
    assert "Handoff fact:" not in prompt


def test_runner_rejects_spoofed_live_transport(tmp_path, monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner, "RESULTS", tmp_path)
    with pytest.raises(ValueError, match="codex stdio"):
        runner.append_immutable(
            "spoof",
            {
                "arm": "codex",
                "task": "task",
                "success": True,
                "live": True,
                "pair_id": "pair",
                "prompt_sha256": "p",
                "seed_manifest_sha256": "s",
                "worker_config_sha256": "w",
                "worker_model": "model",
                "harness_identity_sha256": "h",
                "transport_kind": "test_double",
                "transport_evidence": {"pid": None},
            },
        )
