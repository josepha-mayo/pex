"""Authored offline protocol loops; no benchmark tasks/oracles or provider calls."""

import asyncio
import hashlib
import json
from contextlib import aclosing

import httpx
import pytest
from test_managed_chat import ENDPOINT, MODEL, SYNTHETIC_KEY, VALID, response
from test_managed_chat import no_network as no_network
from test_managed_chat import rig as rig
from test_tool_protocol import InterventionType, ProposedAction, final_arguments, request_fixture
from test_tool_transport import payload

import managed_chat as mc
import strands_bridge as sb


class OfflineFixtureModel(sb.ManagedPEXModel):
    """Local authored harness only; production Model.stream stays deny-all."""

    async def invoke_async(self):
        return await self._invoke_owned_agent()

    async def stream(self, *args, **kwargs):
        credential = mc._ScopedCredential(SYNTHETIC_KEY, self._candidate.route.fingerprint)
        async with aclosing(self._stream_owned(*args, credential=credential, **kwargs)) as stream:
            async for event in stream:
                yield event


def model(role="planner", cls=OfflineFixtureModel):
    request = request_fixture(with_boundaries=True)
    proposal = (
        ProposedAction(
            type=InterventionType.NOOP,
            session_id=request.session.id,
            goal_id=request.goal.id,
            rationale="Synthetic proposal",
        )
        if role == "verifier"
        else None
    )
    return cls(
        mc.Route(ENDPOINT, MODEL, role),
        request,
        invocation_id="fixture-bridge-" + role,
        proposal=proposal,
    )


def kwargs(m):
    return {
        "messages": [{"role": "user", "content": [{"text": m.protocol.initial_prompt}]}],
        "tool_specs": [json.loads(d.advertised_spec_json) for d in m.protocol.definitions],
        "system_prompt": m.protocol.system_prompt,
        "system_prompt_content": [{"text": m.protocol.system_prompt}],
        "invocation_state": {},
        "model_state": {},
    }


async def collect(stream):
    return [event async for event in stream]


def tool_result(call_id, text='{"synthetic":true}'):
    return {"toolResult": {"toolUseId": call_id, "status": "success", "content": [{"text": text}]}}


def assistant_call(call_id="call_fixture", name="get_goal", inputs=None):
    return {
        "role": "assistant",
        "content": [{"toolUse": {"toolUseId": call_id, "name": name, "input": inputs or {}}}],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["stream", "structured_output", "invoke_async"])
async def test_public_model_entries_deny_before_any_transport(rig, entry):
    m = model(cls=sb.ManagedPEXModel)
    with pytest.raises(mc.Refusal, match="live_not_authorized"):
        if entry == "invoke_async":
            await m.invoke_async()
        else:
            await collect(getattr(m, entry)(**kwargs(m)))
    assert m.receipts == () and rig.created == len(rig.calls) == rig.resolutions == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["planner", "verifier"])
async def test_actual_strands_agent_typed_final_output_and_usage(rig, role):
    m = model(role)
    rig.handler = lambda request: response(
        payload(m.protocol.final_name, json.dumps(final_arguments(role)))
    )
    agent = m._make_agent()
    assert agent._retry_strategy._max_attempts == 1
    assert type(agent.conversation_manager) is sb.NullConversationManager
    result = await m.invoke_async()
    assert result.structured_output.model_dump(mode="json").items() >= final_arguments(role).items()
    assert len(m.receipts) == len(rig.calls) == 1
    assert m.receipts[0].usage == mc.Usage(
        12, 3, 15, (("cached_tokens", 2),), (("reasoning_tokens", 1),)
    )
    assert m.observations == () and m.used_tools == ()
    with pytest.raises(mc.Refusal, match="terminal"):
        await collect(m.stream(**kwargs(m)))
    assert len(rig.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["planner", "verifier"])
@pytest.mark.parametrize("blank_preamble", [False, True])
async def test_actual_pex_evidence_roundtrip_preserves_observation_bytes(rig, role, blank_preamble):
    m = model(role)

    def handle(request):
        wire = json.loads(request.content)
        if len(rig.calls) == 1:
            data = payload("get_goal", '{"boundary_page": 0}')
            if blank_preamble:
                data["choices"][0]["message"]["content"] = " \n\t "
            return response(data)
        evidence = wire["messages"][-1]["content"]
        observation = m.observations[0]
        assert evidence.encode() == observation.output.encode()
        assert hashlib.sha256(evidence.encode()).hexdigest() == observation.output_sha256
        result = final_arguments(role)
        result["evidence_refs"] = [json.loads(evidence)["pex_observation_id"]]
        return response(payload(m.protocol.final_name, json.dumps(result), "final_call"))

    rig.handler = handle
    result = await m.invoke_async()
    assert result.structured_output.evidence_refs == [m.observations[0].observation_id]
    assert m.used_tools == ("get_goal",) and len(rig.calls) == len(m.receipts) == 2
    assert sum(r.usage.total_tokens for r in m.receipts) == 30


