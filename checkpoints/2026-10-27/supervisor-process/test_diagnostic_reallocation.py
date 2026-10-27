"""Authored ledger arithmetic only; no provider call or spending authorization."""
import copy
import pytest
from cumulative_budget import include_supervisor_diagnostics


def audit():
    return {'charged_nano_usd': {'baseline':10081800, 'pex':9382800,
                                'supervisor':246988800},
            'attempts': {'baseline':10,'pex':10,'supervisor':3}}


def test_reallocation_keeps_total_cap_equal_workers_and_all_prior_charges():
    before=audit();preserved=copy.deepcopy(before)
    result=include_supervisor_diagnostics(before,[],allocation_profile='250m-250m-500m-v2')
    assert before==preserved
    assert result['charged_nano_usd']==preserved['charged_nano_usd']
    caps={k:result['charged_nano_usd'][k]+result['remaining_nano_usd'][k]
          for k in result['charged_nano_usd']}
    assert caps=={'baseline':250000000,'pex':250000000,'supervisor':500000000}
    assert sum(caps.values())==1000000000
    assert result['remaining_total_nano_usd']==733546600
    assert min(result['remaining_nano_usd'][k] for k in ('baseline','pex'))==239918200
    assert result['remaining_attempts']=={'baseline':2,'pex':2,'supervisor':9}


def test_new_profile_does_not_refund_or_reset_an_exhausted_pool():
    value=audit();value['charged_nano_usd']['supervisor']=500000001
    with pytest.raises(ValueError,match='envelope exceeded'):
        include_supervisor_diagnostics(value,[],allocation_profile='250m-250m-500m-v2')


def test_unknown_profile_remains_refused():
    with pytest.raises(ValueError,match='unknown preregistered'):
        include_supervisor_diagnostics(audit(),[],allocation_profile='unbounded')
