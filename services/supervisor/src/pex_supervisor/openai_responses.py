"""Narrow OpenAI Responses API adapter for Strands-compatible endpoints."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import openai
from strands.models.openai import OpenAIModel


def _value(item: object, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for message in messages:
        role = message["role"]
        text: list[str] = []
        for block in message.get("content") or []:
            if "text" in block:
                text.append(str(block["text"]))
            elif "toolUse" in block:
                if text:
                    result.append({"role": role, "content": "\n".join(text)})
                    text.clear()
                tool = block["toolUse"]
                result.append(
                    {
                        "type": "function_call",
                        "call_id": tool["toolUseId"],
                        "name": tool["name"],
                        "arguments": json.dumps(
                            tool.get("input") or {}, separators=(",", ":"), allow_nan=False
                        ),
                    }
                )
            elif "toolResult" in block:
                if text:
                    result.append({"role": role, "content": "\n".join(text)})
                    text.clear()
                tool_result = block["toolResult"]
                output = tool_result.get("content") or []
                result.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_result["toolUseId"],
                        "output": json.dumps(output, separators=(",", ":"), allow_nan=False),
                    }
                )
        if text:
            result.append({"role": role, "content": "\n".join(text)})
    return result


class OpenAIResponsesModel(OpenAIModel):
    """Use ``responses.create`` while emitting the standard Strands event protocol."""

    def __init__(self, *, http_client_factory=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._http_client_factory = http_client_factory

    @asynccontextmanager
    async def _get_client(self):
        if self._custom_client is not None or self._http_client_factory is None:
            async with super()._get_client() as client:
                yield client
            return
        client_args = self._resolve_client_args()
        client_args["http_client"] = self._http_client_factory()
        async with openai.AsyncOpenAI(**client_args) as client:
            yield client

    async def stream(
        self,
        messages,
        tool_specs=None,
        system_prompt=None,
        *,
        tool_choice=None,
        system_prompt_content=None,
        **kwargs,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if tool_choice not in (None, {"auto": {}}, {"any": {}}):
            raise ValueError("specific tool choice is unsupported by this endpoint")
        request: dict[str, Any] = {
            "model": self.config["model_id"],
            "input": _responses_input(messages),
            "max_output_tokens": 1200,
            "reasoning": {"effort": "low"},
            "tools": [
                {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"]["json"],
                }
                for tool in tool_specs or []
            ],
        }
        if system_prompt:
            request["instructions"] = system_prompt
        if tool_specs:
            request["tool_choice"] = "auto"

        async with self._get_client() as client:
            response = await client.responses.create(**request)

        yield {"messageStart": {"role": "assistant"}}
        used_tool = False
        for item in _value(response, "output", []) or []:
            item_type = _value(item, "type")
            if item_type == "message":
                for content in _value(item, "content", []) or []:
                    if _value(content, "type") != "output_text":
                        continue
                    text = _value(content, "text", "")
                    if text:
                        yield {"contentBlockStart": {"start": {}}}
                        yield {"contentBlockDelta": {"delta": {"text": text}}}
                        yield {"contentBlockStop": {}}
            elif item_type == "function_call":
                used_tool = True
                yield {
                    "contentBlockStart": {
                        "start": {
                            "toolUse": {
                                "name": _value(item, "name"),
                                "toolUseId": _value(item, "call_id"),
                            }
                        }
                    }
                }
                yield {
                    "contentBlockDelta": {
                        "delta": {"toolUse": {"input": _value(item, "arguments", "")}}
                    }
                }
                yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use" if used_tool else "end_turn"}}
        usage = _value(response, "usage")
        if usage is not None:
            input_tokens = int(_value(usage, "input_tokens", 0) or 0)
            output_tokens = int(_value(usage, "output_tokens", 0) or 0)
            yield {
                "metadata": {
                    "usage": {
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "totalTokens": input_tokens + output_tokens,
                    },
                    "metrics": {"latencyMs": 0},
                }
            }
