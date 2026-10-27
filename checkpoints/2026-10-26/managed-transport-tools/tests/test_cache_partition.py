"""Authored usage-parser tests, no provider traffic."""

import copy

import pytest
from test_managed_chat import VALID
from test_managed_chat import no_network as no_network

import managed_chat as mc


def data():
    value = copy.deepcopy(VALID["usage"])
    value.update(prompt_cache_hit_tokens=2, prompt_cache_miss_tokens=10)
    return value


def test_partition_preserves_full_prompt_charge_inputs():
    before = mc._usage(VALID["usage"], mc.Limits())
    after = mc._usage(data(), mc.Limits())
    assert after == before
    assert after.input_tokens == 12


@pytest.mark.parametrize(
    "change",
    [
        {"prompt_cache_hit_tokens": True},
        {"prompt_cache_hit_tokens": -1},
        {"prompt_cache_miss_tokens": 13},
        {"prompt_cache_miss_tokens": 9},
        {"prompt_cache_hit_tokens": 2.0},
        {"prompt_cache_miss_tokens": None},
        {"prompt_tokens_details": {"cached_tokens": 3}},
        {"unknown": 0},
        {"prompt_tokens_details": {"cached_tokens": True}},
    ],
)
def test_invalid_partition_refused(change):
    value = data()
    value.update(change)
    with pytest.raises(mc.Refusal):
        mc._usage(value, mc.Limits())


@pytest.mark.parametrize("name", ["prompt_cache_hit_tokens", "prompt_cache_miss_tokens"])
def test_half_partition_refused(name):
    value = data()
    del value[name]
    with pytest.raises(mc.Refusal):
        mc._usage(value, mc.Limits())


@pytest.mark.parametrize("hit,miss", [(0, 12), (12, 0), (2, 10)])
def test_aliases_without_detail_are_valid(hit, miss):
    value = data()
    del value["prompt_tokens_details"]
    value.update(prompt_cache_hit_tokens=hit, prompt_cache_miss_tokens=miss)
    assert mc._usage(value, mc.Limits()).input_tokens == 12
