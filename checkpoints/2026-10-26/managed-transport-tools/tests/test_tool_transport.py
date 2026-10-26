"""Offline tool transport fixtures; no tool execution or provider inference."""

import copy
import json
from dataclasses import replace

import pytest
from test_managed_chat import ENDPOINT, MODEL, SYNTHETIC_KEY, VALID, response
from test_managed_chat import no_network as no_network
from test_managed_chat import rig as rig
from test_tool_protocol import EventType, bind, final_arguments, initial, request_fixture

import managed_chat as mc
import managed_tool_chat as mt
import tool_protocol as tp


def setup(role="planner", history=None, specs=None, choice=None):
    bound = bind(role)
    c = bound.contract
    candidate = mt.ManagedToolChatCandidate(mc.Route(ENDPOINT, MODEL, role), c)
    invocation = mt.ToolInvocation(
        c.invocation_id + ":1",
        c,
        history or (initial(c),),
        json.dumps(
            specs
            if specs is not None
            else [json.loads(item.advertised_spec_json) for item in c.definitions]
        ),
        json.dumps(choice),
    )
    return bound, candidate, invocation


async def run(candidate, invocation):
    return await candidate._execute_owned(
        invocation, mc._ScopedCredential(SYNTHETIC_KEY, candidate.route.fingerprint)
    )


def payload(name, arguments, call_id="call_fixture"):
    value = copy.deepcopy(VALID)
    value["choices"][0] = {
        "index": 0,
        "finish_reason": "tool_calls",
        "message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        },
    }
    return value


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["planner", "verifier"])
async def test_valid_role_final_response_and_full_authoritative_request(rig, role):
    bound, candidate, invocation = setup(role)
    data = payload(bound.contract.final_name, json.dumps(final_arguments(role)))
    rig.handler = lambda request: response(data)
    result = await run(candidate, invocation)
    assert result.receipt.outcome == "succeeded" and result.receipt.usage == mc.Usage(
        12, 3, 15, (("cached_tokens", 2),), (("reasoning_tokens", 1),)
    )
    assert (
        result.reply.finish_reason == "tool_calls"
        and result.reply.calls[0].name == bound.contract.final_name
    )
    assert result.protocol_fingerprint == bound.contract.fingerprint
    assert bound.used_tools == [] and bound.collector.observations == []
    request = json.loads(rig.calls[0].content)
    assert request["messages"][0]["content"] == bound.contract.system_prompt
    assert request["messages"][1]["content"] == bound.contract.initial_prompt
    final = next(
        tool for tool in request["tools"] if tool["function"]["name"] == bound.contract.final_name
    )
    assert final["function"]["parameters"] == bound.output_type.model_json_schema()
    assert request["stream"] is False and request["tool_choice"] == "auto"
    assert len(rig.calls) == rig.closed == 1


@pytest.mark.asyncio
async def test_public_tool_candidate_entry_stays_denied(rig):
    _, candidate, invocation = setup()
    result = await candidate.invoke(invocation)
    assert result.receipt.reason == "live_not_authorized" and result.receipt.attempts == 0
    assert rig.created == 0


@pytest.mark.asyncio
async def test_batched_evidence_calls_return_without_executing_tools(rig):
    bound, candidate, invocation = setup()
    data = payload("get_goal", '{"boundary_page":0}', "goal_call")
    data["choices"][0]["message"]["tool_calls"].append(
        payload("inspect_acceptance", "{}", "acceptance_call")["choices"][0]["message"][
            "tool_calls"
        ][0]
    )
    rig.handler = lambda request: response(data)
    result = await run(candidate, invocation)
    assert result.receipt.outcome == "succeeded" and len(result.reply.calls) == 2
    assert bound.used_tools == [] and bound.collector.observations == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "wrong_stage",
        "unknown_tool",
        "duplicate_id",
        "final_mixed",
        "bool_integer",
        "float_integer",
        "arguments_object",
        "arguments_duplicate",
        "arguments_nonfinite",
        "wrong_call_type",
        "stop_with_calls",
        "calls_without_calls",
        "too_many",
        "secret_arguments",
        "secret_id",
    ],
)
async def test_invalid_raw_tools_refuse_with_known_usage_no_executable_reply(rig, case):
    bound, candidate, invocation = setup()
    data = payload("get_goal", '{"boundary_page":0}')
    call = data["choices"][0]["message"]["tool_calls"][0]
    if case == "wrong_stage":
        call["function"]["name"] = "IndependentVerifierDecision"
    if case == "unknown_tool":
        call["function"]["name"] = "run_shell"
    if case == "duplicate_id":
        data["choices"][0]["message"]["tool_calls"].append(copy.deepcopy(call))
    if case == "final_mixed":
        data["choices"][0]["message"]["tool_calls"].append(
            payload(
                bound.contract.final_name, json.dumps(final_arguments("planner")), "final_call"
            )["choices"][0]["message"]["tool_calls"][0]
        )
    if case == "bool_integer":
        call["function"]["arguments"] = '{"boundary_page":true}'
    if case == "float_integer":
        call["function"]["arguments"] = '{"boundary_page":1.0}'
    if case == "arguments_object":
        call["function"]["arguments"] = {}
    if case == "arguments_duplicate":
        call["function"]["arguments"] = '{"boundary_page":0,"boundary_page":1}'
    if case == "arguments_nonfinite":
        call["function"]["arguments"] = '{"boundary_page":NaN}'
    if case == "wrong_call_type":
        call["type"] = "custom"
    if case == "stop_with_calls":
        data["choices"][0]["finish_reason"] = "stop"
    if case == "calls_without_calls":
        data["choices"][0]["message"]["tool_calls"] = None
    if case == "too_many":
        data["choices"][0]["message"]["tool_calls"] = [
            dict(call, id=f"call_{i}") for i in range(17)
        ]
    if case == "secret_arguments":
        call["function"]["arguments"] = json.dumps({"boundary_page": SYNTHETIC_KEY})
    if case == "secret_id":
        call["id"] = SYNTHETIC_KEY
    rig.handler = lambda request: response(data)
    result = await run(candidate, invocation)
    assert result.receipt.outcome == "uncertain" and result.receipt.usage is not None
    assert result.reply is None and bound.used_tools == []
    assert SYNTHETIC_KEY not in repr(result)
    assert len(rig.calls) == rig.closed == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [True, "12", 12.0, -1, None])
