"""Fail-closed SDK accounting checks for the opt-in model-only decision policy.

This validates the documented Strands metrics shape, not provider billing or
hidden SDK/transport retries. Unsupported or incomplete shapes are rejected.
"""

from __future__ import annotations

from typing import Any

_MAX_TOKENS = 1_000_000_000_000
_MAX_CYCLES = 64


def _usage(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, dict):
        return None
    keys = ("inputTokens", "outputTokens", "totalTokens")
    if not all(key in value for key in keys):
        return None
    if set(value) - {*keys, "cacheReadInputTokens", "cacheWriteInputTokens"}:
        return None
    # Validate every present counter, including cache counters. No bool/string/
    # float coercion and no zero substitution for missing per-cycle receipts.
    if any(type(count) is not int or not 0 <= count <= _MAX_TOKENS for count in value.values()):
        return None
    input_tokens, output_tokens, total_tokens = (value[key] for key in keys)
    if total_tokens != input_tokens + output_tokens:
        return None
    return input_tokens, output_tokens, total_tokens


def _full_usage(value: Any) -> tuple[int, ...] | None:
    counts = _usage(value)
    if counts is None:
        return None
    return (*counts, value.get("cacheReadInputTokens", 0), value.get("cacheWriteInputTokens", 0))


def validated_sdk_usage(result: object) -> tuple[int, int, int] | None:
    """Return (cycles, input, output) only for complete, consistent SDK-observed metrics."""
    try:
        metrics = getattr(result, "metrics", None)
        invocations = getattr(metrics, "agent_invocations", None)
        if not isinstance(invocations, (list, tuple)) or not 1 <= len(invocations) <= _MAX_CYCLES:
            return None
        totals = [0, 0, 0, 0, 0]
        cycle_count = 0
        for invocation in invocations:
            cycles = getattr(invocation, "cycles", None)
            if not isinstance(cycles, (list, tuple)) or not cycles:
                return None
            subtotal = [0, 0, 0, 0, 0]
            for cycle in cycles:
                cycle_count += 1
                if cycle_count > _MAX_CYCLES:
                    return None
                usage = _full_usage(getattr(cycle, "usage", None))
                if usage is None or usage[0] <= 0 or usage[1] <= 0:
                    return None
                subtotal = [left + right for left, right in zip(subtotal, usage, strict=True)]
            if _full_usage(getattr(invocation, "usage", None)) != tuple(subtotal):
                return None
            totals = [left + right for left, right in zip(totals, subtotal, strict=True)]
        if any(count > _MAX_TOKENS for count in totals):
            return None
        if _full_usage(getattr(metrics, "accumulated_usage", None)) != tuple(totals):
            return None
        reported_cycles = getattr(metrics, "cycle_count", None)
        if type(reported_cycles) is not int or reported_cycles != cycle_count:
            return None
        # Some SDK versions expose the same counters on AgentResult too. If
        # present, they must agree; never choose the more convenient aggregate.
        for name in ("accumulated_usage", "usage"):
            reported = getattr(result, name, None)
            if reported is not None and _full_usage(reported) != tuple(totals):
                return None
        return cycle_count, totals[0], totals[1]
    except (AttributeError, TypeError, ValueError, OverflowError):
        return None
