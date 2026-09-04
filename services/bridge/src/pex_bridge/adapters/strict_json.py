"""Strict JSON helpers for adapter-controlled protocol boundaries."""

from __future__ import annotations

import json
import math
from typing import Any


def strict_json_loads(value: str | bytes | bytearray) -> Any:
    """Decode RFC JSON while rejecting duplicate keys and non-finite numbers."""

    return json.loads(
        value,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )


def strict_json_dumps(value: Any, **kwargs: Any) -> str:
    """Encode interoperable JSON; Python's NaN/Infinity extension is forbidden."""

    return json.dumps(value, allow_nan=False, **kwargs)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is forbidden: {value}")


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("non-finite JSON number is forbidden")
    return parsed