@pytest.mark.asyncio
async def test_actual_parallel_evidence_tools_and_sequential_noninterleaved_events(rig):
    m = model()
    first = payload("get_goal", '{"boundary_page":0}', "goal_call")
    first["choices"][0]["message"]["tool_calls"].append(
        payload("inspect_acceptance", "{}", "acceptance_call")["choices"][0]["message"][
            "tool_calls"
        ][0]
    )

    def handle(request):
        if len(rig.calls) == 1:
            return response(first)
        wire = json.loads(request.content)
        tool_messages = [msg for msg in wire["messages"] if msg["role"] == "tool"]
        assert {msg["tool_call_id"] for msg in tool_messages} == {"goal_call", "acceptance_call"}
        assert {msg["content"] for msg in tool_messages} == {obs.output for obs in m.observations}
        return response(
            payload(m.protocol.final_name, json.dumps(final_arguments("planner")), "final_call")
        )

    rig.handler = handle
    result = await m.invoke_async()
    assert result.structured_output.action_type == InterventionType.NOOP
    assert set(m.used_tools) == {"get_goal", "inspect_acceptance"}
    assert len(m.observations) == 2 and len(rig.calls) == 2


@pytest.mark.asyncio
async def test_actual_strands_forced_final_extra_call_is_counted(rig):
    m = model()

    def handle(request):
        if len(rig.calls) == 1:
            return response(VALID)
        wire = json.loads(request.content)
        assert wire["messages"][-1] == {"role": "user", "content": m.protocol.forced_final_prompt}
        assert wire["tool_choice"] == "required"
        assert [tool["function"]["name"] for tool in wire["tools"]] == [m.protocol.final_name]
        return response(
            payload(m.protocol.final_name, json.dumps(final_arguments("planner")), "final_call")
        )

    rig.handler = handle
    assert (await m.invoke_async()).structured_output.action_type == InterventionType.NOOP
    assert len(m.receipts) == len(rig.calls) == m._rounds == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["401", "429", "500", "timeout", "bad_usage", "bad_arguments"])
async def test_actual_strands_errors_have_one_dispatch_no_tool_execution_no_retry(rig, failure):
    m = model()

    def handle(request):
        if failure.isdigit():
            return response(status=int(failure))
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic")
        data = payload(
            "get_goal", '{"boundary_page":false}' if failure == "bad_arguments" else "{}"
        )
        if failure == "bad_usage":
            data["usage"]["prompt_tokens"] = True
        return response(data)

    rig.handler = handle
    with pytest.raises(mc.Refusal, match="managed_transport_not_validated"):
        await m.invoke_async()
    assert len(m.receipts) == len(rig.calls) == 1
    assert m.receipts[0].outcome == "uncertain"
    assert m.observations == () and m.used_tools == ()
    with pytest.raises(mc.Refusal, match="terminal"):
        await collect(m.stream(**kwargs(m)))
    assert len(rig.calls) == 1


