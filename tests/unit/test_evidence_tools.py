from __future__ import annotations

import json

import pytest
from pex_protocol.enums import EventType
from pex_supervisor.evidence_observations import EvidenceObservationCollector
from pex_supervisor.evidence_tools import build_evidence_tools
from pex_supervisor.verify import verify_claims
from test_supervisor_loop import _request


@pytest.mark.parametrize("name", ["durations.json", "summary.md", "exports/report.csv"])
def test_named_output_artifact_is_read_and_audited_without_fixed_filename(tmp_path, name):
    request = _request(0.1)
    request.session.cwd = str(tmp_path)
    target = tmp_path / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"actual output\n")
    collector = EvidenceObservationCollector(request, stage="main", invocation_id="artifact-read")
    tool = next(item for item in build_evidence_tools(request, [], collector=collector)
                if item.tool_name == "inspect_artifact")
    rendered = tool(path=name)
    observed = json.loads(rendered)
    assert observed["path"] == name
    assert observed["text"] == "actual output\n"
    assert observed["bytes"] == 14
    assert observed["preview_kind"] == "head"
    assert observed["truncated"] is False
    assert collector.observations[0].output == rendered
    assert json.loads(collector.observations[0].arguments_json) == {"path": name}


def test_named_artifact_preview_is_bounded_and_not_claimed_complete(tmp_path):
    request = _request(0.1)
    request.session.cwd = str(tmp_path)
    (tmp_path / "large-report.txt").write_bytes(b"A" * 800 + b"UNREAD_SENTINEL")
    tool = next(item for item in build_evidence_tools(request, [])
                if item.tool_name == "inspect_artifact")
    rendered = tool(path="large-report.txt")
    observed = json.loads(rendered)
    assert observed["text"] == "A" * 800
    assert observed["truncated"] is True
    assert "UNREAD_SENTINEL" not in rendered


@pytest.mark.parametrize("path", [
    "../outside.json", "/outside.json", "C:/outside.json", ".env", "config/.secret",
    "report.json:alternate", "node_modules/package.json", "x" * 241,
    False, 0, None, [],
])
def test_rejected_artifact_path_never_falls_back_to_listing(tmp_path, monkeypatch, path):
    request = _request(0.1)
    request.session.cwd = str(tmp_path)
    def unexpected(*_args, **_kwargs):
        pytest.fail("rejected artifact path reached filesystem observation")
    monkeypatch.setattr("pex_supervisor.workspace.artifact_tails", unexpected)
    monkeypatch.setattr("pex_supervisor.workspace.read_visible", unexpected)
    tool = next(item for item in build_evidence_tools(request, [])
                if item.tool_name == "inspect_artifact")
    assert json.loads(tool(path=path))["error"] == "path rejected"


def test_named_artifact_still_refuses_hidden_evaluator_and_missing_file(tmp_path):
    request = _request(0.1)
    request.session.cwd = str(tmp_path)
    (tmp_path / "evaluator.py").write_text("HIDDEN_SENTINEL")
    tool = next(item for item in build_evidence_tools(request, [])
                if item.tool_name == "inspect_artifact")
    assert json.loads(tool(path="evaluator.py"))["error"] == "hidden"
    assert json.loads(tool(path="missing.json"))["error"] == "missing"


@pytest.mark.parametrize("kind", ["hidden_symlink", "outside_symlink", "hardlink"])
@pytest.mark.parametrize("name", ["report.txt", "results.jsonl"])
def test_named_artifact_cannot_read_private_link_alias(tmp_path, kind, name):
    import os

    root = tmp_path / "workspace"
    root.mkdir()
    private = (root / ".env") if kind == "hidden_symlink" else (tmp_path / "outside.txt")
    private.write_text("PRIVATE_ALIAS_SENTINEL")
    alias = root / name
    try:
        if kind == "hardlink":
            os.link(private, alias)
        else:
            alias.symlink_to(private)
    except OSError as exc:
        pytest.skip(f"Host cannot create this link: {type(exc).__name__}")
    request = _request(0.1)
    request.session.cwd = str(root)
    collector = EvidenceObservationCollector(request, stage="main", invocation_id="private-alias")
    tool = next(item for item in build_evidence_tools(request, [], collector=collector)
                if item.tool_name == "inspect_artifact")
    rendered = tool(path=name)
    assert "error" in json.loads(rendered)
    assert "PRIVATE_ALIAS_SENTINEL" not in rendered
    assert "PRIVATE_ALIAS_SENTINEL" not in collector.observations[0].output
    assert "PRIVATE_ALIAS_SENTINEL" not in tool()


