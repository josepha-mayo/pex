"""Synthetic authored arithmetic only; no runtime accounting or resource calls."""
from dataclasses import FrozenInstanceError
import pytest
from staged_envelope import *


def test_equal_fixed_phases_cannot_mutate_or_roll_over():
    assert PHASES == (Phase(8,32768,120), Phase(4,16384,60))
    assert TOTAL == Phase(12,49152,180)
    with pytest.raises(FrozenInstanceError): PHASES[0].calls=9


def test_lifetime_counts_setup_and_review_pause():
    life=Lifetime(100)
    assert life.deadline==430
    assert life.allowance(120,120,retain=190)==120
    assert life.allowance(310,60,retain=60)==60
    # Even if active worker time is only120, a long review cannot reset330.
    with pytest.raises(WallBudgetExhausted): life.allowance(311,60,retain=60)
    assert life.deadline==430


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
    assert SETUP_SECONDS==40 and GRADE_SECONDS==25 and GRADE_MAX_SECONDS==45
    assert sum((SETUP_SECONDS,TOTAL.active_seconds,OBSERVATION_SECONDS,REVIEW_SECONDS,GRADE_SECONDS,CLEANUP_SECONDS))==330
    life=Lifetime(0)
    assert grade_allowance(life,290,15)==25
    assert grade_allowance(life,270,15)==45
    assert grade_allowance(life,200,15)==45
    with pytest.raises(WallBudgetExhausted):grade_allowance(life,291,15)
    assert grade_allowance(life,293,12)==25  # Stop already used3s of SAME cleanup15.
