"""Review attempt fencing with fake credentials and in-memory HTTP only."""

import asyncio
import json
from contextvars import copy_context
from threading import Event
from types import SimpleNamespace

import httpx
import pytest
import strands
from pex_supervisor import ask_review, inspect_http
from pex_supervisor.ask_review import ReviewAnswer
from pex_supervisor.review_authority import (
    ReviewAuthorityUnavailable,
    require_review_authority,
    review_invocation_guard,
)
from test_supervisor_loop import _request


def install_http(monkeypatch, handler):
    # Neither configuration nor HTTP transport can consult ambient credentials
    # or reach a provider. The .invalid endpoint is only a request-shape fixture.
    monkeypatch.setattr(
        inspect_http,
        "openai_compat_client_config",
        lambda: {
            "provider": "zen",
            "base_url": "https://review.example.invalid/v1",
            "model_id": "explicit-test-model",
            "api_key": "test-only-review-key",
        },
    )
    monkeypatch.setattr(
        inspect_http,
        "credential_safe_http_client",
        lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), trust_env=False, **kwargs
        ),
    )


def successful_response():
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": '{"answer":"FAKE_REVIEW_ANSWER"}'}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        },
    )


def check_request(request):
    assert request.url == "https://review.example.invalid/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-only-review-key"
    payload = json.loads(request.content)
    assert payload["max_tokens"] == 350
    assert payload["stream"] is False
    return payload["model"]


@pytest.mark.parametrize("status", [429, 503])
def test_retry_after_revocation_never_starts_second_http_attempt(monkeypatch, status):
    calls = []
    valid = True

    def check():
        if not valid:
            raise ValueError("private authority details must not be returned")

    def respond(request):
        nonlocal valid
        calls.append(check_request(request))
        valid = False
        return httpx.Response(status, json={"error": "retryable fixture"})

    install_http(monkeypatch, respond)
    with review_invocation_guard(check), pytest.raises(ReviewAuthorityUnavailable) as error:
        inspect_http.complete_review_answer("system", "review")
    assert str(error.value) == "review authority is unavailable"
    assert calls == ["explicit-test-model"]


@pytest.mark.parametrize("status", [429, 503])
def test_current_review_can_retry_and_return_bounded_answer(monkeypatch, status):
    calls, checks = [], []

    def respond(request):
        calls.append(check_request(request))
        return (
            httpx.Response(status, json={"error": "retryable fixture"})
            if len(calls) == 1
            else successful_response()
        )

    install_http(monkeypatch, respond)
    with review_invocation_guard(lambda: checks.append(True)):
        answer, usage, kind = inspect_http.complete_review_answer("system", "review")
    assert answer == "FAKE_REVIEW_ANSWER"
    assert usage == {"input_tokens": 7, "output_tokens": 3}
    assert kind == "review_answer"
    assert len(calls) == len(checks) == 2
    assert calls[0] == "explicit-test-model" and calls[1] != calls[0]


def test_copied_context_cannot_reuse_expired_guard(monkeypatch):
    calls = []
    install_http(monkeypatch, lambda request: calls.append(request) or successful_response())
    with review_invocation_guard(lambda: None):
        inherited = copy_context()
    with pytest.raises(ReviewAuthorityUnavailable, match="ended"):
        inherited.run(inspect_http.complete_review_answer, "system", "review")
    assert calls == []


def test_nested_context_restores_outer_without_reviving_inner():
    checks = []
    with review_invocation_guard(lambda: checks.append("outer")):
        with review_invocation_guard(lambda: checks.append("inner")):
            inherited = copy_context()
            require_review_authority()
        require_review_authority()
        with pytest.raises(ReviewAuthorityUnavailable, match="ended"):
            inherited.run(require_review_authority)
    assert checks == ["inner", "outer"]


async def test_cancellation_revokes_surviving_http_thread_before_retry(monkeypatch):
    entered, release = Event(), Event()
    calls, threads = [], []

    def respond(request):
        calls.append(check_request(request))
        entered.set()
        assert release.wait(5)
        return httpx.Response(429, json={"error": "retryable fixture"})

    install_http(monkeypatch, respond)

    async def invoke():
        with review_invocation_guard(lambda: None):
            thread = asyncio.create_task(
                asyncio.to_thread(
                    inspect_http.complete_review_answer,
                    "system",
                    "review",
                )
            )
            threads.append(thread)
            return await asyncio.shield(thread)

    invocation = asyncio.create_task(invoke())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        invocation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await invocation
    finally:
        release.set()
        await asyncio.gather(invocation, return_exceptions=True)
    with pytest.raises(ReviewAuthorityUnavailable, match="ended"):
        await asyncio.wait_for(threads[0], 5)
    assert calls == ["explicit-test-model"]


@pytest.mark.parametrize("revoke_queued", [False, True])
async def test_queued_strands_entry_checks_current_review(monkeypatch, revoke_queued):
    calls, cancellations = [], []
    valid = True

    class FakeAgent:
        def __init__(self, **kwargs):
            assert kwargs["model"] is model

        async def invoke_async(self, *args, **kwargs):
            calls.append(kwargs["limits"])
            return SimpleNamespace(structured_output=ReviewAnswer(answer="FAKE_STRANDS_ANSWER"))

        def cancel(self):
            cancellations.append(True)

    def check():
        if not valid:
            raise ValueError("review revoked")

    def revoke():
        nonlocal valid
        valid = False

    original_create_task = asyncio.create_task

    def create_task(coroutine, **kwargs):
        if revoke_queued and coroutine.cr_code.co_name == "invoke":
            # This runs after construction but before the scheduled invoke body.
            asyncio.get_running_loop().call_soon(revoke)
        return original_create_task(coroutine, **kwargs)

    monkeypatch.setattr(strands, "Agent", FakeAgent)
    monkeypatch.setattr(ask_review.asyncio, "create_task", create_task)
    model = object()
    request = _request(0.1)
    with review_invocation_guard(check):
        answer = await ask_review.complete_inspect_review_async(
            "brief review",
            [request.session],
            [],
            [request.goal],
            model,
        )
    if revoke_queued:
        assert answer is None and calls == [] and cancellations == [True]
    else:
        assert answer == "FAKE_STRANDS_ANSWER" and cancellations == []
        assert calls == [{"turns": 3, "output_tokens": 800, "total_tokens": 8_000}]
