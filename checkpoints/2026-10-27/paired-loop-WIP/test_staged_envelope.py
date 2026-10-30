"""Synthetic authored arithmetic only; no runtime accounting or resource calls."""
from dataclasses import FrozenInstanceError
import pytest
from staged_envelope import *


def test_equal_fixed_phases_cannot_mutate_or_roll_over():
    assert PHASES == (Phase(8,131072,360), Phase(4,65536,180))
    assert TOTAL == Phase(12,196608,540)
    with pytest.raises(FrozenInstanceError): PHASES[0].calls=9


def test_lifetime_counts_setup_and_review_pause():
    life=Lifetime(100)
    assert life.deadline==850
    assert life.allowance(160,360,retain=330)==360
    assert life.allowance(610,180,retain=60)==180
    # Even if active worker time is only360, a long review cannot reset750.
    with pytest.raises(WallBudgetExhausted): life.allowance(611,180,retain=60)
    assert life.deadline==850


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,True,'1'])
def test_bad_clocks(value):
    with pytest.raises(ValueError): Lifetime(value)


def synthetic(**changes):
    args=dict(prior_provider=50,equal_worker_fresh=20,supervisor_fresh=9,
              provider_ceiling=100,prior_compute=30,verified_vm_bound=10,
              uncertain_create_reserve=50,compute_ceiling=100)
    args.update(changes)
    return reservation_envelope(**args)


def test_full_lifetime_and_unknown_create_counted_sequentially():
    assert synthetic()==dict(provider_reserved_ceiling=99,compute_sequential_peak=90,
        compute_final_lifetime_bound=50,paused_VM_seconds_discounted=False)


@pytest.mark.parametrize('change',[dict(prior_provider=52),dict(prior_compute=41),
    dict(uncertain_create_reserve=9),dict(equal_worker_fresh=0),dict(prior_provider=True)])
def test_ceiling_fail_closed(change):
    with pytest.raises(ValueError): synthetic(**change)


def test_frozen_partition_and_grade_only_borrows_actual_unused_wall():
    assert SETUP_SECONDS==60 and GRADE_SECONDS==30 and GRADE_MAX_SECONDS==60
    assert sum((SETUP_SECONDS,TOTAL.active_seconds,OBSERVATION_SECONDS,REVIEW_SECONDS,GRADE_SECONDS,CLEANUP_SECONDS))==750
    life=Lifetime(0)
    assert grade_allowance(life,700,20)==30
    assert grade_allowance(life,670,20)==60
    assert grade_allowance(life,600,20)==60
    with pytest.raises(WallBudgetExhausted):grade_allowance(life,701,20)
    assert grade_allowance(life,703,17)==30  # Stop already used3s of SAME cleanup20.

@pytest.mark.parametrize('now,expected',[(0,60),(370,60),(410,20),(420,10)])
def test_observation_borrows_only_unused_wall_with_full_future_reserve(now,expected):
    life=Lifetime(0)
    assert observation_allowance(life.deadline,now)==expected
    assert life.deadline==750
    assert now+expected+90+180+30+20<=life.deadline

@pytest.mark.parametrize('now',[420.001,500,750])
def test_observation_refuses_exhausted_remaining_wall(now):
    with pytest.raises(WallBudgetExhausted):observation_allowance(750,now)
