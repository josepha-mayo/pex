"""Pinned stateless Responses requests using the controller's existing IPC budget."""

import re

from benchmarks.model_relay import SCHEMA, PinnedModelRelay

FIELDS = {
    "model", "input", "instructions", "tools", "tool_choice", "parallel_tool_calls",
    "max_output_tokens", "temperature", "top_p", "reasoning", "text", "stream", "store",
    "include", "truncation", "prompt_cache_key", "service_tier", "client_metadata",
}
INPUT_TYPES = {
    "message", "function_call", "function_call_output", "custom_tool_call",
    "custom_tool_call_output", "reasoning",
}


def _text_content(value):
    if isinstance(value, str):
        return
    if (not isinstance(value, list) or len(value) > 128
            or any(not isinstance(part, dict)
                   or set(part) - {"type", "text", "refusal", "annotations"}
                   or part.get("type") not in {"input_text", "output_text", "refusal"}
                   or not isinstance(part.get("refusal" if part.get("type") == "refusal"
                                              else "text"), str)
                   or part.get("annotations", []) != [] for part in value)):
        raise ValueError("Responses content must be self-contained text")


class PinnedResponsesRelay(PinnedModelRelay):
    """No hosted tools, stored state, retries or ambient provider credentials.

    Backend configuration remains controller-owned. HTTP/SSE framing and real
    provider receipts are separate from this non-streaming IPC contract.
    """

    def __init__(self, *, model, max_calls, deadline, backend):
        if not callable(backend):
            raise ValueError("Responses backend must be callable")

        async def completed_backend(body):
            result = await backend(body)
            if (not isinstance(result, dict) or result.get("model") != model
                    or result.get("status") != "completed"
                    or not isinstance(result.get("output"), list)
                    or len(result["output"]) > 256):
                raise ValueError("Responses backend did not return a pinned completed result")
            return result

        super().__init__(model=model, max_calls=max_calls, deadline=deadline,
                         backend=completed_backend)

    def _validate(self, payload):
        if not isinstance(payload, dict) or set(payload) != {"schema", "request_id", "body"}:
            raise ValueError("invalid Responses request envelope")
        identity, body = payload["request_id"], payload["body"]
        if (payload["schema"] != SCHEMA or not isinstance(identity, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", identity)):
            raise ValueError("invalid Responses request identity")
        if (not isinstance(body, dict) or set(body) - FIELDS or body.get("model") != self.model
                or body.get("stream", False) is not False or body.get("store") is not False):
            raise ValueError("Responses request does not match the pinned stateless contract")
        tokens = body.get("max_output_tokens")
        if type(tokens) is not int or not 1 <= tokens <= 16_384:
            raise ValueError("Responses request requires a bounded output token limit")
        metadata = body.get("client_metadata", {})
        if (not isinstance(metadata, dict) or len(metadata) > 16
                or any(not isinstance(key, str) or len(key) > 128
                       or not isinstance(value, str) or len(value) > 4096
                       for key, value in metadata.items())):
            raise ValueError("Responses client metadata must be bounded text")
        value = body.get("input")
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("Responses input cannot be empty")
        elif isinstance(value, list) and 1 <= len(value) <= 256:
            for item in value:
                if not isinstance(item, dict) or item.get("type", "message") not in INPUT_TYPES:
                    raise ValueError("unsupported Responses input item")
                if item.get("type", "message") == "message" and item.get("role") not in {
                    "system", "developer", "user", "assistant",
                }:
                    raise ValueError("invalid Responses message role")
                kind = item.get("type", "message")
                if kind == "message":
                    if set(item) - {"type", "role", "content", "id", "status", "phase"}:
                        raise ValueError("unsupported Responses message fields")
                    _text_content(item.get("content"))
                elif kind in {"function_call_output", "custom_tool_call_output"}:
                    if set(item) - {"type", "id", "call_id", "output", "status"}:
                        raise ValueError("unsupported Responses tool output fields")
                    _text_content(item.get("output"))
                elif kind in {"function_call", "custom_tool_call"}:
                    content = "arguments" if kind == "function_call" else "input"
                    if (set(item) - {"type", "id", "call_id", "name", content, "status"}
                            or not isinstance(item.get(content), str)):
                        raise ValueError("unsupported Responses tool call fields")
                elif kind == "reasoning":
                    summary = item.get("summary", [])
                    if (set(item) - {"type", "id", "summary", "encrypted_content", "status"}
                            or not isinstance(summary, list) or len(summary) > 128
                            or any(not isinstance(part, dict) or set(part) != {"type", "text"}
                                   or part["type"] != "summary_text"
                                   or not isinstance(part["text"], str) for part in summary)
                            or not isinstance(item.get("encrypted_content", ""), str)):
                        raise ValueError("unsupported Responses reasoning fields")
        else:
            raise ValueError("Responses request requires bounded input items")
        tools = body.get("tools", [])
        if (not isinstance(tools, list) or len(tools) > 128
                or any(not isinstance(tool, dict) or tool.get("type") not in {"function", "custom"}
                       for tool in tools)):
            raise ValueError("Responses hosted tools are not permitted")
        return identity, body
