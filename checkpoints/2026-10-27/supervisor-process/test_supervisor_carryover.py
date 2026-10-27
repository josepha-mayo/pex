import pytest
from accounting import Ledger,PilotBudgetExhausted
from pilot_process import pilot_routes

def ledger(path,prior=164659200,digest='a'*64):
    routes=pilot_routes()
    return Ledger(path,budget=250000000,input_rate=300,output_rate=900,route=routes[0],currency='USD',pricing_provenance_sha256='b'*64,input_token_bound=262144,output_token_bound=4096,approved_routes=routes,max_attempts=12,prior_charged_nano_usd=prior,predecessor_sha256=digest)

def test_cumulative_quarter_dollar_retains_prior_and_uncertain(tmp_path):
    p=tmp_path/'new.sqlite';db=ledger(p);routes=pilot_routes()
    db.reserve('one',routes[0])
    with pytest.raises(PilotBudgetExhausted,match='budget reservation'):
        db.reserve('two',routes[1])
    db.close()
    db=ledger(p)
    with pytest.raises(PilotBudgetExhausted):db.reserve('two',routes[1])
    db.close()
    with pytest.raises(ValueError,match='predecessor identity'):
        ledger(p,0,None)

def test_missing_prior_pin_refused(tmp_path):
    with pytest.raises(ValueError,match='pinned prior'):
        ledger(tmp_path/'new.sqlite',1,None)


def test_successor_300m_pool_preserves_prior_uncertainty(tmp_path):
    routes=pilot_routes()
    db=Ledger(tmp_path/'successor.sqlite',budget=300000000,input_rate=300,output_rate=900,route=routes[0],currency='USD',pricing_provenance_sha256='b'*64,input_token_bound=262144,output_token_bound=4096,approved_routes=routes,max_attempts=12,prior_charged_nano_usd=164659200,predecessor_sha256='a'*64)
    db.reserve('one',routes[0])
    assert db._validate_stored()==246988800
    with pytest.raises(PilotBudgetExhausted):db.reserve('two-uncertain',routes[1])
    db.close()
