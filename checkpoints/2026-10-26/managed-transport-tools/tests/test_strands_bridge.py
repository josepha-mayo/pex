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
    agent = m.make_agent()
    assert agent._retry_strategy.max_attempts == 1
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
