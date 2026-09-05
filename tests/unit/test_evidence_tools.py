from __future__ import annotations

import json

from pex_supervisor.evidence_tools import build_evidence_tools
from test_supervisor_loop import _request


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
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    request.scores.features["prefetched_evidence"] = {
        "cycle": cyclic,
        "huge": 10**5_000,
    }

    inspect_workspace = next(
        item for item in build_evidence_tools(request, []) if item.tool_name == "inspect_workspace"
    )
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
