"""Synthetic ledger unit tests, no HTTP, provider or VM."""
import pytest
from staged_funding import PhaseFunding
from worker_funding import WorkerBudgetExhausted


class Ledger:
    def __init__(self): self.calls=0;self.uncertain=0;self.settled=0
    def usage_snapshot(self):
        return dict(calls=self.calls,input_tokens=self.settled,output_tokens=self.settled,uncertain_calls=self.uncertain)
    def reserve(self,*a): self.calls+=1;self.uncertain+=1
    def settle_raw(self,*a): self.uncertain-=1;self.settled+=1


def use(f,n):
    for _ in range(n): f.reserve();f.settle_raw()


def test_accepted_finalization_counts_in_eight_plus_four():
    ledger=Ledger();f=PhaseFunding(ledger)
    f.begin(0);use(f,8);assert f.finish(natural_stop=True)['calls']==8
    f.begin(1);use(f,4);assert f.finish(natural_stop=True)['calls']==4
    assert ledger.calls==12
    with pytest.raises(ValueError): f.begin(2)


def test_ninth_reservation_never_reaches_underlying_ledger_or_becomes_checkpoint():
    ledger=Ledger();f=PhaseFunding(ledger);f.begin(0);use(f,8)
    with pytest.raises(WorkerBudgetExhausted): f.reserve()
    assert ledger.calls==8
    with pytest.raises(ValueError): f.finish(natural_stop=True)
    with pytest.raises(ValueError): f.begin(1)


def test_unused_first_phase_not_borrowed():
    ledger=Ledger();f=PhaseFunding(ledger);f.begin(0);use(f,1);f.finish(natural_stop=True)
    f.begin(1);use(f,4)
    with pytest.raises(WorkerBudgetExhausted): f.reserve()
    assert ledger.calls==5


def test_uncertain_charge_retained_and_no_resume():
    ledger=Ledger();f=PhaseFunding(ledger);f.begin(0);f.reserve()
    with pytest.raises(ValueError): f.finish(natural_stop=True)
    assert ledger.calls==1 and ledger.uncertain==1
    with pytest.raises(ValueError): f.begin(1)
    f.settle_raw()  # Late validated settlement is allowed, but never resumes.
    with pytest.raises(ValueError): f.begin(1)


@pytest.mark.parametrize('mode',['live-pilot','live',None])
def test_live_denied(mode):
    with pytest.raises(PermissionError): PhaseFunding(None,mode=mode)


def test_no_open_no_restart_no_skip():
    ledger=Ledger();f=PhaseFunding(ledger)
    with pytest.raises(PermissionError): f.reserve()
    with pytest.raises(ValueError): f.begin(1)
    ledger.calls=1
    with pytest.raises(ValueError): f.begin(0)


def test_global_money_refusal_is_not_overridden():
    class Empty(Ledger):
        def reserve(self,*args): raise WorkerBudgetExhausted('worker_budget_reservation_refused')
    f=PhaseFunding(Empty());f.begin(0)
    with pytest.raises(WorkerBudgetExhausted,match='worker_budget_reservation_refused'): f.reserve()
    assert f.usage_snapshot()['calls']==0
