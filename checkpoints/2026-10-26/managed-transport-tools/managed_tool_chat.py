"""Owned bounded tool-response layer. No tool execution and no live admission."""

from __future__ import annotations

from dataclasses import dataclass, field

from managed_chat import (
    _ID,
    Completion,
    ManagedChatCandidate,
    Refusal,
    _contains_secret,
    _strict_json,
)
from tool_protocol import (
    ProtocolContract,
    TextMessage,
    ToolCall,
    _text,
    serialize_history,
    validate_calls,
)


@dataclass(frozen=True, slots=True)
class ToolInvocation:
    invocation_id: str
    contract: ProtocolContract = field(repr=False)
    history: tuple = field(repr=False)
    offered_specs_json: str = field(repr=False)
    tool_choice_json: str = "null"

    def __post_init__(self):
        if type(self.invocation_id) is not str or not _ID.fullmatch(self.invocation_id):
            raise Refusal("invalid_invocation_id")
        if type(self.contract) is not ProtocolContract:
            raise Refusal("unsupported_protocol_contract")
        _text(self.offered_specs_json, 262144)
        _text(self.tool_choice_json, 1024)
        offered = self.offered()
        choice = self.choice()
        wire_choice = self.contract.tool_choice(choice, offered)
        forced = self.forced()
        if offered == (self.contract.final_name,) and wire_choice == "required" and not forced:
            raise Refusal("invalid_forced_final_mode")
        serialize_history(self.contract, self.history, allow_forced_final=forced)
        last = self.history[-1]
        if type(last) is TextMessage and last.role == "assistant":
            raise Refusal("assistant_history_requires_forced_followup")
        if forced and not (
            type(last) is TextMessage
            and last.role == "user"
            and last.text == self.contract.forced_final_prompt
            and len(self.history) > 1
        ):
            raise Refusal("invalid_forced_final_mode")

    def offered(self):
        return self.contract.offered(_strict_json(self.offered_specs_json.encode()))

    def choice(self):
        return _strict_json(self.tool_choice_json.encode())

    def forced(self):
        return self.offered() == (self.contract.final_name,) and self.choice() == {"any": {}}


@dataclass(frozen=True, slots=True)
class AssistantReply:
    text: str | None = field(default=None, repr=False)
    calls: tuple[ToolCall, ...] = field(default=(), repr=False)
    finish_reason: str = "stop"


@dataclass(frozen=True, slots=True, repr=False)
class ToolCompletion(Completion):
    reply: AssistantReply | None = field(default=None, repr=False)
    protocol_fingerprint: str = ""


class ManagedToolChatCandidate(ManagedChatCandidate):
    """Private one-round execution shares all owned HTTP/accounting safeguards.

    Public invoke is inherited unchanged and always live-denied. This layer
    validates and RETURNS tool calls; it never executes them or opens a PEX gate.
    """

    __slots__ = ("_contract",)

    def __init__(self, route, contract):
        super().__init__(route)
        if type(contract) is not ProtocolContract or contract.role != route.role:
            raise Refusal("route_protocol_role_mismatch")
        self._contract = contract

    @property
    def contract(self):
        return self._contract

    def _accept_invocation(self, invocation):
        return type(invocation) is ToolInvocation and invocation.contract is self.contract

    def _body_fields(self):
        return super()._body_fields() | {"tools", "tool_choice"}

    def _request_payload(self, invocation):
        offered = invocation.offered()
        messages, _ = serialize_history(
            self.contract, invocation.history, allow_forced_final=invocation.forced()
        )
        return {
            "model": self.route.model_id,
            "stream": False,
            "n": 1,
            self.route.output_field: self.route.limits.max_output_tokens,
            "messages": messages,
            "tools": [self.contract.definition(name).wire_spec() for name in offered],
            "tool_choice": self.contract.tool_choice(invocation.choice(), offered),
        }

    def _response_content(self, raw, credential, invocation):
        # Called only AFTER complete bounded response + exact raw usage checks.
        if _contains_secret(raw, credential._value):
            raise Refusal("credential_in_response_refused")
        choices = raw.get("choices")
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            raise Refusal("invalid_response_choices")
        choice = choices[0]
        if type(choice.get("index")) is not int or choice["index"] != 0:
            raise Refusal("invalid_response_choice_index")
        message = choice.get("message")
        if (
            type(message) is not dict
            or message.get("role") != "assistant"
            or message.get("refusal") is not None
            or "function_call" in message
        ):
            raise Refusal("unsupported_response_message")
        content = message.get("content")
        if content is not None:
            _text(content, self.route.limits.max_response_bytes, empty=True)
        finish = choice.get("finish_reason")
        raw_calls = message.get("tool_calls")
        if finish == "stop":
            if raw_calls is not None or type(content) is not str or not content.strip():
                raise Refusal("stop_tool_mismatch_or_empty_text")
            return AssistantReply(content, (), "stop")
        if finish != "tool_calls" or type(raw_calls) is not list or not raw_calls:
            raise Refusal("incomplete_or_mismatched_tool_response")
        calls = []
        for item in raw_calls:
            if (
                type(item) is not dict
                or set(item) != {"id", "type", "function"}
                or item["type"] != "function"
            ):
                raise Refusal("invalid_function_call_shape")
            function = item["function"]
            if type(function) is not dict or set(function) != {"name", "arguments"}:
                raise Refusal("invalid_function_call_shape")
            calls.append(ToolCall(item["id"], function["name"], function["arguments"]))
        _, seen = serialize_history(
            self.contract, invocation.history, allow_forced_final=invocation.forced()
        )
        validate_calls(self.contract, tuple(calls), invocation.offered(), seen)
        return AssistantReply(content or None, tuple(calls), "tool_calls")

    def _completion(self, receipt, content=None):
        return ToolCompletion(
            receipt,
            content.text if content is not None else None,
            content,
            self.contract.fingerprint,
        )
