"""Authored fake-remote lifecycle ordering; no actual VM/model/candidate execution."""
import asyncio,base64,json,shlex
from pathlib import Path
from types import SimpleNamespace
import pytest
import asyncpool_adapter as a
from asyncpool_grade import RemoteGrade
from asyncpool_request import collect_public_observation
from stockroom_task import digest,encoded
from test_asyncpool_adapter import ROOT,deny_network


def export():
    p=a.load_public_package(ROOT)
    return {'schema':'pex.asyncpool-export.v1','files':{n:base64.b64encode(v).decode() for n,v in p.files.items()}}

class FakeRemote:
    def __init__(self):
        self.events=[];self.files={};self.value=export();self._sandbox=SimpleNamespace(files=self)
    def write_files(self,values,**kwargs):
        self.events.append(('upload',tuple(values)));self.files.update(values)
    def run(self,command,timeout=None):
        if 'pex.asyncpool-export.v1' in command:
            self.events.append(('export',));return {'exit_code':0,'stdout':json.dumps(self.value),'stderr':''}
        if 'pex.asyncpool-upload-verified.v1' in command:
            spec=json.loads(shlex.split(command)[-1]);self.events.append(('check',spec['mode']))
            assert all(digest(self.files[spec['root']+'/'+n])==h for n,h in spec['files'].items())
            prefix='PEX_SNAPSHOT_VERIFIED:'+digest(encoded(spec['files']))+'\n'
            result='' if spec['mode']=='public' else json.dumps({'schema':'pex.asyncpool-grade.v1','checks':8,'passed':8,'failed':0,'complete':True,'all_pass':True})
            return {'exit_code':0,'stdout':prefix+result,'stderr':''}
        if command==a.PUBLIC_CHECK_COMMAND:
            self.events.append(('public-collector',));return {'exit_code':1,'stdout':'AUTHORED failing public test','stderr':''}
        self.events.append(('diff',));return {'exit_code':0,'stdout':'AUTHORED public diff','stderr':''}


def test_public_collector_uses_frozen_command_and_snapshots_only_public():
    remote=FakeRemote();saved=[]
    obs=collect_public_observation(remote,SimpleNamespace(messages=['AUTHORED'],stdout_sha256='a'*64),capture_public_snapshot=True,snapshot_sink=lambda e,s:saved.append((e,s)))
    assert remote.events==[('public-collector',),('diff',),('export',)]
    assert obs['public_check']['exit_code']==1 and len(saved)==1
    assert set(obs['public_candidate_snapshot']['files'])==set(a.PUBLIC_FILES)

@pytest.mark.asyncio
@pytest.mark.parametrize('stopped,revoked',[(False,False),(True,False),(False,True)])
async def test_grade_refuses_before_stop_and_revocation(stopped,revoked):
    remote=FakeRemote();grade=RemoteGrade({'baseline':remote},ROOT,lambda c:stopped,revoked=lambda c:revoked)
    with pytest.raises(ValueError,match='post_stop'):await grade.grade({'condition':'baseline'})
    assert remote.events==[]

@pytest.mark.asyncio
async def test_post_stop_isolated_copy_public_before_heldout_and_separate_schema():
    remote=FakeRemote();evidence=[]
    grade=RemoteGrade({'baseline':remote},ROOT,lambda c:True,revoked=lambda c:True,evidence_sink=lambda *v:evidence.append(v) or {'authored':True})
    result=await grade.grade({'condition':'baseline'})
    assert result['status']=='graded_with_limits' and result['summary']['total']==8
    assert result['schema']=='pex.asyncpool-same-vm-grade.v1'
    assert [x for x in remote.events if x[0]=='check']==[('check','public'),('check','protected')]
    uploads=[x[1] for x in remote.events if x[0]=='upload']
    assert all('/candidate/' in x for x in uploads[0])
    assert all(x.endswith(('run_grade.py','test_acceptance.py')) for x in uploads[1])
    assert all(x.startswith('/tmp/pex-asyncpool-evaluation-') for group in uploads for x in group)
    with pytest.raises(ValueError):await grade.grade({'condition':'baseline'})
    assert evidence

@pytest.mark.asyncio
async def test_modified_spec_is_not_graded():
    remote=FakeRemote();remote.value['files']['TASK.md']=base64.b64encode(b'changed').decode()
    grade=RemoteGrade({'baseline':remote},ROOT,lambda c:True,revoked=lambda c:True)
    result=await grade.grade({'condition':'baseline'})
    assert result['status']=='public_contract_changed'
    assert all(row[0]!='upload' for row in remote.events)

@pytest.mark.asyncio
async def test_saved_phase0_requires_both_workers_revoked():
    remote=FakeRemote();revoked={'baseline':False,'pex':True}
    grade=RemoteGrade({'pex':remote},ROOT,lambda c:True,revoked=lambda c:revoked[c],saved_phase0=lambda c:export())
    await grade.grade({'condition':'pex'})
    with pytest.raises(ValueError,match='all_workers_revoked'):await grade.grade_phase0({'condition':'pex'})
    revoked['baseline']=True
    result=await grade.grade_phase0({'condition':'pex'})
    assert result['status']=='graded_with_limits'
    assert sum(e[0]=='export' for e in remote.events)==1

@pytest.mark.asyncio
@pytest.mark.parametrize('outcome,code,status',[('candidate_import_failure',1,'graded_with_limits'),('grader_import_infrastructure',2,'inconclusive')])
async def test_import_failure_has_honest_zero_check_classification(outcome,code,status):
    class ImportRemote(FakeRemote):
        def run(self,command,timeout=None):
            result=super().run(command,timeout)
            if 'pex.asyncpool-upload-verified.v1' in command and json.loads(shlex.split(command)[-1])['mode']=='protected':
                prefix=result['stdout'].split('\n')[0]+'\n'
                result={'exit_code':code,'stderr':'','stdout':prefix+json.dumps({'schema':'pex.asyncpool-import-grade.v1','outcome':outcome,'checks':0,'passed':0,'failed':0,'expected_checks':8,'loader_errors':1,'complete':False,'all_pass':False})}
            return result
    remote=ImportRemote();grade=RemoteGrade({'baseline':remote},ROOT,lambda c:True,revoked=lambda c:True)
    result=await grade.grade({'condition':'baseline'})
    assert result['status']==status and result['failure_category']==outcome
    assert result['task_tests_measured'] is False and result['tests']['checks']==0
    if outcome=='candidate_import_failure':assert result['task_success'] is False
    else:assert 'task_success' not in result
