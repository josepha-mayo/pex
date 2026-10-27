"""Trusted controller funding terminals only; authored IPC, no inference."""
import asyncio
import base64
import hashlib
import json
import pytest
from budget_rpc import FundingChannel,serve_budget
from controller import WorkerBudgetTerminal,run_pair
from nebius_worker import raise_funding_terminal
from test_budget_rpc import post
from test_loop import Worker,Grade,Review,arms
from worker_funding import _WorkerLedger,MODEL,PRICING_SHA,WorkerBudgetExhausted


def test_actual_ledger_refusal_retained_as_trusted_object(tmp_path):
    ledger=_WorkerLedger(tmp_path/'funding.sqlite',arm='pex',approved_config_digest='a'*64,approval_ref='AUTHORED',pricing_provenance_sha256=PRICING_SHA)
    body=json.dumps({'model':MODEL,'messages':[{'role':'user','content':'AUTHORED'}],
        'max_completion_tokens':4096,'tools':[{'type':'function','function':{'name':'pex_remote_run'}}]}).encode()
    sha=hashlib.sha256(body).hexdigest()
    try:
        ledger.reserve('first',sha,body) # retained uncertain reserve blocks next
        with serve_budget(ledger) as channel:
            status,reply=post(channel,{'operation':'reserve','call_id':'second','request_sha256':sha,'request_base64':base64.b64encode(body).decode()})
            assert status==403 and reply['category']=='WorkerBudgetExhausted'
            assert isinstance(channel.last_error,WorkerBudgetExhausted)
            with pytest.raises(WorkerBudgetTerminal) as caught:raise_funding_terminal(channel)
            assert caught.value.code=='worker_budget_reservation_refused'
            assert json.loads(json.dumps(channel))==dict(channel) # exception not serialized
    finally:ledger.close()


def test_model_text_and_generic_errors_cannot_forge_budget_terminal():
    raise_funding_terminal({'last_error':'WorkerBudgetExhausted'})
    channel=FundingChannel();channel.last_error=ValueError('worker_budget_reservation_refused')
    raise_funding_terminal(channel)


@pytest.mark.parametrize('code',['worker_budget_reservation_refused','worker_attempt_cap_refused'])
def test_controller_reports_worker_budget_as_inconclusive_not_infrastructure(code):
    class Exhausted(Worker):
        async def turn(self,*args,**kwargs):raise WorkerBudgetTerminal(code)
    worker=Exhausted()
    result=asyncio.run(run_pair(arms(),worker,Review(),Grade(worker)))
    assert all(s['status']=='worker_budget_terminal_inconclusive' and s['budget_terminal_reason']==code for s in result['arms'].values())
    assert result['pex_lift'] is None and result['presentation_eligible'] is False
    assert worker.cleaned