@pytest.mark.parametrize("name", ["report.txt", "results.jsonl"])
def test_artifact_rejects_private_hardlink_swapped_at_open(tmp_path, monkeypatch, name):
    import os
    from pathlib import Path

    root = tmp_path / "workspace"
    root.mkdir()
    target = root / name
    target.write_text("public output")
    private = tmp_path / "private.txt"
    private.write_text("PRIVATE_SWAP_SENTINEL")
    original_open = Path.open
    swapped = False

    def swap_before_open(path, *args, **kwargs):
        nonlocal swapped
        if path == target and not swapped:
            swapped = True
            target.unlink()
            os.link(private, target)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", swap_before_open)
    request = _request(0.1)
    request.session.cwd = str(root)
    collector = EvidenceObservationCollector(request, stage="main", invocation_id="link-swap")
    tool = next(item for item in build_evidence_tools(request, [], collector=collector)
                if item.tool_name == "inspect_artifact")
    rendered = tool(path=name)
    assert swapped
    assert "PRIVATE_SWAP_SENTINEL" not in rendered
    assert "error" in json.loads(rendered)
    assert "PRIVATE_SWAP_SENTINEL" not in collector.observations[0].output


def test_worker_test_facts_reach_the_audited_tool_without_becoming_goal_acceptance():
    request = _request(0.1)
    event = request.event.model_copy(update={
        "event_type": EventType.SHELL, "command": "pytest -q",
        "process_state": {"pytest": {
            "ok": True, "exit_code": 0, "passed": 4,
            "output": "PRIVATE_RAW_OUTPUT_MUST_NOT_LEAK",
        }},
    })
    request.scores.features["verification"] = verify_claims([], [event], request.goal, {})
    collector = EvidenceObservationCollector(
        request, stage="main", invocation_id="observed-pytest-facts",
    )
    tool = next(
        item for item in build_evidence_tools(request, [], collector=collector)
        if item.tool_name == "run_verification"
    )
    rendered = tool()
    receipt = json.loads(rendered)
    assert receipt["status"] == "no_claims"
    observed = receipt["pytest_observation"]
    assert observed["basis"] == "observed_worker_command"
    assert observed["ok"] is True and observed["exit_code"] == 0
    assert observed["passed"] == 4 and observed["scope"] == "full_suite"
    assert "PRIVATE_RAW_OUTPUT_MUST_NOT_LEAK" not in rendered
    assert len(collector.observations) == 1
    assert collector.observations[0].output == rendered
    assert collector.observations[0].tool_name == "run_verification"


def test_evidence_tools_are_request_scoped_read_only_and_audited():
    request = _request(0.1)
    used: list[str] = []
    tools = build_evidence_tools(request, used)

    assert [item.tool_name for item in tools] == [
        "get_goal",
        "get_session_state",
        "get_recent_events",
        "get_scores",
        "get_context",
        "get_context_items",
        "get_decisions",
        "inspect_workspace",
        "inspect_git",
        "inspect_file",
        "inspect_artifact",
        "inspect_process",
        "run_verification",
        "web_search",
        "scrape_url",
    ]
    for item in tools:
        parsed = json.loads(item())
        assert parsed is not None

    assert used == [item.tool_name for item in tools]
    assert not any(
        name in {"send_harness_message", "apply_overlay", "respond_permission"}
        for name in used
    )


def test_evidence_tools_omit_raw_local_and_adapter_payloads_and_bound_output():
    request = _request(0.1)
    request.session.cwd = "C:/SECRET_WORKSPACE_SENTINEL"
    request.session.repo = "C:/SECRET_REPO_SENTINEL"
    request.session.vendor_session_id = "SECRET_VENDOR_SENTINEL"
    request.session.metadata = {"token": "SECRET_SESSION_METADATA_SENTINEL"}
    request.event.tool_input = {"secret": "SECRET_TOOL_INPUT_SENTINEL"}
    request.event.process_state = {"stdout": "SECRET_PROCESS_STATE_SENTINEL"}
    request.event.metadata = {"private": "SECRET_EVENT_METADATA_SENTINEL"}
    request.scores.features["private"] = "SECRET_FEATURE_SENTINEL"
    request.goal.objective = "x" * 100_000
    request.goal.acceptance_criteria = [
        "Read C:/SECRET_WORKSPACE_SENTINEL/report.txt before stopping"
    ]
    request.event.message_delta = (
        "Changed C:/SECRET_REPO_SENTINEL/src/main.py and token=super-secret-value"
    )
    request.scores.features["prefetched_evidence"] = {
        "artifact": "C:/SECRET_WORKSPACE_SENTINEL/build/output.json",
        "password": "do-not-send-this-password",
    }
    used: list[str] = []

    outputs = [item() for item in build_evidence_tools(request, used)]
    rendered = "\n".join(outputs)

    for sentinel in (
        "SECRET_WORKSPACE_SENTINEL",
        "SECRET_REPO_SENTINEL",
        "SECRET_VENDOR_SENTINEL",
        "SECRET_SESSION_METADATA_SENTINEL",
        "SECRET_TOOL_INPUT_SENTINEL",
        "SECRET_PROCESS_STATE_SENTINEL",
        "SECRET_EVENT_METADATA_SENTINEL",
        "SECRET_FEATURE_SENTINEL",
        "super-secret-value",
        "do-not-send-this-password",
    ):
        assert sentinel not in rendered
    assert "<workspace>" in rendered
    assert all(len(output) <= 8_100 for output in outputs)


