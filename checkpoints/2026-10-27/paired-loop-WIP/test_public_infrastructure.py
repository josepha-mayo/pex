"""Authored remote-result boundaries; no CLI, provider or VM execution."""
import asyncio
from dataclasses import dataclass
import importlib
import json
import sqlite3
import pytest
from controller import PublicEvidenceInfrastructureError,run_pair
from public_request import build_public_request
from test_loop import Worker,Grade,Review,arms

@dataclass
class Receipt:
    session_id:str='authored-session'
    stdout_sha256:str='a'*64
    messages:tuple=('Authored final',)

@pytest.mark.parametrize('public_command',['python -m unittest discover -s tests -p test_smoke.py','python -m unittest discover -s tests -v'])
@pytest.mark.parametrize('module_name',['cli_worker','nebius_worker'])
@pytest.mark.parametrize('smoke,diff,expected',[(0,0,'supported'),(1,0,'contradicted'),(127,0,None),(124,0,None),(0,128,None)])
def test_worker_public_exit_boundaries(monkeypatch,tmp_path,module_name,smoke,diff,expected,public_command):
    module=importlib.import_module(module_name)
    cls=module.CLIWorker if module_name=='cli_worker' else module.NebiusCLIWorker
    worker=object.__new__(cls)
    if module_name=='nebius_worker':worker.public_check_command=public_command
    profile=tmp_path/'profile';(profile/'data/opencode').mkdir(parents=True)
    db=profile/'data/opencode/opencode.db';conn=sqlite3.connect(db)
    conn.execute('create table session_message(session_id text,seq int,type text,data text)')
    provider='opencode' if module_name=='cli_worker' else 'nebius'
    conn.execute('insert into session_message values(?,?,?,?)',('authored-session',1,'assistant',json.dumps({'model':{'providerID':provider,'id':module.MODEL},'tokens':{'input':1,'output':1,'reasoning':0,'cache':{'read':0,'write':0}}})));conn.commit();conn.close()
    worker.states={'pex':{'profile':profile,'case':profile,'stopped':False,'seq':0}}
    worker._start=lambda condition:None
    worker.binary=tmp_path/'never-executed'
    class Remote:
        def run(self,command):return {'exit_code':smoke if command.startswith('python ') else diff,'stdout':'Authored evidence','stderr':''}
    worker.remotes={'pex':Remote()}
    monkeypatch.setattr(module,'prior_sequence',lambda *a:0)
    async def fake_turn(**kwargs):return Receipt()
    monkeypatch.setattr(module,'run_turn',fake_turn)
    arm={'condition':'pex','public_sha256':'b'*64,'worker_identity':provider+'/'+module.MODEL,'prompt':'Authored public task'}
    def turn():return asyncio.run(worker.turn(arm,prompt=arm['prompt'],session_id=None,remaining={'active_seconds':1}))
    if expected is None:
        with pytest.raises(PublicEvidenceInfrastructureError):turn()
    else:
        result=turn()
        if module_name=='nebius_worker':
            assert result['public_observation']['public_check']['command']==public_command
            if public_command.endswith('-v'):return
        req=build_public_request(arm,result['public_observation'],result['session_id'])
        assert req.scores.features['verification']['status']==expected
        assert req.scores.features['verification']['acceptance_status']=='uncertain'

@pytest.mark.parametrize('code',[124,127,-9])
def test_public_request_rejects_non_test_terminal(code):
    observation={'assistant_final':'Authored','public_diff':'','receipt_sha256':'a'*64,
      'public_check':{'command':'python -m unittest discover -s tests -p test_smoke.py','exit_code':code,'output':'Authored','receipt_sha256':'b'*64}}
    with pytest.raises(PublicEvidenceInfrastructureError):build_public_request({},observation,'session')

def test_infrastructure_inconclusive_is_never_graded_or_goal_contradiction():
    class Broken(Worker):
        async def turn(self,*a,**kw):raise PublicEvidenceInfrastructureError('public_diff_failed')
    worker=Broken();result=asyncio.run(run_pair(arms(),worker,Review(),Grade(worker)))
    assert all(s['status']=='infrastructure_inconclusive' and 'protected_grade' not in s for s in result['arms'].values())
    assert result['pex_lift'] is None and worker.cleaned