async def test_usage_failure_precedes_any_tool_argument_validation(rig, monkeypatch, bad):
    _, candidate, invocation = setup()
    data = payload("get_goal", '{"boundary_page":0}')
    data["usage"]["prompt_tokens"] = bad
    calls = []
    original = tp.ToolDefinition.validate_arguments

    def seen(self, raw):
        calls.append(True)
        return original(self, raw)

    monkeypatch.setattr(tp.ToolDefinition, "validate_arguments", seen)
    rig.handler = lambda request: response(data)
    result = await run(candidate, invocation)
    assert result.reply is None and result.receipt.usage is None
    assert calls == [] and len(rig.calls) == 1


@pytest.mark.asyncio
async def test_exact_evidence_text_round_trip_and_secret_in_tool_result_refused(rig):
    bound, candidate, _ = setup()
    c = bound.contract
    call = tp.ToolCall("old_call", "inspect_acceptance", "{}")
    evidence = '{ "pex_observation_id": "fixture", "value": "é" }'
    history = (initial(c), tp.AssistantTools((call,)), tp.ToolResult("old_call", evidence))
    invocation = mt.ToolInvocation(
        c.invocation_id + ":2",
        c,
        history,
        json.dumps([json.loads(item.advertised_spec_json) for item in c.definitions]),
    )
    rig.handler = lambda request: response(
        payload(c.final_name, json.dumps(final_arguments("planner")))
    )
    assert (await run(candidate, invocation)).receipt.outcome == "succeeded"
    assert json.loads(rig.calls[0].content)["messages"][-1]["content"].encode() == evidence.encode()
    secret_history = history[:-1] + (tp.ToolResult("old_call", SYNTHETIC_KEY),)
    secret_invocation = replace(
        invocation, invocation_id=c.invocation_id + ":3", history=secret_history
    )
    result = await run(candidate, secret_invocation)
    assert result.receipt.reason == "credential_in_prompt_refused" and result.receipt.attempts == 0
    assert len(rig.calls) == 1


def test_forced_final_catalog_choice_and_exact_prompt_are_coupled():
    c = bind().contract
    full = json.dumps([json.loads(item.advertised_spec_json) for item in c.definitions])
    final_only = json.dumps([json.loads(c.definition(c.final_name).advertised_spec_json)])
    history = (
        initial(c),
        tp.TextMessage("assistant", "Synthetic plain response"),
        tp.TextMessage("user", c.forced_final_prompt),
    )
    invocation = mt.ToolInvocation("forced_1", c, history, final_only, '{"any":{}}')
    assert invocation.forced()
    for specs, choice, messages in [
        (full, '{"any":{}}', history),
        (final_only, "null", history),
        (final_only, '{"any":{}}', (initial(c),)),
        (full, "null", history[:-1]),
    ]:
        with pytest.raises(mc.Refusal):
            mt.ToolInvocation("forced_bad", c, messages, specs, choice)


def test_full_prompt_fingerprint_bound_is_consistent_and_text_stays_complete():
    c = bind().contract
    long = replace(c, initial_prompt="x" * 65537)
    assert len(long.fingerprint) == 64
    assert (
        tp.serialize_history(long, (tp.TextMessage("user", long.initial_prompt),))[0][1]["content"]
        == "x" * 65537
    )
    with pytest.raises(mc.Refusal):
        replace(c, initial_prompt="x" * 131073)


def escaped_synthetic_key():
    return "".join(f"\\u{ord(char):04x}" for char in SYNTHETIC_KEY)


