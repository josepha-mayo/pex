"""Mocked optional-null schema tests; nonnull legacy calls remain unsupported."""

import copy
import json

import pytest
from test_managed_chat import VALID, candidate, response, run
from test_managed_chat import no_network as no_network
from test_managed_chat import rig as rig


@pytest.mark.asyncio
async def test_text_accepts_absent_legacy_call_as_null(rig):
    data = copy.deepcopy(VALID)
    data["choices"][0]["message"]["function_call"] = None
    rig.handler = lambda _: response(data)
    assert (await run(candidate())).receipt.outcome == "succeeded"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [{}, [], False, "", {"name": "x", "arguments": "{}"}])
async def test_text_rejects_every_nonnull_legacy_call(rig, legacy):
    data = copy.deepcopy(VALID)
    data["choices"][0]["message"]["function_call"] = legacy
    rig.handler = lambda _: response(data)
    assert (await run(candidate())).receipt.reason == "unsupported_response_message"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [None, {}, False])
async def test_tool_path_only_accepts_null_legacy_placeholder(rig, legacy):
    from test_tool_transport import final_arguments, payload, setup
    from test_tool_transport import run as run_tool

    bound, c, invocation = setup()
    data = payload(bound.contract.final_name, json.dumps(final_arguments("planner")))
    data["choices"][0]["message"]["function_call"] = legacy
    rig.handler = lambda _: response(data)
    out = await run_tool(c, invocation)
    if legacy is None:
        assert out.receipt.outcome == "succeeded"
    else:
        assert out.receipt.reason == "unsupported_response_message"
