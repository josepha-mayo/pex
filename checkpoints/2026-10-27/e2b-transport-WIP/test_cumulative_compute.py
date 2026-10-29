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


def test_explicit_new_approved_ceiling_fits_one_pair_without_releasing_prior(tmp_path):
    tmp_path.chmod(0o700)
    kwargs=dict(prior_upper_bound_nano_usd=49_912_500,evidence_sha256='b'*64,cap_nano_usd=120_000_000)
    b=ComputeBudget(tmp_path/'new.sqlite',**kwargs)
    b.reserve('baseline');assert b.total()==98_752_500
    b.settle_verified_allocation('baseline',cpu=2,memory_mb=512,max_seconds=330)
    b.reserve('pex');assert b.total()==108_735_000
    b.settle_verified_allocation('pex',cpu=2,memory_mb=512,max_seconds=330)
    assert b.total()==69_877_500;b.close()
    b=ComputeBudget(tmp_path/'new.sqlite',**kwargs);assert b.total()==69_877_500;b.close()
    with pytest.raises(ValueError,match='ceiling identity'):
        ComputeBudget(tmp_path/'new.sqlite',**dict(kwargs,cap_nano_usd=100_000_000))


def test_existing_legacy_compute_cap_is_not_implicitly_raised(tmp_path):
    b=budget(tmp_path);b.close()
    with pytest.raises(ValueError,match='ceiling identity'):
        ComputeBudget(tmp_path/'compute.sqlite',prior_upper_bound_nano_usd=19_965_000,
            evidence_sha256='a'*64,cap_nano_usd=120_000_000)
    b=budget(tmp_path);assert b.cap==100_000_000;b.close()


def test_future140_capability_preserves_eight_prior_full_lifetimes_and_unknowns(tmp_path):
    tmp_path.chmod(0o700)
    kwargs=dict(prior_upper_bound_nano_usd=79_860_000,evidence_sha256='c'*64,cap_nano_usd=140_000_000)
    b=ComputeBudget(tmp_path/'future.sqlite',**kwargs)
    b.reserve('baseline');assert b.total()==128_700_000
    with pytest.raises(ValueError,match='reservation refused'):b.reserve('unknown_not_refunded')
    assert b.total()==128_700_000
    b.settle_verified_allocation('baseline',cpu=2,memory_mb=512,max_seconds=330)
    b.reserve('pex');assert b.total()==138_682_500
    b.settle_verified_allocation('pex',cpu=2,memory_mb=512,max_seconds=330)
    assert b.total()==99_825_000;b.close()
    with pytest.raises(ValueError,match='ceiling identity'):
        ComputeBudget(tmp_path/'future.sqlite',**dict(kwargs,cap_nano_usd=120_000_000))


def test_future140_capability_cannot_widen_existing120_ledger(tmp_path):
    tmp_path.chmod(0o700)
    kwargs=dict(prior_upper_bound_nano_usd=49_912_500,evidence_sha256='d'*64,cap_nano_usd=120_000_000)
    b=ComputeBudget(tmp_path/'unchanged120.sqlite',**kwargs);b.reserve('uncertain');b.close()
    with pytest.raises(ValueError,match='ceiling identity'):
        ComputeBudget(tmp_path/'unchanged120.sqlite',**dict(kwargs,cap_nano_usd=140_000_000))
    b=ComputeBudget(tmp_path/'unchanged120.sqlite',**kwargs)
    assert b.cap==120_000_000 and b.total()==98_752_500;b.close()


def test_future250_capability_keeps_original06_generic_charge_and_existing_caps(tmp_path):
    tmp_path.chmod(0o700)
    kwargs=dict(prior_upper_bound_nano_usd=128_700_000,evidence_sha256='e'*64,cap_nano_usd=250_000_000)
    b=ComputeBudget(tmp_path/'future250.sqlite',**kwargs)
    b.reserve('next-baseline');assert b.total()==177_540_000
    b.settle_verified_allocation('next-baseline',cpu=2,memory_mb=512,max_seconds=330)
    b.reserve('next-pex');assert b.total()==187_522_500
    b.settle_verified_allocation('next-pex',cpu=2,memory_mb=512,max_seconds=330)
    assert b.total()==148_665_000;b.close()
    with pytest.raises(ValueError,match='ceiling identity'):
        ComputeBudget(tmp_path/'future250.sqlite',**dict(kwargs,cap_nano_usd=140_000_000))