@pytest.mark.asyncio
@pytest.mark.parametrize("choice", [{"any": {}}, {"tool": {"name": "get_goal"}}])
async def test_required_or_named_choice_rejects_plain_stop(rig, choice):
    _, candidate, invocation = setup(choice=choice)
    rig.handler = lambda request: response(VALID)
    result = await run(candidate, invocation)
    assert result.receipt.reason == "response_tool_choice_mismatch"
    assert result.receipt.outcome == "uncertain" and result.receipt.usage is not None
    assert result.reply is None and len(rig.calls) == 1


@pytest.mark.asyncio
async def test_named_choice_rejects_another_offered_tool(rig):
    _, candidate, invocation = setup(choice={"tool": {"name": "get_goal"}})
    rig.handler = lambda request: response(payload("inspect_acceptance", "{}"))
    result = await run(candidate, invocation)
    assert result.receipt.reason == "response_tool_choice_mismatch" and result.reply is None
    assert result.receipt.usage is not None and len(rig.calls) == 1


@pytest.mark.asyncio
async def test_forced_final_rejects_plain_stop(rig):
    bound, candidate, _ = setup()
    c = bound.contract
    invocation = mt.ToolInvocation(
        "forced_refusal",
        c,
        (
            initial(c),
            tp.TextMessage("assistant", "Synthetic text"),
            tp.TextMessage("user", c.forced_final_prompt),
        ),
        json.dumps([json.loads(c.definition(c.final_name).advertised_spec_json)]),
        '{"any":{}}',
    )
    rig.handler = lambda request: response(VALID)
    result = await run(candidate, invocation)
    assert result.receipt.reason == "response_tool_choice_mismatch" and result.reply is None


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["value", "key"])
async def test_decoded_response_arguments_cannot_echo_credential(rig, field):
    bound, candidate, invocation = setup()
    escaped = escaped_synthetic_key()
    nested = '{"value":"' + escaped + '"}' if field == "value" else '{"' + escaped + '":0}'
    arguments = '{"action_type":"NOOP","rationale":"synthetic","payload":' + nested + "}"
    assert SYNTHETIC_KEY not in arguments
    rig.handler = lambda request: response(payload(bound.contract.final_name, arguments))
    result = await run(candidate, invocation)
    assert result.receipt.reason == "credential_in_response_refused"
    assert result.receipt.usage is not None and result.reply is None
    assert SYNTHETIC_KEY not in repr(result) and escaped not in repr(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["arguments", "evidence", "duplicate_evidence"])
async def test_embedded_outbound_json_secret_or_invalid_envelope_refuses_before_dispatch(
    rig, source
):
    bound, candidate, _ = setup()
    c = bound.contract
    if source == "arguments":
        bound = bind(request=request_fixture(EventType.TOOL_RESULT, with_boundaries=True))
        c = bound.contract
        candidate = mt.ManagedToolChatCandidate(mc.Route(ENDPOINT, MODEL, "planner"), c)
    escaped = escaped_synthetic_key()
    args = '{"path":"' + escaped + '"}' if source == "arguments" else "{}"
    name = "inspect_file" if source == "arguments" else "inspect_acceptance"
    evidence = '{"result":"' + escaped + '"}' if source != "arguments" else '{"result":0}'
    if source == "duplicate_evidence":
        evidence = '{"result":0,"result":"' + escaped + '"}'
    invocation = mt.ToolInvocation(
        "outbound_encoded",
        c,
        (
            initial(c),
            tp.AssistantTools((tp.ToolCall("prior_call", name, args),)),
            tp.ToolResult("prior_call", evidence),
        ),
        json.dumps([json.loads(item.advertised_spec_json) for item in c.definitions]),
    )
    result = await run(candidate, invocation)
    assert result.receipt.outcome == "refused" and result.receipt.attempts == 0
    assert result.receipt.usage is None and result.reply is None
    assert rig.created == rig.resolutions == len(rig.calls) == 0
    assert SYNTHETIC_KEY not in repr(result)


@pytest.mark.asyncio
async def test_plaintext_sdk_error_result_is_preserved_exactly(rig):
    bound, candidate, _ = setup()
    c = bound.contract
    error_text = "Synthetic local tool failure: café\nno mutation."
    invocation = mt.ToolInvocation(
        "error_text",
        c,
        (
            initial(c),
            tp.AssistantTools((tp.ToolCall("prior_call", "inspect_acceptance", "{}"),)),
            tp.ToolResult("prior_call", error_text, "error"),
        ),
        json.dumps([json.loads(item.advertised_spec_json) for item in c.definitions]),
    )
    rig.handler = lambda request: response(
        payload(c.final_name, json.dumps(final_arguments("planner")))
    )
    assert (await run(candidate, invocation)).receipt.outcome == "succeeded"
    assert (
        json.loads(rig.calls[0].content)["messages"][-1]["content"].encode() == error_text.encode()
    )
