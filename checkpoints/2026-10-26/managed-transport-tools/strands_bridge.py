"""Buffered, single-invocation PEX/Strands bridge; PUBLIC LIVE ENTRY IS DENIED.

Only the private owned path is exercised by authored offline fixtures. No native
SSE, TTFT, tokenizer, money-cap, production-admission or inference claim is made.
"""

from __future__ import annotations

import hashlib
from importlib.metadata import version

from strands import Agent
from strands.agent.conversation_manager import NullConversationManager
from strands.models.model import Model

from managed_chat import Refusal, Route
from managed_tool_chat import ManagedToolChatCandidate, ToolInvocation
from tool_protocol import (
    AssistantTools,
    TextMessage,
    ToolCall,
    ToolResult,
    _canonical,
    bind_existing_pex,
)

_ROLE_LIMITS = {
    "planner": {"turns": 3, "output_tokens": 1200, "total_tokens": 12000},
    "verifier": {"turns": 3, "output_tokens": 900, "total_tokens": 10000},
}


def _empty_state(value):
    return value is None or (type(value) is dict and not value)


def _text_block(content):
    if type(content) is not list or len(content) != 1:
        raise Refusal("unsupported_strands_content")
    block = content[0]
    if type(block) is not dict or set(block) != {"text"}:
        raise Refusal("unsupported_strands_content")
    return block["text"]


def _decode_messages(messages):
    """Decode the small actual PEX protocol, not generic multimodal content."""
    if type(messages) is not list or not 1 <= len(messages) <= 64:
        raise Refusal("invalid_strands_messages")
    decoded = []
    for message in messages:
        if type(message) is not dict or set(message) != {"role", "content"}:
            raise Refusal("unsupported_strands_message")
        role, content = message["role"], message["content"]
        if type(content) is not list or not 1 <= len(content) <= 16:
            raise Refusal("unsupported_strands_content")
        if role == "user":
            if len(content) == 1 and type(content[0]) is dict and set(content[0]) == {"text"}:
                decoded.append(TextMessage("user", _text_block(content)))
                continue
            for block in content:
                if type(block) is not dict or set(block) != {"toolResult"}:
                    raise Refusal("unsupported_strands_tool_result")
                result = block["toolResult"]
                if type(result) is not dict or set(result) != {"toolUseId", "status", "content"}:
                    raise Refusal("unsupported_strands_tool_result")
                decoded.append(
                    ToolResult(
                        result["toolUseId"], _text_block(result["content"]), result["status"]
                    )
                )
        elif role == "assistant":
            text, calls = None, []
            for block in content:
                if type(block) is not dict:
                    raise Refusal("unsupported_strands_content")
                if set(block) == {"text"} and text is None and not calls:
                    text = TextMessage("assistant", block["text"]).text
                elif set(block) == {"toolUse"}:
                    call = block["toolUse"]
                    if type(call) is not dict or set(call) != {"toolUseId", "name", "input"}:
                        raise Refusal("unsupported_strands_tool_use")
                    if type(call["input"]) is not dict:
                        raise Refusal("tool_arguments_must_be_object")
                    calls.append(
                        ToolCall(call["toolUseId"], call["name"], _canonical(call["input"]))
                    )
                else:
                    raise Refusal("unsupported_strands_content")
            if calls:
                decoded.append(
                    AssistantTools(tuple(calls), text if text and text.strip() else None)
                )
            elif text is not None:
                decoded.append(TextMessage("assistant", text))
            else:
                raise Refusal("empty_strands_assistant")
        else:
            raise Refusal("unsupported_strands_role")
    return tuple(decoded)