def test_fresh500_profile_retains_prior_unknown_compute_and_cannot_reset_old250(tmp_path):
    tmp_path.chmod(0o700)
    kwargs=dict(prior_upper_bound_nano_usd=209_467_500,evidence_sha256='f'*64,cap_nano_usd=500_000_000)
    b=ComputeBudget(tmp_path/'fresh500.sqlite',**kwargs)
    b.reserve('new-baseline');assert b.total()==258_307_500
    b.settle_verified_allocation('new-baseline',cpu=2,memory_mb=512,max_seconds=330)
    b.reserve('new-pex');assert b.total()==268_290_000
    b.settle_verified_allocation('new-pex',cpu=2,memory_mb=512,max_seconds=330)
    assert b.total()==229_432_500;b.close()
    with pytest.raises(ValueError,match='predecessor compute identity'):
        ComputeBudget(tmp_path/'fresh500.sqlite',**dict(kwargs,prior_upper_bound_nano_usd=0))
    old=dict(kwargs,cap_nano_usd=250_000_000)
    b=ComputeBudget(tmp_path/'old250.sqlite',**old);b.close()
    with pytest.raises(ValueError,match='ceiling identity'):
        ComputeBudget(tmp_path/'old250.sqlite',**kwargs)


def test_fresh750_profile_exact_sequential_peak_and_immutable_old330(tmp_path):
    tmp_path.chmod(0o700)
    kwargs=dict(prior_upper_bound_nano_usd=229_432_500,evidence_sha256='a'*64,cap_nano_usd=500_000_000,vm_seconds=750)
    b=ComputeBudget(tmp_path/'new750.sqlite',**kwargs)
    assert (b.reservation,b.verified_full_lifetime)==(111_000_000,22_687_500)
    b.reserve('baseline');assert b.total()==340_432_500
    with pytest.raises(ValueError):b.settle_verified_allocation('baseline',cpu=2,memory_mb=512,max_seconds=330)
    b.settle_verified_allocation('baseline',cpu=2,memory_mb=512,max_seconds=750)
    b.reserve('pex');assert b.total()==363_120_000
    b.settle_verified_allocation('pex',cpu=2,memory_mb=512,max_seconds=750)
    assert b.total()==274_807_500;b.close()
    with pytest.raises(ValueError,match='allocation identity'):ComputeBudget(tmp_path/'new750.sqlite',**dict(kwargs,vm_seconds=330))
    b=ComputeBudget(tmp_path/'old330.sqlite',**dict(kwargs,vm_seconds=330));b.reserve('unknown');b.close()
    with pytest.raises(ValueError,match='allocation identity'):ComputeBudget(tmp_path/'old330.sqlite',**kwargs)
    b=ComputeBudget(tmp_path/'old330.sqlite',**dict(kwargs,vm_seconds=330));assert b.total()==229_432_500+RESERVATION;b.close()

def test_750_profile_unknown_is_not_discounted_and_allocation_tamper_fails(tmp_path):
    tmp_path.chmod(0o700)
    kwargs=dict(prior_upper_bound_nano_usd=229_432_500,evidence_sha256='b'*64,cap_nano_usd=500_000_000,vm_seconds=750)
    b=ComputeBudget(tmp_path/'unknown750.sqlite',**kwargs);b.reserve('unknown');b.close()
    b=ComputeBudget(tmp_path/'unknown750.sqlite',**kwargs);assert b.total()==340_432_500
    b.db.execute('UPDATE allocation SET seconds=330')
    with pytest.raises(ValueError,match='allocation changed'):b.total()
    b.close()

@pytest.mark.parametrize('seconds',[True,0,331,749,751,750.0])
def test_only_exact_reviewed_allocation_profiles(tmp_path,seconds):
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError,match='exact supported'):ComputeBudget(tmp_path/'bad.sqlite',prior_upper_bound_nano_usd=0,evidence_sha256='b'*64,vm_seconds=seconds)
