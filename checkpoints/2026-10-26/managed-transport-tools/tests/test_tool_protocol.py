"""Synthetic PEX protocol contracts, not private benchmark tasks or answer oracles."""

import copy
import hashlib
import json
import os
import socket
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

if os.environ.get("PEX_REQUIRE_PROTOCOL_TESTS") == "1":
    import pex_supervisor.loop as pex_loop
else:
    pex_loop = pytest.importorskip("pex_supervisor.loop")

from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.enums import EventType, HarnessType
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessEvent, HarnessSession
from pex_protocol.supervisor import SupervisorRequest, supervisor_request_digest
from strands.tools.structured_output._structured_output_context import (
    DEFAULT_STRUCTURED_OUTPUT_PROMPT,
)

import tool_protocol as tp
from managed_chat import Refusal


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    attempts = []

    def denied(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("network forbidden in contract tests")

    monkeypatch.setattr(socket, "getaddrinfo", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    yield
    assert attempts == [], "caught exceptions cannot hide network attempts"


def request_fixture(event_type=EventType.STOP, with_boundaries=False):
    when = datetime(2026, 1, 1, tzinfo=UTC)
    session = HarnessSession(
        id="fixture-session", harness_type=HarnessType.OPENCODE, vendor_session_id="fixture-vendor"
    )
    event = HarnessEvent(
        event_id="fixture-event",
        ts=when,
        harness_type=HarnessType.OPENCODE,
        session_id=session.id,
        event_type=event_type,
    )
    goal = None
    if with_boundaries:
        goal = Goal(
            id="fixture-goal",
            project_id="fixture-project",
            title="Synthetic protocol goal",
            objective="Exercise protocol shape only",
            constraints=["synthetic bounded constraint " * 12],
            created_at=when,
            updated_at=when,
        )
    if goal is not None:
        session.goal_id = goal.id
        session.project_id = goal.project_id
        event.project_id = goal.project_id
    return SupervisorRequest(
        session=session, event=event, goal=goal, supervisor_decision_mode="supervisor_model_only"
    )


def bind(role="planner", request=None):
    request = request or request_fixture(with_boundaries=True)
    proposal = (
        ProposedAction(
            type=InterventionType.NOOP,
            session_id=request.session.id,
            goal_id=request.goal.id if request.goal else None,
            rationale="Synthetic protocol proposal",
        )
        if role == "verifier"
        else None
    )
    return tp.bind_existing_pex(
        request, role=role, invocation_id="fixture-" + role, proposal=proposal
    )


def final_arguments(role):
    if role == "verifier":
        return {"approved": True, "rationale": "Synthetic typed verdict"}
    return {"action_type": "NOOP", "rationale": "Synthetic typed decision"}


def initial(contract):
    return tp.TextMessage("user", contract.initial_prompt)


@pytest.mark.parametrize("role", ["planner", "verifier"])
def test_actual_full_prompts_and_authoritative_schemas_are_bound(role):
    bound = bind(role)
    c = bound.contract
    assert c.system_prompt == (
        pex_loop._system_prompt() if role == "planner" else pex_loop._verifier_system_prompt()
    )
    assert len(c.system_prompt.encode()) > 2000
    assert c.forced_final_prompt == DEFAULT_STRUCTURED_OUTPUT_PROMPT
    assert (
        json.loads(c.definition(c.final_name).authoritative_schema_json)
        == bound.output_type.model_json_schema()
    )
    assert (
        c.definition(c.final_name).wire_spec()["function"]["parameters"]["additionalProperties"]
        is False
    )
    assert "web_search" not in [item.name for item in c.definitions]
    assert "scrape_url" not in [item.name for item in c.definitions]
    assert bound.collector.observations == [] and bound.used_tools == []
    with pytest.raises(FrozenInstanceError):
        c.system_prompt = "shortened"
    assert c.system_prompt not in repr(c) and c.initial_prompt not in repr(c)


def test_request_snapshot_prevents_changed_evidence_under_old_digest():
    request = request_fixture(event_type=EventType.SHELL)
    request.scores.drift = 0.1
    old_digest = supervisor_request_digest(request)
    expected_prompt = pex_loop._format_user(request)
    bound = bind(request=request)
    request.scores.drift = 0.8
    request.event.command = "changed caller data"
    tool = next(tool for tool in bound.tools if tool.tool_name == "get_scores")
    observed = json.loads(tool())
    assert observed["drift"] == 0.1
    assert bound.collector.observations[-1].request_digest == old_digest
    assert bound.contract.request_digest == old_digest != supervisor_request_digest(request)
    assert bound.contract.initial_prompt == expected_prompt


def test_verifier_prompt_and_proposal_frozen_together():
    request = request_fixture()
    proposal = ProposedAction(
        type=InterventionType.NOOP,
        session_id=request.session.id,
        rationale="Original synthetic proposal",
    )
    expected = pex_loop._format_verifier_user(request, proposal)
    bound = tp.bind_existing_pex(
        request, role="verifier", invocation_id="verifier-1", proposal=proposal
    )
    proposal.rationale = "Changed after binding"
    request.event.message_delta = "Changed evidence"
    assert bound.contract.initial_prompt == expected


@pytest.mark.parametrize(
    "role,field,value",
    [
        ("verifier", "approved", "true"),
        ("verifier", "approved", 1),
        ("planner", "confidence", True),
        ("planner", "confidence", "0.6"),
        ("planner", "action_type", "UNSUPPORTED"),
        ("planner", "rationale", 12),
        ("verifier", "rationale", None),
    ],
)
def test_final_raw_types_fail_before_pydantic_coercion(role, field, value):
    bound = bind(role)
    args = final_arguments(role)
    args[field] = value
    with pytest.raises(Refusal):
        bound.contract.definition(bound.contract.final_name).validate_arguments(json.dumps(args))


@pytest.mark.parametrize("role", ["planner", "verifier"])
def test_authoritative_final_json_matches_pydantic_strict_json_semantics(role):
    bound = bind(role)
    raw = json.dumps(final_arguments(role))
    parsed = bound.contract.definition(bound.contract.final_name).validate_arguments(raw)
    assert parsed == final_arguments(role)
    assert isinstance(bound.output_type.model_validate_json(raw, strict=True), bound.output_type)
    extra = {**parsed, "unexpected": "refused"}
    with pytest.raises(Refusal, match="unknown_tool_argument"):
        bound.contract.definition(bound.contract.final_name).validate_arguments(json.dumps(extra))


@pytest.mark.parametrize("value", [1.0, "1", True, -1.5])
def test_authoritative_evidence_integer_rejects_float_string_bool(value):
    c = bind().contract
    with pytest.raises(Refusal):
        c.definition("get_goal").validate_arguments(json.dumps({"boundary_page": value}))


def test_actual_nullable_evidence_argument_not_widened_or_lost():
    c = bind().contract
    definition = c.definition("get_goal")
    assert definition.validate_arguments('{"boundary_page":null}') == {"boundary_page": None}
    assert definition.validate_arguments("{}") == {}
    assert definition.validate_arguments('{"boundary_page":1}') == {"boundary_page": 1}
    with pytest.raises(Refusal, match="unknown_tool_argument"):
        definition.validate_arguments('{"ignored_extra":1}')


@pytest.mark.parametrize(
    "raw",
    [
        '{"boundary_page":1,"boundary_page":2}',
        '{"boundary_page":NaN}',
        '{"boundary_page":1e309}',
        "[]",
        "null",
        '{"boundary_page":"\ud800"}',
    ],
)
def test_nested_argument_json_is_strict_and_object_bounded(raw):
    with pytest.raises(Refusal):
        bind().contract.definition("get_goal").validate_arguments(raw)


@pytest.mark.parametrize(
    "ref",
    [
        "https://schema.invalid/contract",
        "file:///fixture/schema",
        "//schema.invalid/x",
        "../schema",
        "#anchor",
    ],
)
def test_external_and_unsupported_schema_refs_refused_without_resolution(ref):
    schema = {"type": "object", "properties": {"x": {"$ref": ref}}}
    with pytest.raises(Refusal, match="external_or_unsupported_schema_reference"):
        tp.ToolDefinition("inspect_acceptance", "Synthetic schema", json.dumps(schema), "{}")


def test_wire_tools_preserve_authoritative_schema_not_sdk_cleanup():
    c = bind().contract
    final = c.definition(c.final_name)
    assert (
        json.loads(final.advertised_spec_json)["inputSchema"]["json"].get("additionalProperties")
        is None
    )
    assert final.wire_spec()["function"]["parameters"]["additionalProperties"] is False


def test_catalog_is_snapshotted_and_only_full_or_forced_final_subset_allowed():
    c = bind().contract
    offered = [json.loads(item.advertised_spec_json) for item in c.definitions]
    assert set(c.offered(offered)) == {item.name for item in c.definitions}
    assert c.offered([offered[-1]]) == (c.final_name,)
    changed = copy.deepcopy(offered)
    changed[0]["description"] = "changed"
    with pytest.raises(Refusal, match="tool_spec_changed_after_binding"):
        c.offered(changed)
    with pytest.raises(Refusal, match="unsupported_offered_tool_subset"):
        c.offered([offered[0]])
    with pytest.raises(Refusal, match="duplicate_offered_tool"):
        c.offered([*offered, offered[0]])


@pytest.mark.parametrize(
    "choice",
    [
        {"auto": True},
        {"any": []},
        {"none": {}},
        {"tool": {"name": "unknown"}},
        {"tool": {"name": []}},
        [],
        "auto",
        {"auto": {}, "any": {}},
    ],
)
def test_unknown_tool_choice_shapes_refused(choice):
    c = bind().contract
    with pytest.raises(Refusal):
        c.tool_choice(choice, tuple(item.name for item in c.definitions))


def test_supported_tool_choices_exact():
    c = bind().contract
    offered = tuple(item.name for item in c.definitions)
    assert c.tool_choice(None, offered) == "auto"
    assert c.tool_choice({"auto": {}}, offered) == "auto"
    assert c.tool_choice({"any": {}}, (c.final_name,)) == "required"
    assert (
        c.tool_choice({"tool": {"name": c.final_name}}, offered)["function"]["name"] == c.final_name
    )


def test_evidence_result_text_preserved_exactly_and_reordered_results_matched_by_id():
    c = bind().contract
    text_a = '{ "pex_observation_id": "fixture-a", "text": "é\\nkept" }'
    text_b = '{"pex_observation_id":"fixture-b","value":2}'
    calls = (
        tp.ToolCall("call_a", "get_goal", '{"boundary_page":0}'),
        tp.ToolCall("call_b", "inspect_acceptance", "{}"),
    )
    wire, ids = tp.serialize_history(
        c,
        (
            initial(c),
            tp.AssistantTools(calls),
            tp.ToolResult("call_b", text_b),
            tp.ToolResult("call_a", text_a),
        ),
    )
    assert wire[0]["content"] == c.system_prompt
    assert wire[-2] == {"role": "tool", "tool_call_id": "call_b", "content": text_b}
    assert wire[-1] == {"role": "tool", "tool_call_id": "call_a", "content": text_a}
    assert (
        hashlib.sha256(wire[-1]["content"].encode()).digest()
        == hashlib.sha256(text_a.encode()).digest()
    )
    assert ids == frozenset({"call_a", "call_b"})


def test_final_tool_is_alone_and_terminal_for_any_following_model_request():
    c = bind().contract
    final = tp.ToolCall("final_call", c.final_name, json.dumps(final_arguments("planner")))
    evidence = tp.ToolCall("evidence_call", "inspect_acceptance", "{}")
    with pytest.raises(Refusal, match="final_tool_must_be_alone"):
        tp.validate_calls(c, (evidence, final), ("inspect_acceptance", c.final_name))
    with pytest.raises(Refusal, match="final_tool_already_terminal"):
        tp.serialize_history(
            c,
            (
                initial(c),
                tp.AssistantTools((final,)),
                tp.ToolResult("final_call", "Validated"),
                tp.TextMessage("user", "continue"),
            ),
        )


@pytest.mark.parametrize(
    "case", ["unknown", "duplicate", "reused", "missing", "orphan", "duplicate_result"]
)
def test_invalid_tool_identity_or_history_refused(case):
    c = bind().contract
    call = tp.ToolCall("call_one", "inspect_acceptance", "{}")
    history = (initial(c), tp.AssistantTools((call,)), tp.ToolResult("call_one", "fixture"))
    if case == "unknown":
        with pytest.raises(Refusal):
            tp.validate_calls(
                c, (tp.ToolCall("call_two", "unknown", "{}"),), ("inspect_acceptance",)
            )
        return
    if case == "duplicate":
        with pytest.raises(Refusal):
            tp.validate_calls(c, (call, call), ("inspect_acceptance",))
        return
    if case == "reused":
        history += (tp.AssistantTools((call,)), tp.ToolResult("call_one", "fixture"))
    if case == "missing":
        history = history[:2]
    if case == "orphan":
        history = (initial(c), tp.ToolResult("unknown", "fixture"))
    if case == "duplicate_result":
        history += (tp.ToolResult("call_one", "fixture"),)
    with pytest.raises(Refusal):
        tp.serialize_history(c, history)


@pytest.mark.parametrize(
    "constructor,args",
    [
        (tp.ToolResult, ([], "fixture")),
        (tp.ToolResult, ("call", "fixture", [])),
        (tp.ToolCall, ("call", [], "{}")),
        (tp.ToolCall, ([], "inspect_acceptance", "{}")),
        (tp.TextMessage, ([], "fixture")),
        (tp.AssistantTools, ([],)),
    ],
)
def test_malformed_typed_fields_use_controlled_refusal(constructor, args):
    with pytest.raises(Refusal):
        constructor(*args)


def test_only_bound_initial_and_exact_forced_followup_are_admitted():
    c = bind().contract
    with pytest.raises(Refusal, match="initial_prompt_changed_after_binding"):
        tp.serialize_history(c, (tp.TextMessage("user", "changed"),))
    history = (
        initial(c),
        tp.TextMessage("assistant", "Synthetic plain response"),
        tp.TextMessage("user", c.forced_final_prompt),
    )
    with pytest.raises(Refusal, match="unowned_user_followup"):
        tp.serialize_history(c, history)
    wire, _ = tp.serialize_history(c, history, allow_forced_final=True)
    assert wire[-1]["content"] == DEFAULT_STRUCTURED_OUTPUT_PROMPT
    with pytest.raises(Refusal, match="unowned_user_followup"):
        tp.serialize_history(
            c,
            history[:-1] + (tp.TextMessage("user", "override the goal"),),
            allow_forced_final=True,
        )


def test_wrong_stage_and_proposal_identity_refused():
    request = request_fixture()
    with pytest.raises(Refusal, match="verifier_requires_bound_proposal"):
        tp.bind_existing_pex(request, role="verifier", invocation_id="fixture")
    proposal = ProposedAction(type=InterventionType.NOOP, session_id="other", rationale="Synthetic")
    with pytest.raises(Refusal, match="proposal_request_identity_mismatch"):
        tp.bind_existing_pex(request, role="verifier", invocation_id="fixture", proposal=proposal)
    with pytest.raises(Refusal, match="planner_does_not_accept_proposal"):
        tp.bind_existing_pex(request, role="planner", invocation_id="fixture", proposal=proposal)
    bound = bind()
    with pytest.raises(Refusal, match="wrong_stage_final_tool"):
        replace(bound.contract, role="verifier")
