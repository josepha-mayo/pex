"""Authored provider-envelope cases, not reconstructed live counters."""
import copy
import pytest
import managed_chat as mc
from test_managed_chat import VALID, no_network

def data():
    value=copy.deepcopy(VALID['usage'])
    value['prompt_tokens_details'].update(audio_tokens=None,created_cache_tokens=0,multimodal_tokens=None)
    value['completion_tokens_details'].update(audio_tokens=None,accepted_prediction_tokens=None,rejected_prediction_tokens=None)
    return value

def test_observed_field_types_with_synthetic_counts():
    out=mc._usage(data(), mc.Limits())
    assert (out.input_tokens,out.output_tokens,out.total_tokens)==(12,3,15)
    assert dict(out.input_details)=={'cached_tokens':2,'created_cache_tokens':0}
    assert dict(out.output_details)=={'reasoning_tokens':1}

@pytest.mark.parametrize('field,val',[('created_cache_tokens',1),('created_cache_tokens',True),('created_cache_tokens',-1),('created_cache_tokens','0'),('multimodal_tokens',{}),('multimodal_tokens',0),('audio_tokens',1),('unknown',None)])
def test_unsupported_or_invalid_prompt_details_refused(field,val):
    value=data();value['prompt_tokens_details'][field]=val
    with pytest.raises(mc.Refusal):mc._usage(value,mc.Limits())

@pytest.mark.parametrize('field',['prompt_tokens','completion_tokens','total_tokens'])
def test_aggregate_null_still_refused(field):
    value=data();value[field]=None
    with pytest.raises(mc.Refusal):mc._usage(value,mc.Limits())

def test_null_optional_cache_detail_does_not_override_partition():
    value=data();value['prompt_tokens_details']['cached_tokens']=None
    value.update(prompt_cache_hit_tokens=2,prompt_cache_miss_tokens=10)
    assert mc._usage(value,mc.Limits()).input_tokens==12
    value['prompt_cache_miss_tokens']=9
    with pytest.raises(mc.Refusal):mc._usage(value,mc.Limits())
