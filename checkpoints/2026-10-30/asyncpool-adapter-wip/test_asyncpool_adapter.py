"""Authored data/managed-tool composition only; never executes a worker candidate."""
import base64,json,shutil,socket
from pathlib import Path
import pytest
import asyncpool_adapter as a
ROOT=Path(__file__).resolve().parents[1]/'pex-asyncpool-benchmark-WIP-20261030'

@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('offline only')
    monkeypatch.setattr(socket,'getaddrinfo',denied);monkeypatch.setattr(socket.socket,'connect',denied)

def package():return a.load_public_package(ROOT)
def snapshot(p):return a.snapshot_from_export({'schema':'pex.asyncpool-export.v1','files':{n:base64.b64encode(v).decode() for n,v in p.files.items()}})
def request():
    p=package();check={'command':a.PUBLIC_CHECK_COMMAND,'exit_code':1,'output':'AUTHORED public test failure fixture','receipt_sha256':'a'*64}
    return a.build_monitor_request(p,{'public_sha256':p.public_sha256,'worker_identity':'authored-model'},
        {'assistant_final':'AUTHORED fixture','public_check':check,'public_diff':'AUTHORED diff','receipt_sha256':'b'*64,'public_candidate_snapshot':snapshot(p)},'authored-session')

def test_manifest_and_public_stage_exclude_reference_and_grader(tmp_path):
    p=package();out=tmp_path/'public';receipt=a.stage_public(p,out)
    assert receipt['dispatched'] is False
    assert sorted(str(f.relative_to(out)) for f in out.rglob('*') if f.is_file())==list(a.PUBLIC_FILES)
    assert all('reference' not in x and 'heldout' not in x for x in receipt['public_files'])
    with pytest.raises(ValueError):a.stage_public(p,out)

def test_manifest_mutation_and_linked_source_refused(tmp_path):
    root=tmp_path/'copy';shutil.copytree(ROOT,root)
    file=root/'public/asyncpool/__init__.py';file.write_text('changed')
    with pytest.raises(ValueError,match='frozen_package'):a.load_public_package(root)
    file.unlink();file.symlink_to(ROOT/'public/asyncpool/__init__.py')
    with pytest.raises(ValueError,match='linked_source'):a.load_public_package(root)

@pytest.mark.parametrize('path',['../heldout/test_acceptance.py','asyncpool/../x.py','/asyncpool/x.py','asyncpool//x.py','asyncpool/.hidden.py','reference/asyncpool/x.py','heldout/run_grade.py','stockroom/service.py','asyncpool\\x.py'])
def test_nonpublic_snapshot_paths_refused(path):
    p=package();s=snapshot(p);s['files'][path]={'content':'authored','sha256':a.digest(b'authored')};s['snapshot_sha256']=a.digest(a.canonical(s['files']))
    with pytest.raises(ValueError):a.validate_snapshot(s)

def test_snapshot_hash_and_spec_changes_refused():
    p=package();s=snapshot(p);s['files']['TASK.md']['content']='changed'
    with pytest.raises(ValueError):a.validate_snapshot(s)

@pytest.mark.parametrize('role',['planner','verifier'])
def test_full_managed_snapshot_protocol_selects_asyncpool(role):
    from pex_supervisor.evidence_tools import select_evidence_tool_names
    from strands_bridge import ManagedPEXModel
    from managed_chat import Route
    from pex_protocol.actions import ProposedAction,InterventionType
    req=request();assert req.session.cwd is None and req.session.repo is None
    assert 'inspect_public_snapshot' in select_evidence_tool_names(req)
    action=ProposedAction(type=InterventionType.SEND_NUDGE,session_id=req.session.id,goal_id=req.goal.id,rationale='AUTHORED',payload={'text':'AUTHORED'}) if role=='verifier' else None
    model=ManagedPEXModel(Route('https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions','nvidia/nemotron-3-super-120b-a12b',role),req,invocation_id='authored-asyncpool-'+role,proposal=action)
    assert 'inspect_public_snapshot' in {d.name for d in model.protocol.definitions}

def test_snapshot_namespaces_do_not_cross_task_identity():
    from pex_supervisor.evidence_tools import select_evidence_tool_names
    req=request();req.session.metadata={}
    assert 'inspect_public_snapshot' not in select_evidence_tool_names(req)
    req=request();s=req.scores.features['public_candidate_snapshot'];item=s['files'].pop('asyncpool/__init__.py');s['files']['stockroom/service.py']=item;s['snapshot_sha256']=a.digest(a.canonical(s['files']))
    assert 'inspect_public_snapshot' not in select_evidence_tool_names(req)
    req=request();req.session.metadata['benchmark_manifest_sha256']='0'*64
    assert 'inspect_public_snapshot' not in select_evidence_tool_names(req)

def test_grade_schema_does_not_accept_stockroom_or_inconsistent_result():
    good={'schema':'pex.asyncpool-grade.v1','checks':8,'passed':8,'failed':0,'complete':True,'all_pass':True}
    assert a.parse_grade(json.dumps(good))==good
    for change in [{'schema':'stockroom.grade.v1'},{'checks':40},{'passed':True},{'complete':False},{'failed':1}]:
        with pytest.raises(ValueError):a.parse_grade(json.dumps(good|change))

def test_dispatch_always_closed():
    assert a.APPROVED_ASYNCPOOL_RUN is None
    with pytest.raises(PermissionError):a.dispatch('anything')


def test_forged_public_package_cannot_change_staged_task(tmp_path):
    from dataclasses import replace
    p=package();files=dict(p.files);files['TASK.md']=b'forged'
    with pytest.raises(ValueError,match='exact_public_package'):a.stage_public(replace(p,files=files),tmp_path/'forged')


def test_forged_initial_prompt_refused(tmp_path):
    from dataclasses import replace
    with pytest.raises(ValueError,match='exact_public_package'):a.stage_public(replace(package(),initial_prompt='forged'),tmp_path/'forged')


def test_isolated_grader_loads_only_authored_reference_explicitly():
    import subprocess,sys
    result=subprocess.run([sys.executable,'-I',str(ROOT/'heldout/run_grade.py'),str(ROOT/'reference')],capture_output=True,text=True,timeout=10)
    assert result.returncode==0, result.stderr
    assert a.parse_grade(result.stdout)['passed']==8


def test_isolated_grader_refuses_linked_candidate_directory(tmp_path):
    import subprocess,sys
    link=tmp_path/'linked';link.symlink_to(ROOT/'reference',target_is_directory=True)
    result=subprocess.run([sys.executable,'-I',str(ROOT/'heldout/run_grade.py'),str(link)],capture_output=True,text=True,timeout=10)
    assert result.returncode!=0 and 'plain candidate directory required' in result.stderr