@pytest.mark.asyncio
async def test_receipt_completed_before_first_buffered_event_and_kept_on_close(rig):
    m = model()
    rig.handler = lambda request: response(payload("get_goal", "{}"))
    stream = m.stream(**kwargs(m))
    assert rig.calls == [] and m.receipts == ()
    assert await anext(stream) == {"messageStart": {"role": "assistant"}}
    assert m.receipts[0].outcome == "succeeded" and m.receipts[0].usage is not None
    await stream.aclose()
    with pytest.raises(mc.Refusal, match="terminal"):
        await collect(m.stream(**kwargs(m)))
    assert len(rig.calls) == 1 and m.observations == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["prompt", "system_content", "spec", "model_state", "extra", "initial_history"]
)
async def test_unowned_configuration_refuses_without_dispatch_and_is_terminal(rig, mutation):
    m = model()
    inputs = kwargs(m)
    if mutation == "prompt":
        inputs["system_prompt"] += " changed"
    if mutation == "system_content":
        inputs["system_prompt_content"].append({"cachePoint": {}})
    if mutation == "spec":
        inputs["tool_specs"][0]["description"] += " changed"
    if mutation == "model_state":
        inputs["model_state"] = {"previous_response_id": "forbidden"}
    if mutation == "extra":
        inputs["extra_body"] = {"model": "alias"}
    if mutation == "initial_history":
        inputs["messages"].append(assistant_call())
    with pytest.raises(mc.Refusal):
        await collect(m.stream(**inputs))
    with pytest.raises(mc.Refusal, match="terminal"):
        await collect(m.stream(**kwargs(m)))
    assert rig.created == rig.resolutions == len(rig.calls) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "replace_prompt",
        "replace_args",
        "replace_id",
        "missing_result",
        "orphan_result",
        "injected_assistant",
    ],
)
async def test_committed_history_and_result_correlations_are_owned(rig, mutation):
    m = model()
    rig.handler = lambda request: response(payload("get_goal", '{"boundary_page":0}'))
    inputs = kwargs(m)
    await collect(m.stream(**inputs))
    inputs["messages"] += [
        assistant_call(inputs={"boundary_page": 0}),
        {"role": "user", "content": [tool_result("call_fixture")]},
    ]
    if mutation == "replace_prompt":
        inputs["messages"][0]["content"][0]["text"] += " changed"
    if mutation == "replace_args":
        inputs["messages"][1]["content"][0]["toolUse"]["input"] = {"boundary_page": 1}
    if mutation == "replace_id":
        inputs["messages"][1]["content"][0]["toolUse"]["toolUseId"] = "replacement"
    if mutation == "missing_result":
        inputs["messages"].pop()
    if mutation == "orphan_result":
        inputs["messages"][-1]["content"][0]["toolResult"]["toolUseId"] = "orphan"
    if mutation == "injected_assistant":
        inputs["messages"].append({"role": "assistant", "content": [{"text": "injected"}]})
    with pytest.raises(mc.Refusal):
        await collect(m.stream(**inputs))
    assert len(rig.calls) == len(m.receipts) == 1


@pytest.mark.asyncio
async def test_three_call_cap_counts_plain_third_reply_then_denies_forced_fourth(rig):
    m = model()
    inputs = kwargs(m)
    for round_number in range(3):
        call_id = f"round_{round_number}"
        rig.handler = lambda request, call_id=call_id: response(
            payload("get_goal", "{}", call_id) if len(rig.calls) < 3 else VALID
        )
        await collect(m.stream(**inputs))
        if round_number < 2:
            inputs["messages"] += [
                assistant_call(call_id),
                {"role": "user", "content": [tool_result(call_id)]},
            ]
    inputs["messages"] += [
        {"role": "assistant", "content": [{"text": VALID["choices"][0]["message"]["content"]}]},
        {"role": "user", "content": [{"text": m.protocol.forced_final_prompt}]},
    ]
    inputs["tool_specs"] = [
        json.loads(m.protocol.definition(m.protocol.final_name).advertised_spec_json)
    ]
    inputs["tool_choice"] = {"any": {}}
    with pytest.raises(mc.Refusal, match="round_budget_exhausted"):
        await collect(m.stream(**inputs))
    assert len(rig.calls) == len(m.receipts) == m._rounds == 3


@pytest.mark.asyncio
async def test_cancellation_retains_uncertain_receipt_and_terminal_state(rig):
    m = model()
    started = asyncio.Event()

    async def handle(request):
        started.set()
        await asyncio.Event().wait()

    rig.handler = handle
    task = asyncio.create_task(collect(m.stream(**kwargs(m))))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(rig.calls) == len(m.receipts) == 1
    assert m.receipts[0].outcome == "uncertain" and m.receipts[0].reason == "cancelled"
    with pytest.raises(mc.Refusal, match="terminal"):
        await collect(m.stream(**kwargs(m)))


@pytest.mark.parametrize(
    "block",
    [
        {"image": {}},
        {"document": {}},
        {"cachePoint": {}},
        {"reasoningContent": {}},
        {"text": "text", "toolUse": {}},
        {"toolUse": {"name": "get_goal", "toolUseId": "id", "input": "{}"}},
    ],
)
def test_unsupported_multimodal_or_malformed_blocks_refuse(block):
    with pytest.raises(mc.Refusal):
        sb._decode_messages([{"role": "assistant", "content": [block]}])