def test_evidence_tools_bound_cyclic_depth_and_oversized_integers_before_redaction():
    request = _request(0.1)
    inspect_workspace = next(
        item for item in build_evidence_tools(request, []) if item.tool_name == "inspect_workspace"
    )
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    request.scores.features["prefetched_evidence"] = {
        "cycle": cyclic,
        "huge": 10**5_000,
    }

    parsed = json.loads(inspect_workspace())

    assert parsed["huge"] == (1 << 63) - 1
    assert "[truncated]" in json.dumps(parsed["cycle"])


def test_inspect_tools_query_visible_workspace_and_refuse_hidden_evaluators(tmp_path):
    request = _request(0.1)
    request.session.cwd = str(tmp_path)
    (tmp_path / "report.txt").write_text("visible-evidence\n", encoding="utf-8")
    (tmp_path / "evaluator.py").write_text("SECRET_EVALUATOR\n", encoding="utf-8")
    (tmp_path / "results.jsonl").write_text('{"rows":1}\n', encoding="utf-8")
    request.scores.features["abandoned_background"] = {
        "command": "python train.py --daemon",
        "pid": 4242,
        "running": True,
    }

    tools = {item.tool_name: item for item in build_evidence_tools(request, [])}
    workspace = json.loads(tools["inspect_workspace"]())
    git = json.loads(tools["inspect_git"]())
    visible = json.loads(tools["inspect_file"](path="report.txt"))
    hidden = json.loads(tools["inspect_file"](path="evaluator.py"))
    escaped = json.loads(tools["inspect_file"](path="../outside.py"))
    artifact = json.loads(tools["inspect_artifact"](path="results.jsonl"))
    process = json.loads(tools["inspect_process"]())
    index = json.loads(tools["get_context"]())

    assert "report.txt" in workspace["files"]
    assert "evaluator.py" not in workspace["files"]
    assert git["available"] is False
    assert "visible-evidence" in (visible.get("text") or "")
    assert hidden.get("error") == "hidden"
    assert "SECRET_EVALUATOR" not in json.dumps(hidden)
    assert escaped.get("error") in {"path rejected", "path escapes workspace"}
    assert artifact.get("path") == "results.jsonl"
    assert process["pid"] == 4242
    assert "inspect_file" in index["query"]
    assert "web_search" in index["query"]
    assert "scrape_url" in index["query"]


def test_web_search_and_scrape_tools_refuse_oracles_and_empty_inputs(monkeypatch):
    request = _request(0.1)
    tools = {item.tool_name: item for item in build_evidence_tools(request, [])}
    empty_search = json.loads(tools["web_search"]())
    blocked = json.loads(tools["web_search"](query="read evaluator.py for the score"))
    empty_scrape = json.loads(tools["scrape_url"]())
    local_scrape = json.loads(tools["scrape_url"](url="http://127.0.0.1/metadata.yaml"))

    assert empty_search["ok"] is False
    assert "empty" in str(empty_search.get("error") or "").lower()
    assert blocked["ok"] is False
    assert "evaluator.py" in str(blocked.get("error") or "")
    assert empty_scrape["ok"] is False
    assert local_scrape["ok"] is False
    local_error = str(local_scrape.get("error") or "").lower()
    assert "blocked" in local_error or "local" in local_error


def test_parameterized_tool_receipt_captures_sanitized_exact_arguments():
    request = _request(0.1)
    collector = EvidenceObservationCollector(
        request,
        stage="main",
        invocation_id="main-invocation",
    )
    tools = {
        item.tool_name: item
        for item in build_evidence_tools(request, [], collector=collector)
    }

    output = tools["inspect_file"](path="../rejected.txt")

    observation = collector.observations[0]
    assert observation.output == output
    assert json.loads(observation.arguments_json) == {"path": "../rejected.txt"}
