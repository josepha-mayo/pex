"""Authored offline diagnostic-pool tests; no provider calls."""
import pytest
from accounting import Ledger,PilotBudgetExhausted
from pilot_process import pilot_routes

def make(path,prior=2809730700,budget=3159730700):
 routes=pilot_routes()
 return Ledger(path,budget=budget,input_rate=300,output_rate=900,route=routes[0],currency='USD',pricing_provenance_sha256='a'*64,
  input_token_bound=262144,output_token_bound=4096,approved_routes=routes,max_attempts=12,prior_charged_nano_usd=prior,predecessor_sha256='b'*64)

def test_all_prior_once_and_uncertain_fresh_reservations_retained_on_reopen(tmp_path):
 p=tmp_path/'diagnostic.sqlite';ledger=make(p);route=pilot_routes()[0]
 assert ledger._validate_stored()==2809730700
 for n in range(4):ledger.reserve('unknown-'+str(n),route)
 assert ledger._validate_stored()==2809730700+4*82329600
 with pytest.raises(PilotBudgetExhausted):ledger.reserve('fifth',route)
 ledger.close();ledger=make(p)
 assert ledger._validate_stored()==2809730700+4*82329600
 assert len(ledger.summary())==4
 with pytest.raises(PilotBudgetExhausted):ledger.reserve('fifth',route)
 ledger.close()

@pytest.mark.parametrize('prior',[0,659514900,2809730699,2809730701])
def test_exact_history_cannot_be_reset_or_relabelled(tmp_path,prior):
 with pytest.raises(ValueError,match='exact retrospective provider predecessor'):make(tmp_path/'bad.sqlite',prior=prior)

def test_new_profile_does_not_open_arbitrary_pools(tmp_path):
 with pytest.raises(ValueError,match='shared pilot'):make(tmp_path/'bad.sqlite',budget=3159730701)