def test_configuration_cannot_accept_external_registry_or_client():
    m = model()
    with pytest.raises(mc.Refusal):
        m.update_config(model_id="alias")
    with pytest.raises(TypeError):
        sb.ManagedPEXModel(
            mc.Route(ENDPOINT, MODEL, "planner"),
            request_fixture(),
            invocation_id="fixture",
            tools=[],
        )
    config = m.get_config()
    config["model_id"] = "alias"
    assert m.get_config()["model_id"] == MODEL


@pytest.mark.asyncio
async def test_public_denial_cannot_construct_agent_trace_or_execute_injected_tool(
    rig, monkeypatch
):
    m = model(cls=sb.ManagedPEXModel)
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append("forbidden_agent_or_trace")
        raise AssertionError("public denial must precede framework activity")

    monkeypatch.setattr(sb, "Agent", forbidden)
    monkeypatch.setattr("strands.telemetry.tracer.get_tracer", forbidden)
    assert not hasattr(m, "make_agent")
    with pytest.raises(mc.Refusal, match="live_not_authorized"):
        await m.invoke_async()
    with pytest.raises(TypeError):
        await m.invoke_async([assistant_call()])
    with pytest.raises(mc.Refusal, match="live_not_authorized"):
        await collect(m.stream(messages=[assistant_call()]))
    assert attempts == [] and m.used_tools == () and m.observations == ()
    assert m.receipts == () and rig.calls == []


def test_exact_normalized_sdk_presentation_maps_to_unchanged_authoritative_schema():
    m = model()
    original = [json.loads(d.advertised_spec_json) for d in m.protocol.definitions]
    normalized = [json.loads(raw) for _, raw in m._normalized_specs]
    assert original != normalized
    assert m._translate_specs(normalized) == original
    normalized[0]["inputSchema"]["json"]["properties"]["boundary_page"]["type"] = "string"
    with pytest.raises(mc.Refusal, match="changed_after_binding"):
        m._translate_specs(normalized)
    assert m.protocol.definition("get_goal").wire_spec()["function"]["parameters"]["properties"][
        "boundary_page"
    ]["anyOf"] == [{"type": "integer"}, {"type": "null"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_key",
        "wrong_agent",
        "request_state",
        "wrong_model",
        "wrong_messages",
        "wrong_parent",
    ],
)
async def test_actual_runtime_metadata_overrides_are_refused(rig, mutation):
    class CorruptRuntime(OfflineFixtureModel):
        async def stream(self, *args, **kw):
            state = kw["invocation_state"]
            if mutation == "unknown_key":
                state["extra_body"] = {"model": "alias"}
            if mutation == "wrong_agent":
                state["agent"] = object()
            if mutation == "request_state":
                state["request_state"]["arbitrary"] = True
            if len(rig.calls) == 1:
                if mutation == "wrong_model":
                    state["model"] = object()
                if mutation == "wrong_messages":
                    state["messages"] = []
                if mutation == "wrong_parent":
                    state["event_loop_parent_cycle_id"] = None
            async for event in super().stream(*args, **kw):
                yield event

    m = model(cls=CorruptRuntime)
    rig.handler = lambda request: response(payload("get_goal", "{}"))
    from strands.types.exceptions import EventLoopException

    with pytest.raises((mc.Refusal, EventLoopException), match="unowned_strands_runtime_state"):
        await m.invoke_async()
    assert len(rig.calls) == (
        1 if mutation in {"wrong_model", "wrong_messages", "wrong_parent"} else 0
    )
    assert all(receipt.attempts == 1 for receipt in m.receipts)


@pytest.mark.asyncio
async def test_owned_agent_invocation_has_no_repeat_or_caller_prompt_api(rig):
    m = model()
    rig.handler = lambda request: response(
        payload(m.protocol.final_name, json.dumps(final_arguments("planner")))
    )
    await m.invoke_async()
    with pytest.raises(mc.Refusal, match="invocation_reuse_refused"):
        await m.invoke_async()
    with pytest.raises(TypeError):
        await m._invoke_owned_agent([assistant_call()])
    assert len(rig.calls) == 1


@pytest.mark.asyncio
async def test_actual_null_context_manager_never_retries_overflow(rig):
    from strands.types.exceptions import ContextWindowOverflowException

    attempts = []

    class OverflowFixture(OfflineFixtureModel):
        async def stream(self, *args, **kw):
            attempts.append("model_attempt")
            raise ContextWindowOverflowException("synthetic overflow")
            yield

    m = model(cls=OverflowFixture)
    with pytest.raises(ContextWindowOverflowException):
        await m.invoke_async()
    assert attempts == ["model_attempt"] and rig.calls == [] and m.receipts == ()


