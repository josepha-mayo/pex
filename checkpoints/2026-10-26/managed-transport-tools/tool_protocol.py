"""WIP strict PEX tool contract and serializer; no provider or tool execution.

The public live transport remains denied. This module binds the COMPLETE prompt
and authoritative schemas from the installed PEX source; it does not replace
PEX owner, workspace, evidence, action or budget admission.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from importlib.metadata import version
from typing import Literal

from jsonschema import Draft202012Validator, validators
from jsonschema.exceptions import SchemaError, ValidationError

from managed_chat import Refusal, Role, _strict_json

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,63}\Z")
_CALL_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_EVIDENCE_NAMES = frozenset({
    "get_goal", "get_session_state", "get_recent_events", "get_scores",
    "inspect_acceptance", "get_context", "get_context_items", "get_decisions",
    "inspect_workspace", "inspect_git", "inspect_file", "inspect_artifact",
    "inspect_process", "run_verification",
})
_FINAL = {"planner": "SupervisorDecision", "verifier": "IndependentVerifierDecision"}
_MAX_TOOLS = 15
_MAX_CALLS = 16
_MAX_MESSAGES = 64


def _text(value, maximum, *, empty=False):
    if type(value) is not str or (not empty and not value) or "\x00" in value:
        raise Refusal("invalid_protocol_text")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError:
        raise Refusal("invalid_protocol_text") from None
    if size > maximum:
        raise Refusal("protocol_text_too_large")
    return value


def _bounded_json(value, *, max_depth=12, max_nodes=4096):
    nodes = 0
    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            raise Refusal("protocol_json_too_complex")
        if item is None or type(item) in (bool, int):
            if type(item) is int and abs(item) > 1_000_000_000_000:
                raise Refusal("protocol_integer_too_large")
        elif type(item) is float:
            if not math.isfinite(item):
                raise Refusal("nonfinite_json")
        elif type(item) is str:
            _text(item, 65536, empty=True)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif type(item) is dict:
            for key, child in item.items():
                _text(key, 256)
                visit(child, depth + 1)
        else:
            raise Refusal("unsupported_protocol_json_type")
    visit(value, 0)


def _canonical(value, maximum=65536):
    _bounded_json(value, max_depth=24, max_nodes=8192)
    try:
        rendered = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (ValueError, TypeError, UnicodeEncodeError):
        raise Refusal("invalid_protocol_json") from None
    return _text(rendered, maximum)


def _schema_safety(schema):
    _bounded_json(schema, max_depth=24, max_nodes=8192)
    def visit(value):
        if type(value) is dict:
            for key, child in value.items():
                if key == "$ref" and (type(child) is not str or not child.startswith(("#/$defs/", "#/definitions/"))):
                    raise Refusal("external_or_unsupported_schema_reference")
                if key in {"$id", "$dynamicRef", "$recursiveRef"}:
                    raise Refusal("external_or_unsupported_schema_reference")
                visit(child)
        elif type(value) is list:
            for child in value:
                visit(child)
    visit(schema)
    if type(schema) is not dict or schema.get("type") != "object":
        raise Refusal("tool_schema_must_be_object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise Refusal("invalid_tool_schema") from None


_STRICT_TYPES = Draft202012Validator.TYPE_CHECKER.redefine_many({
    "integer": lambda _, value: type(value) is int,
    "boolean": lambda _, value: type(value) is bool,
    "number": lambda _, value: type(value) in (int, float) and math.isfinite(value),
})
StrictValidator = validators.extend(Draft202012Validator, type_checker=_STRICT_TYPES)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    authoritative_schema_json: str
    advertised_spec_json: str
    final: bool = False

    def __post_init__(self):
        if type(self.name) is not str or not _NAME.fullmatch(self.name):
            raise Refusal("invalid_tool_name")
        _text(self.description, 16384)
        _text(self.authoritative_schema_json, 65536)
        _schema_safety(_strict_json(self.authoritative_schema_json.encode()))
        _text(self.advertised_spec_json, 65536)
        if type(self.final) is not bool:
            raise Refusal("invalid_tool_kind")

    def wire_spec(self):
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": _strict_json(self.authoritative_schema_json.encode()),
        }}

    def validate_arguments(self, raw):
        _text(raw, 16384 if self.final else 4096)
        value = _strict_json(raw.encode())
        if type(value) is not dict:
            raise Refusal("tool_arguments_must_be_object")
        _bounded_json(value)
        schema = _strict_json(self.authoritative_schema_json.encode())
        # Current PEX evidence functions have explicit named arguments and no
        # **kwargs. Their decorator's Pydantic model otherwise ignores extras.
        if value.keys() - set(schema.get("properties", {})):
            raise Refusal("unknown_tool_argument")
        try:
            StrictValidator(schema).validate(value)
        except (ValidationError, RecursionError):
            raise Refusal("tool_arguments_schema_mismatch") from None
        return value


@dataclass(frozen=True, slots=True)
class ProtocolContract:
    role: Role
    invocation_id: str
    request_digest: str
    system_prompt: str
    definitions: tuple[ToolDefinition, ...]
    max_rounds: int = 3

    def __post_init__(self):
        if self.role not in _FINAL or type(self.definitions) is not tuple:
            raise Refusal("invalid_protocol_contract")
        _text(self.invocation_id, 128)
        _text(self.request_digest, 128)
        _text(self.system_prompt, 65536)
        if type(self.max_rounds) is not int or self.max_rounds != 3:
            raise Refusal("unsupported_round_budget")
        if not 1 <= len(self.definitions) <= _MAX_TOOLS or any(type(item) is not ToolDefinition for item in self.definitions):
            raise Refusal("invalid_tool_catalog")
        names = tuple(item.name for item in self.definitions)
        if len(names) != len(set(names)):
            raise Refusal("duplicate_tool_definition")
        finals = [item.name for item in self.definitions if item.final]
        if finals != [_FINAL[self.role]]:
            raise Refusal("wrong_stage_final_tool")
        if any(item.name not in _EVIDENCE_NAMES for item in self.definitions if not item.final):
            raise Refusal("unapproved_evidence_tool")

    @property
    def final_name(self):
        return _FINAL[self.role]

    @property
    def fingerprint(self):
        data = [self.role, self.invocation_id, self.request_digest, self.system_prompt,
                [[item.name, item.description, item.authoritative_schema_json, item.advertised_spec_json, item.final] for item in self.definitions], self.max_rounds]
        return hashlib.sha256(_canonical(data, 262144).encode()).hexdigest()

    def definition(self, name):
        for item in self.definitions:
            if item.name == name:
                return item
        raise Refusal("tool_not_offered")

    def offered(self, specs):
        if type(specs) is not list or not specs:
            raise Refusal("invalid_offered_tools")
        names = []
        for spec in specs:
            if type(spec) is not dict:
                raise Refusal("invalid_offered_tools")
            definition = self.definition(spec.get("name"))
            if _canonical(spec) != definition.advertised_spec_json:
                raise Refusal("tool_spec_changed_after_binding")
            names.append(definition.name)
        if len(names) != len(set(names)):
            raise Refusal("duplicate_offered_tool")
        if set(names) not in ({item.name for item in self.definitions}, {self.final_name}):
            raise Refusal("unsupported_offered_tool_subset")
        return tuple(names)

    def tool_choice(self, choice, offered):
        if choice is None or choice == {"auto": {}}:
            return "auto"
        if choice == {"any": {}}:
            return "required"
        if type(choice) is dict and set(choice) == {"tool"} and type(choice["tool"]) is dict and set(choice["tool"]) == {"name"}:
            name = choice["tool"]["name"]
            if name in offered:
                return {"type": "function", "function": {"name": name}}
        raise Refusal("unsupported_tool_choice")


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class TextMessage:
    role: Literal["user", "assistant"]
    text: str


@dataclass(frozen=True, slots=True)
class AssistantTools:
    calls: tuple[ToolCall, ...]
    text: str | None = None


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    text: str
    status: Literal["success", "error"] = "success"


def validate_calls(contract, calls, offered, seen=frozenset()):
    if type(calls) is not tuple or not 1 <= len(calls) <= _MAX_CALLS:
        raise Refusal("invalid_tool_call_count")
    ids = set()
    for call in calls:
        if type(call) is not ToolCall or type(call.call_id) is not str or not _CALL_ID.fullmatch(call.call_id):
            raise Refusal("invalid_tool_call_id")
        if call.call_id in ids or call.call_id in seen:
            raise Refusal("duplicate_or_reused_tool_call_id")
        ids.add(call.call_id)
        if call.name not in offered:
            raise Refusal("tool_not_offered")
        contract.definition(call.name).validate_arguments(call.arguments_json)
    if any(call.name == contract.final_name for call in calls) and len(calls) != 1:
        raise Refusal("final_tool_must_be_alone")
    return ids


def serialize_history(contract, messages):
    if type(messages) is not tuple or not 1 <= len(messages) <= _MAX_MESSAGES:
        raise Refusal("invalid_message_history")
    if type(messages[0]) is not TextMessage or messages[0].role != "user":
        raise Refusal("history_must_start_with_user")
    output = [{"role": "system", "content": contract.system_prompt}]
    pending, seen = set(), set()
    offered = tuple(item.name for item in contract.definitions)
    for message in messages:
        if type(message) is ToolResult:
            if message.call_id not in pending or message.status not in {"success", "error"}:
                raise Refusal("orphan_or_duplicate_tool_result")
            _text(message.text, 8000)
            # The evidence envelope is already a JSON STRING. Preserve it
            # exactly, not json.loads/json.dumps or a different content block.
            output.append({"role": "tool", "tool_call_id": message.call_id, "content": message.text})
            pending.remove(message.call_id)
            continue
        if pending:
            raise Refusal("missing_tool_results")
        if type(message) is TextMessage:
            if message.role not in {"user", "assistant"}:
                raise Refusal("unsupported_message_role")
            output.append({"role": message.role, "content": _text(message.text, 131072)})
        elif type(message) is AssistantTools:
            ids = validate_calls(contract, message.calls, offered, seen)
            pending.update(ids)
            seen.update(ids)
            if message.text is not None:
                _text(message.text, 65536, empty=True)
            output.append({"role": "assistant", "content": message.text, "tool_calls": [
                {"id": call.call_id, "type": "function", "function": {"name": call.name, "arguments": call.arguments_json}}
                for call in message.calls
            ]})
        else:
            raise Refusal("unsupported_message_block")
    if pending:
        raise Refusal("missing_tool_results")
    return output, frozenset(seen)


@dataclass(frozen=True, slots=True)
class BoundPEXProtocol:
    contract: ProtocolContract
    tools: tuple[object, ...]
    collector: object
    used_tools: list[str]
    output_type: type


def bind_existing_pex(request, *, role: Role, invocation_id: str):
    """Bind actual PEX code-owned tools/prompts, never a supplied custom registry.

    This creates closures only; it neither reads a workspace nor calls a tool.
    The caller still has NO live-dispatch admission.
    """
    if version("strands-agents") != "1.53.0":
        raise Refusal("unsupported_strands_version")
    from pex_protocol.supervisor import SupervisorRequest, supervisor_request_digest
    from pex_supervisor.evidence_observations import EvidenceObservationCollector
    from pex_supervisor.evidence_tools import build_evidence_tools, select_evidence_tool_names
    from pex_supervisor.loop import IndependentVerifierDecision, SupervisorDecision, _system_prompt, _verifier_system_prompt
    from strands.tools.structured_output.structured_output_tool import StructuredOutputTool

    if type(request) is not SupervisorRequest or request.supervisor_decision_mode != "supervisor_model_only" or role not in _FINAL:
        raise Refusal("unsupported_pex_binding")
    output_type = SupervisorDecision if role == "planner" else IndependentVerifierDecision
    system_prompt = _system_prompt() if role == "planner" else _verifier_system_prompt()
    collector = EvidenceObservationCollector(request, stage="main" if role == "planner" else "verifier", invocation_id=invocation_id)
    used = []
    tools = build_evidence_tools(request, used, collector=collector, tool_names=select_evidence_tool_names(request))
    definitions = []
    for tool in tools:
        spec = tool.tool_spec
        # Pin this private API to the inspected Strands version. Its authoritative
        # model retains nullable arguments that the advertised schema removes.
        schema = tool._metadata.input_model.model_json_schema()
        definitions.append(ToolDefinition(spec["name"], spec["description"], _canonical(schema), _canonical(spec)))
    final = StructuredOutputTool(output_type).tool_spec
    definitions.append(ToolDefinition(final["name"], final["description"], _canonical(output_type.model_json_schema()), _canonical(final), True))
    contract = ProtocolContract(role, invocation_id, supervisor_request_digest(request), system_prompt, tuple(definitions))
    return BoundPEXProtocol(contract, tuple(tools), collector, used, output_type)