class ManagedPEXModel(Model):
    """One owned PEX invocation, created from a typed request, never a registry.

    Public stream/structured_output always refuse. Private offline execution is
    bounded to three calls, including forced-final, with no reset/retry API.
    """

    def __init__(self, route, request, *, invocation_id, proposal=None):
        if type(route) is not Route or version("strands-agents") != "1.53.0":
            raise Refusal("unsupported_bridge_configuration")
        self._bound = bind_existing_pex(
            request, role=route.role, invocation_id=invocation_id, proposal=proposal
        )
        if route.limits.max_output_tokens > _ROLE_LIMITS[route.role]["output_tokens"]:
            raise Refusal("role_output_cap_exceeded")
        self._candidate = ManagedToolChatCandidate(route, self._bound.contract)
        self._rounds = 0
        self._committed = (TextMessage("user", self.protocol.initial_prompt),)
        self._pending = frozenset()
        self._plain_reply = False
        self._terminal = False
        self._busy = False
        self._receipts = []
        self._failure = None

    @property
    def protocol(self):
        return self._bound.contract

    @property
    def receipts(self):
        return tuple(self._receipts)

    @property
    def observations(self):
        return tuple(item.model_copy(deep=True) for item in self._bound.collector.observations)

    @property
    def used_tools(self):
        return tuple(self._bound.used_tools)

    @property
    def failure(self):
        return self._failure

    def get_config(self):
        return {
            "model_id": self._candidate.route.model_id,
            "mode": "buffered",
            "live_enabled": False,
        }

    def update_config(self, **model_config):
        raise Refusal("immutable_bridge_configuration")

    async def count_tokens(self, *args, **kwargs):
        raise Refusal("token_estimation_not_qualified")

    async def structured_output(self, *args, **kwargs):
        raise Refusal("live_not_authorized")
        yield  # pragma: no cover - preserve the abstract async-generator interface

    async def stream(self, *args, **kwargs):
        raise Refusal("live_not_authorized")
        yield  # pragma: no cover - public admission never depends on env/provenance

    def make_agent(self):
        # Code-owned construction. No caller tools, callbacks, hooks, client or
        # retry/context-management policy is accepted by this interface.
        return Agent(
            model=self,
            tools=list(self._bound.tools),
            system_prompt=self.protocol.system_prompt,
            structured_output_model=self._bound.output_type,
            callback_handler=None,
            retry_strategy=None,  # Strands1.53 => max_attempts=1, not default6.
            conversation_manager=NullConversationManager(),
        )

    async def invoke_async(self):
        # Even this owned high-level entry reaches the denied public stream.
        return await self.make_agent().invoke_async(
            self.protocol.initial_prompt, limits=dict(_ROLE_LIMITS[self.protocol.role])
        )

    def _validate_extension(self, history):
        if history[: len(self._committed)] != self._committed:
            raise Refusal("committed_history_changed")
        extension = history[len(self._committed) :]
        if self._rounds == 0:
            if extension:
                raise Refusal("unowned_initial_history")
        elif self._plain_reply:
            if extension != (TextMessage("user", self.protocol.forced_final_prompt),):
                raise Refusal("invalid_forced_final_extension")
        elif (
            len(extension) != len(self._pending)
            or any(type(item) is not ToolResult for item in extension)
            or {item.call_id for item in extension} != self._pending
        ):
            raise Refusal("unowned_tool_result_extension")

    def _reply_message(self, reply):
        if reply.calls:
            calls = tuple(
                ToolCall(
                    call.call_id,
                    call.name,
                    _canonical(
                        self.protocol.definition(call.name).validate_arguments(call.arguments_json)
                    ),
                )
                for call in reply.calls
            )
            return AssistantTools(calls, reply.text if reply.text and reply.text.strip() else None)
        return TextMessage("assistant", reply.text)

    def _events(self, reply, usage):
        # Full response, raw usage and every tool argument have already passed
        # validation. No partial executable tool event is ever exposed.
        events = [{"messageStart": {"role": "assistant"}}]
        index = 0
        if reply.text and (reply.text.strip() or not reply.calls):
            events.extend(
                [
                    {"contentBlockStart": {"contentBlockIndex": index, "start": {}}},
                    {
                        "contentBlockDelta": {
                            "contentBlockIndex": index,
                            "delta": {"text": reply.text},
                        }
                    },
                    {"contentBlockStop": {"contentBlockIndex": index}},
                ]
            )
            index += 1
        for call in reply.calls:
            events.extend(
                [
                    {
                        "contentBlockStart": {
                            "contentBlockIndex": index,
                            "start": {"toolUse": {"toolUseId": call.call_id, "name": call.name}},
                        }
                    },
                    {
                        "contentBlockDelta": {
                            "contentBlockIndex": index,
                            "delta": {"toolUse": {"input": call.arguments_json}},
                        }
                    },
                    {"contentBlockStop": {"contentBlockIndex": index}},
                ]
            )
            index += 1
        wire_usage = {
            "inputTokens": usage.input_tokens,
            "outputTokens": usage.output_tokens,
            "totalTokens": usage.total_tokens,
        }
        cached = dict(usage.input_details).get("cached_tokens")
        if cached is not None:
            wire_usage["cacheReadInputTokens"] = cached
        events.extend(
            [
                {"messageStop": {"stopReason": "tool_use" if reply.calls else "end_turn"}},
                {"metadata": {"usage": wire_usage}},
            ]
        )
        return events

    async def _stream_owned(
        self,
        messages,
        tool_specs=None,
        system_prompt=None,
        *,
        credential,
        tool_choice=None,
        system_prompt_content=None,
        invocation_state=None,
        **kwargs,
    ):
        """Private offline implementation. Not a live-admission entry point."""
        if self._terminal or self._busy:
            self._terminal = True
            raise Refusal("bridge_terminal_or_concurrent")
        self._busy = True
        consumed = False
        try:
            if self._rounds >= self.protocol.max_rounds:
                raise Refusal("bridge_round_budget_exhausted")
            if (
                system_prompt != self.protocol.system_prompt
                or system_prompt_content != [{"text": self.protocol.system_prompt}]
                or not _empty_state(invocation_state)
                or set(kwargs) - {"model_state"}
                or not _empty_state(kwargs.get("model_state"))
            ):
                raise Refusal("unowned_strands_configuration")
            history = _decode_messages(messages)
            self._validate_extension(history)
            call_id = hashlib.sha256(self.protocol.invocation_id.encode()).hexdigest()[:40]
            invocation = ToolInvocation(
                f"{call_id}.{self._rounds + 1}",
                self.protocol,
                history,
                _canonical(tool_specs, 262144),
                _canonical(tool_choice),
            )
            self._rounds += 1  # Forced-final consumes the SAME finite allowance.
            try:
                completion = await self._candidate._execute_owned(invocation, credential)
            finally:
                receipt = self._candidate.receipt(invocation.invocation_id)
                if receipt is not None:
                    self._receipts.append(receipt)
            if completion.receipt.outcome != "succeeded" or completion.reply is None:
                raise Refusal("managed_transport_not_validated")
            if self._terminal:
                raise Refusal("bridge_terminal_or_concurrent")
            reply = completion.reply
            if any(call.name == self.protocol.final_name for call in reply.calls):
                # JSON validation retains enum JSON semantics while requiring raw
                # strict booleans/numbers before Strands' coercive output tool.
                self._bound.output_type.model_validate_json(
                    reply.calls[0].arguments_json, strict=True
                )
                self._terminal = True
            self._committed = history + (self._reply_message(reply),)
            self._pending = frozenset(call.call_id for call in reply.calls)
            self._plain_reply = not reply.calls
            events = self._events(reply, completion.receipt.usage)
            for event in events:
                yield event
            consumed = True
        except Refusal as exc:
            self._failure = str(exc)
            self._terminal = True
            raise
        except BaseException:
            self._failure = "bridge_interrupted_or_invalid"
            self._terminal = True
            raise
        finally:
            if not consumed:
                self._terminal = True
            self._busy = False
