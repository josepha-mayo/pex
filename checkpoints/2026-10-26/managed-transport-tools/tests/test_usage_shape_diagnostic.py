"""Schema diagnostics only; mocked response bodies, no real provider calls."""

import copy
import json
from dataclasses import asdict

import pytest
from test_managed_chat import SYNTHETIC_KEY, VALID, candidate, response, run
from test_managed_chat import no_network as no_network
from test_managed_chat import rig as rig

import managed_chat as mc


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "usage",
    [
        None,
        [],
        {"prompt_tokens": 4},
        {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15, "extra": None},
        {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15, "extra": 1},
    ],
)
async def test_refusal_preserves_schema_without_accepting_unknown_usage(rig, usage):
    payload = copy.deepcopy(VALID)
    payload["usage"] = usage
    rig.handler = lambda _: response(payload)
    out = await run(candidate())
    assert out.receipt.reason == "invalid_usage_shape"
    assert out.receipt.outcome == "uncertain" and out.receipt.usage is None
    assert out.receipt.http_status == 200 and len(rig.calls) == 1
    assert out.receipt.usage_shape[0][0] == "$type"


@pytest.mark.asyncio
async def test_schema_diagnostic_does_not_retain_values_or_nested_content(rig):
    payload = copy.deepcopy(VALID)
    payload["usage"]["extra"] = {"private_value": "DO_NOT_RETAIN_RESPONSE_VALUE"}
    rig.handler = lambda _: response(payload)
    out = await run(candidate())
    assert ("extra", "dict") in out.receipt.usage_shape
    assert "DO_NOT_RETAIN_RESPONSE_VALUE" not in json.dumps(asdict(out.receipt))
    assert "private_value" not in json.dumps(asdict(out.receipt))


@pytest.mark.parametrize("raw", [{SYNTHETIC_KEY: None}, {"extra": SYNTHETIC_KEY}, [SYNTHETIC_KEY]])
def test_secret_bearing_usage_is_fully_redacted(raw):
    assert mc._usage_shape(raw, SYNTHETIC_KEY) == (("$type", "redacted"),)


def test_schema_names_and_size_are_bounded():
    out = mc._usage_shape({"user@example.com": None, "x" * 1000: 1}, SYNTHETIC_KEY)
    assert out == (("$type", "dict"), ("<noncanonical>", "null"), ("<noncanonical>", "int"))
    assert mc._usage_shape({str(i): i for i in range(33)}, SYNTHETIC_KEY) == (
        ("$type", "dict"),
        ("$fields", "outside_diagnostic_bound"),
    )


@pytest.mark.asyncio
async def test_valid_usage_and_settlement_contract_are_unchanged(rig):
    out = await run(candidate())
    assert out.receipt.outcome == "succeeded"
    assert out.receipt.usage.total_tokens == 15
    assert ("prompt_tokens", "int") in out.receipt.usage_shape
    assert SYNTHETIC_KEY not in json.dumps(asdict(out.receipt))


def test_detail_schema_names_only_and_no_deep_recursion():
    raw = {
        "prompt_tokens_details": {
            "cached_tokens": 111,
            "new_counter": 222,
            "nested": {"never_emit_this": "private"},
        },
        "completion_tokens_details": {"reasoning_tokens": 333},
    }
    out = mc._usage_shape(raw, SYNTHETIC_KEY)
    assert ("prompt_tokens_details.new_counter", "int") in out
    assert ("prompt_tokens_details.nested", "dict") in out
    assert "111" not in repr(out) and "222" not in repr(out)
    assert "never_emit_this" not in repr(out) and "private" not in repr(out)


def test_nested_schema_bounds_and_noncanonical_names():
    out = mc._usage_shape({"prompt_tokens_details": {"x" * 1000: 2}}, SYNTHETIC_KEY)
    assert ("prompt_tokens_details.<noncanonical>", "int") in out
    out = mc._usage_shape(
        {"completion_tokens_details": {str(i): i for i in range(33)}}, SYNTHETIC_KEY
    )
    assert ("completion_tokens_details.$fields", "outside_diagnostic_bound") in out


def test_nested_secret_still_redacts_whole_schema():
    assert mc._usage_shape(
        {"prompt_tokens_details": {"cached_tokens": SYNTHETIC_KEY}}, SYNTHETIC_KEY
    ) == (("$type", "redacted"),)
