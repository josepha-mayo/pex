import pytest
from cumulative_compute import ComputeBudget,RESERVATION
from e2b_transport import PilotPool,TransportError
from test_transport import Api

def budget(tmp_path,prior=19965000):
    tmp_path.chmod(0o700)
    return ComputeBudget(tmp_path/'compute.sqlite',prior_upper_bound_nano_usd=prior,evidence_sha256='a'*64)

def test_two_successors_fit_only_after_verified_allocation(tmp_path):
    b=budget(tmp_path);api=Api();p=PilotPool(api,'synthetic',approved=True,cumulative_budget=b)
    p.create('baseline');assert b.total()==29947500
    p.create('supervised');assert b.total()==39930000
    p.close();b.close()
    b=budget(tmp_path);assert b.total()==39930000;b.close()

def test_uncertain_never_released_and_new_pool_cannot_reset(tmp_path):
    b=budget(tmp_path);api=Api();api.failure=True
    with pytest.raises(TransportError):PilotPool(api,'synthetic',approved=True,cumulative_budget=b).create('baseline')
    assert b.total()==19965000+RESERVATION
    with pytest.raises(ValueError,match='reservation refused'):PilotPool(api,'synthetic',approved=True,cumulative_budget=b).create('baseline')
    assert len(api.calls)==1;b.close()

def test_unverified_allocation_retains_reservation(tmp_path):
    b=budget(tmp_path);api=Api();api.alloc=(2,1024,330)
    with pytest.raises(TransportError):PilotPool(api,'synthetic',approved=True,cumulative_budget=b).create('baseline')
    assert b.total()==19965000+RESERVATION;b.close()

def test_changed_prior_does_not_reset(tmp_path):
    b=budget(tmp_path);b.close()
    with pytest.raises(ValueError,match='identity changed'):budget(tmp_path,0)

def test_settlement_requires_exact_once_reserved_identity(tmp_path):
    b=budget(tmp_path)
    with pytest.raises(ValueError):b.settle_verified_allocation('missing',cpu=2,memory_mb=512,max_seconds=330)
    b.reserve('one')
    with pytest.raises(ValueError):b.settle_verified_allocation('one',cpu=2,memory_mb=512,max_seconds=1)
    b.settle_verified_allocation('one',cpu=2,memory_mb=512,max_seconds=330)
    with pytest.raises(ValueError):b.settle_verified_allocation('one',cpu=2,memory_mb=512,max_seconds=330)
    b.close()
