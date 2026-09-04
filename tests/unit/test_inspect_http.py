from __future__ import annotations

import json

import httpx
import pytest
from pex_supervisor.inspect_http import (
    _chat_json,
    _loads_object,
    _model_unsupported,
    _parse_response_object,
    _read_response_text,
    _skip_model,
    complete_review_answer,
    usage_tokens,
)


def test_parse_review_answer_from_json_content():
    payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({"answer": "Nothing needs you."})
                }
            }
        ],
        "usage": {"prompt_tokens": 11, "completion_tokens": 4},
    }
    parsed = _parse_response_object(payload)
    assert parsed == {"answer": "Nothing needs you."}
    assert usage_tokens(payload) == {"input_tokens": 11, "output_tokens": 4}


def test_parse_review_answer_from_wrapped_json():
    payload = {
        "choices": [
            {
                "message": {
                    "content": (
                        "Review:\n"
                        '{"answer":"The latest verified action was NOOP."}\n'
                    )
                }
            }
        ]
    }
    assert _parse_response_object(payload) == {
        "answer": "The latest verified action was NOOP."
    }


def test_review_completion_rejects_action_payload(monkeypatch):
    monkeypatch.setattr(
        "pex_supervisor.inspect_http._chat_json",
        lambda *_args, **_kwargs: (
            {"answer": "continue", "action_type": "SEND_NUDGE"},
            {},
        ),
    )

    with pytest.raises(ValueError, match="only answer"):
        complete_review_answer("system", "question")


def test_review_parser_does_not_accept_legacy_action_tool_calls():
    payload = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "propose_typed_action",
                                "arguments": '{"action_type":"SEND_NUDGE"}',
                            }
                        }
                    ]
                }
            }
        ]
    }

    with pytest.raises(ValueError, match="review content"):
        _parse_response_object(payload)


def test_unsupported_model_status_is_retryable():
    assert _model_unsupported(
        401, '{"error":{"message":"Model x-preview-f-free is not supported"}}'
    )
    assert _model_unsupported(404, '{"error":{"message":"No endpoints found"}}')
    assert not _model_unsupported(401, '{"error":{"message":"invalid api key"}}')


def test_zen_fallbacks_are_not_sent_to_openrouter():
    from pex_supervisor.inspect_http import _candidate_models

    openrouter = _candidate_models(
        {"provider": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"}
    )
    assert openrouter == ["anthropic/claude-sonnet-4.6"]
    zen = _candidate_models({"provider": "zen", "model_id": "hy3-free"})
    assert zen[0] == "hy3-free"
    assert "laguna-s-2.1-free" in zen


def test_rate_limit_skips_exhausted_free_model():
    from pex_supervisor.inspect_http import _rate_limited

    assert _rate_limited(429, "")
    assert _rate_limited(
        400, '{"error":{"type":"FreeUsageLimitError","message":"Rate limit exceeded"}}'
    )
    assert not _rate_limited(401, '{"error":{"message":"invalid api key"}}')


def test_skip_model_on_5xx_rate_limit_and_unavailable():
    assert _skip_model(503, '{"error":"Endpoint is unavailable."}')
    assert _skip_model(429, "FreeUsageLimitError")
    assert _skip_model(400, "Model is unavailable.")
    assert _model_unsupported(401, "Model x is not supported")
    assert not _skip_model(200, "{}")


@pytest.mark.parametrize(
    "payload",
    [
        {"choices": "not-a-list"},
        {"choices": ["not-an-object"]},
        {"choices": [{"message": "not-an-object"}]},
        {"choices": [{"message": {"content": 42}}]},
    ],
)
def test_review_parser_rejects_malformed_response_shapes(payload):
    with pytest.raises(ValueError):
        _parse_response_object(payload)


def test_review_parser_rejects_nonfinite_json_and_bounds_usage_counts():
    with pytest.raises(ValueError, match="non-finite"):
        _loads_object('{"answer":NaN}')
    with pytest.raises(ValueError, match="duplicate JSON key"):
        _loads_object('{"answer":"safe","answer":"overridden"}')
    assert usage_tokens(
        {
            "usage": {
                "prompt_tokens": -10,
                "completion_tokens": 10**5_000,
            }
        }
    ) == {"input_tokens": 0, "output_tokens": 1_000_000_000}
    assert usage_tokens({"usage": "invalid"}) == {
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_review_response_reader_rejects_excessive_empty_chunks():
    class EmptyChunkResponse:
        def iter_bytes(self):
            yield from [b""] * 4_097

    with pytest.raises(ValueError, match="too many chunks"):
        _read_response_text(EmptyChunkResponse())  # type: ignore[arg-type]


def test_chat_json_uses_bounded_streaming_json_response(monkeypatch):
    payload = {
        "choices": [{"message": {"content": '{"answer":"bounded"}'}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "application/json; charset=utf-8"},
            json=payload,
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "pex_supervisor.inspect_http.openai_compat_client_config",
        lambda: {
            "provider": "openrouter",
            "base_url": "https://example.invalid/v1",
            "model_id": "test-model",
            "api_key": None,
        },
    )
    monkeypatch.setattr(
        "pex_supervisor.providers.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    parsed, usage = _chat_json("system", "user")

    assert parsed == {"answer": "bounded"}
    assert usage == {"input_tokens": 3, "output_tokens": 2}


def test_chat_json_rejects_oversized_streamed_response(monkeypatch):
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            headers={"content-type": "application/json"},
            content=b"x" * 262_145,
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "pex_supervisor.inspect_http.openai_compat_client_config",
        lambda: {
            "provider": "openrouter",
            "base_url": "https://example.invalid/v1",
            "model_id": "test-model",
            "api_key": None,
        },
    )
    monkeypatch.setattr(
        "pex_supervisor.providers.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    with pytest.raises(RuntimeError, match="ValueError"):
        _chat_json("system", "user")