@pytest.mark.asyncio
async def test_pending_parallel_result_reorder_preserves_exact_text(rig):
    m = model()
    first = payload("get_goal", "{}", "first_id")
    first["choices"][0]["message"]["tool_calls"].append(
        payload("inspect_acceptance", "{}", "second_id")["choices"][0]["message"]["tool_calls"][0]
    )
    rig.handler = lambda request: response(first)
    inputs = kwargs(m)
    await collect(m.stream(**inputs))
    inputs["messages"] += [
        {
            "role": "assistant",
            "content": assistant_call("first_id")["content"]
            + assistant_call("second_id", "inspect_acceptance")["content"],
        },
        {
            "role": "user",
            "content": [
                tool_result("second_id", '{ "synthetic": "é", "order": 2 }'),
                tool_result("first_id", '{ "synthetic": true, "order": 1 }'),
            ],
        },
    ]
    rig.handler = lambda request: response(
        payload(m.protocol.final_name, json.dumps(final_arguments("planner")), "final_id")
    )
    await collect(m.stream(**inputs))
    messages = json.loads(rig.calls[-1].content)["messages"]
    assert messages[-2:] == [
        {
            "role": "tool",
            "tool_call_id": "second_id",
            "content": '{ "synthetic": "é", "order": 2 }',
        },
        {
            "role": "tool",
            "tool_call_id": "first_id",
            "content": '{ "synthetic": true, "order": 1 }',
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["planner", "verifier"])
@pytest.mark.parametrize(
    "sequence", ["tools_plain_final", "tools_tools_final", "tools_tools_plain"]
)
async def test_actual_three_round_lifecycle_sequences_never_dispatch_a_fourth(rig, role, sequence):
    m = model(role)
    kinds = sequence.split("_")

    def handle(request):
        round_number = len(rig.calls)
        assert round_number <= 3
        kind = kinds[round_number - 1]
        if kind == "plain":
            return response(VALID)
        if kind == "tools":
            return response(payload("get_goal", "{}", f"evidence_{round_number}"))
        return response(
            payload(m.protocol.final_name, json.dumps(final_arguments(role)), "final_id")
        )

    rig.handler = handle
    if kinds[-1] == "plain":
        with pytest.raises(mc.Refusal, match="structured_output_missing"):
            await m.invoke_async()
    else:
        result = await m.invoke_async()
        assert type(result.structured_output) is m._bound.output_type
    assert len(rig.calls) == len(m.receipts) == m._rounds == 3
    with pytest.raises(mc.Refusal, match="reuse_refused"):
        await m.invoke_async()
    assert len(rig.calls) == 3


def test_isolated_in_memory_telemetry_exporter_sees_zero_public_denial_spans():
    import os
    import subprocess
    import sys
    from pathlib import Path

    # Fresh process owns its in-memory exporter, avoiding any global tracing
    # modification in the test runner or future multi-threaded application.
    script = r"""
import asyncio, socket
attempts = []
def denied(*args, **kwargs):
    attempts.append(True)
    raise AssertionError("no network authorized")
socket.getaddrinfo = denied
socket.socket.connect = denied
socket.socket.connect_ex = denied
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
provider = TracerProvider()
exporter = InMemorySpanExporter()
provider.add_span_processor(SimpleSpanProcessor(exporter))
trace.set_tracer_provider(provider)
from test_strands_bridge import model, collect, kwargs
from strands_bridge import ManagedPEXModel
from managed_chat import Refusal
async def check():
    m = model(cls=ManagedPEXModel)
    for name in ("invoke_async", "stream", "structured_output"):
        try:
            if name == "invoke_async":
                await m.invoke_async()
            else:
                await collect(getattr(m, name)(**kwargs(m)))
        except Refusal as error:
            assert str(error) == "live_not_authorized"
        else:
            raise AssertionError("public entry did not deny")
    assert not hasattr(m, "make_agent")
    assert m.receipts == m.observations == m.used_tools == ()
asyncio.run(check())
provider.force_flush()
assert len(exporter.get_finished_spans()) == 0
provider.shutdown()
assert attempts == []
print("zero public telemetry spans; zero tools; zero network attempts")
"""
    root = Path(__file__).resolve().parents[1]
    env = {
        "PATH": os.defpath,
        "PYTHONPATH": os.pathsep.join(
            [str(root), str(root / "tests"), os.environ.get("PYTHONPATH", "")]
        ),
        "PEX_REQUIRE_PROTOCOL_TESTS": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    assert result.stdout.strip() == "zero public telemetry spans; zero tools; zero network attempts"
