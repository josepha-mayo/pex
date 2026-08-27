from __future__ import annotations

import json

from pex_supervisor.inspect_http import _model_unsupported, _skip_model, parse_proposal_args, usage_tokens
from pex_supervisor.loop import run_strands
from pex_supervisor.tools import bind_request, record_proposal, reset_request, take_proposed

from tests.unit.test_graphs import _request


def test_parse_proposal_from_tool_call():
    payload = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "propose_typed_action",
                                "arguments": json.dumps(
                                    {
                                        "action_type": "SEND_NUDGE",
                                        "rationale": "report.txt is missing",
                                        "evidence": "workspace files=[]",
                                        "message": "Create report.txt containing shipped.",
                                    }
                                ),
                            }
                        }
                    ]
                }
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 4},
    }
    args = parse_proposal_args(payload)
    assert args["action_type"] == "SEND_NUDGE"
    assert "report.txt" in args["message"]
    assert usage_tokens(payload) == {"input_tokens": 11, "output_tokens": 4}


def test_parse_proposal_from_json_content():
    payload = {
        "choices": [
            {
                "message": {
                    "content": '{"action_type":"NOOP","rationale":"done","evidence":"report.txt exists"}'
                }
            }
        ]
    }
    assert parse_proposal_args(payload)["action_type"] == "NOOP"


def test_parse_proposal_from_wrapped_json():
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        "Here is the action:\n"
                        '{"action_type":"SEND_NUDGE","rationale":"missing","evidence":"no report.txt","message":"Create report.txt containing shipped."}\n'
                    )
                }
            }
        ]
    }
    args = parse_proposal_args(payload)
    assert args["action_type"] == "SEND_NUDGE"
    assert "report.txt" in args["message"]


def test_unsupported_model_status_is_retryable():
    assert _model_unsupported(401, '{"error":{"message":"Model x-preview-f-free is not supported"}}')
    assert not _model_unsupported(401, '{"error":{"message":"invalid api key"}}')


def test_rate_limit_skips_exhausted_free_model():
    from pex_supervisor.inspect_http import _rate_limited

    assert _rate_limited(429, "")
    assert _rate_limited(400, '{"error":{"type":"FreeUsageLimitError","message":"Rate limit exceeded"}}')
    assert not _rate_limited(401, '{"error":{"message":"invalid api key"}}')


def test_record_proposal_accepts_list_evidence():
    request = _request(0.9)
    token = bind_request(request)
    try:
        record_proposal(
            action_type="SEND_NUDGE",
            rationale="missing artifact",
            evidence=["no report.txt", "goal wants shipped"],
            message="Create report.txt containing shipped.",
        )
        proposed = take_proposed()
    finally:
        reset_request(token)
    assert proposed is not None
    assert proposed["evidence"] == ["no report.txt", "goal wants shipped"]


def test_run_strands_uses_bounded_http(monkeypatch):
    monkeypatch.setattr(
        "pex_supervisor.loop.complete_typed_action",
        lambda system, user: (
            {
                "action_type": "SEND_NUDGE",
                "rationale": "report.txt missing",
                "evidence": "workspace has no report.txt",
                "message": "Create report.txt containing shipped.",
            },
            {"input_tokens": 9, "output_tokens": 6},
            "propose_typed_action:SEND_NUDGE",
        ),
    )
    result = run_strands(_request(0.95), model=object())
    assert result.used_llm is True
    assert result.action.type.value == "SEND_NUDGE"
    assert "report.txt" in str(result.action.payload.get("text") or "")
    assert not str(result.action.payload.get("text") or "").startswith("PEX:")
    assert result.diagnosis == "strands_supervisor"


def test_skip_model_on_5xx_rate_limit_and_unavailable():
    assert _skip_model(503, '{"error":"Endpoint is unavailable."}')
    assert _skip_model(429, "FreeUsageLimitError")
    assert _skip_model(400, "Model is unavailable.")
    assert _model_unsupported(401, "Model x is not supported")
    assert not _skip_model(200, "{}")


def test_run_strands_inspect_failure_nudges_when_required_file_missing(tmp_path, monkeypatch):
    def _boom(_system, _user):
        raise RuntimeError("model laguna-s-2.1-free timed out")

    monkeypatch.setattr("pex_supervisor.loop.complete_typed_action", _boom)
    request = _request(0.95)
    request.session.cwd = str(tmp_path)
    request.goal.evidence_requirements = ["report.txt"]
    request.goal.objective = "Create report.txt containing shipped."
    result = run_strands(request, model=object())
    assert result.used_llm is False
    assert result.action.type.value == "SEND_NUDGE"
    assert "report.txt" in str(result.action.payload.get("text") or "")
    assert not str(result.action.payload.get("text") or "").startswith("PEX:")


def test_run_strands_inspect_failure_stays_noop_when_file_present(tmp_path, monkeypatch):
    def _boom(_system, _user):
        raise RuntimeError("model laguna-s-2.1-free timed out")

    monkeypatch.setattr("pex_supervisor.loop.complete_typed_action", _boom)
    request = _request(0.95)
    request.session.cwd = str(tmp_path)
    (tmp_path / "report.txt").write_text("shipped", encoding="utf-8")
    request.goal.evidence_requirements = ["report.txt"]
    result = run_strands(request, model=object())
    assert result.used_llm is False
    assert result.action.type.value == "NOOP"
