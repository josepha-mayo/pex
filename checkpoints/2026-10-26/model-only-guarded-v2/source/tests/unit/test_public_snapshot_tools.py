import hashlib
import json
import pytest
from pex_supervisor.evidence_tools import build_evidence_tools,select_evidence_tool_names,_validated_public_snapshot
from test_supervisor_loop import _request

def snapshot(files):
    entries={p:{'content':v,'sha256':hashlib.sha256(v.encode()).hexdigest()} for p,v in files.items()}
    return dict(schema='pex.public-candidate-snapshot.v1',files=entries,
        snapshot_sha256=hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest())
def setup(files=None):
    r=_request(.1);r.session.cwd=None;r.session.repo=None
    r.scores.features['public_candidate_snapshot']=snapshot(files or {'TASK.md':'Contract','stockroom/service.py':'a'*9001})
    used=[];t=next(t for t in build_evidence_tools(r,used,tool_names=["inspect_public_snapshot"]) if t.tool_name=='inspect_public_snapshot')
    return r,t,used

def test_valid_snapshot_offered_on_stop_without_workspace():
    r,t,used=setup();assert 'inspect_public_snapshot' in select_evidence_tool_names(r)
    data=json.loads(t());assert data['paths']==['TASK.md','stockroom/service.py']
    assert used==['inspect_public_snapshot'];assert data['pex_observation_id']

def test_pagination_reconstructs_complete_code_and_bound_snapshot():
    r,t,_=setup();pieces=[]
    for offset in (0,4000,8000):
        d=json.loads(t(path='stockroom/service.py',offset=offset));pieces.append(d['content'])
        assert len(d['content'])<=4000
    assert ''.join(pieces)=='a'*9001;assert d['next_offset'] is None
    r.scores.features['public_candidate_snapshot']['files']['stockroom/service.py']['content']='mutated'
    assert json.loads(t(path='stockroom/service.py'))['content']=='a'*4000

@pytest.mark.parametrize('path',['../secret','/etc/passwd','stockroom/../secret','stockroom/.env','tests//x','stockroom\\x','secret.py','tests/x\x00'])
def test_rejects_unsafe_snapshot_paths(path):
    r,t,_=setup({path:'content'});assert _validated_public_snapshot(r) is None
    assert 'inspect_public_snapshot' not in select_evidence_tool_names(r)
    assert json.loads(t())['error']=='snapshot_unavailable'

@pytest.mark.parametrize('offset',[-1,True,'0',10000])
def test_invalid_offsets(offset):
    r,t,_=setup();assert json.loads(t(path='TASK.md',offset=offset))['error']=='invalid_page'

def test_no_host_path_reads_and_no_snapshot_default():
    r,t,_=setup();assert json.loads(t(path='/etc/passwd'))['error']=='path_not_in_public_snapshot'
    r.scores.features.pop('public_candidate_snapshot');assert 'inspect_public_snapshot' not in select_evidence_tool_names(r)

@pytest.mark.parametrize('mutation',['entry','snapshot','size','count','unicode'])
def test_corrupt_and_oversized_snapshot_not_offered(mutation):
    r,_,_=setup();s=r.scores.features['public_candidate_snapshot']
    if mutation=='entry':s['files']['TASK.md']['sha256']='0'*64
    elif mutation=='snapshot':s['snapshot_sha256']='0'*64
    elif mutation=='size':r.scores.features['public_candidate_snapshot']=snapshot({'TASK.md':'a'*131073})
    elif mutation=='count':r.scores.features['public_candidate_snapshot']=snapshot({f'tests/{i}.py':'a' for i in range(129)})
    else:s['files']['TASK.md']['content']='\ud800'
    assert _validated_public_snapshot(r) is None

def test_listing_pagination_and_unicode_character_offsets():
    r,t,_=setup({**{f'tests/t{i:03}.py':'v' for i in range(17)},'TASK.md':'界'*4001})
    a=json.loads(t());b=json.loads(t(offset=a['next_offset']))
    assert len(a['paths']+b['paths'])==18;assert b['next_offset'] is None
    assert json.loads(t(path='TASK.md',offset=4000))['content']=='界'


def test_multibyte_and_escaped_content_stays_receipted_and_complete():
    text = ('界\\\n' * 2500)
    r,t,_=setup({'TASK.md':text})
    offset=0;parts=[]
    while True:
        raw=t(path='TASK.md',offset=offset);data=json.loads(raw)
        assert len(raw.encode())<=8000 and 'content' in data
        parts.append(data['content'])
        if data['next_offset'] is None:break
        assert data['next_offset']>offset
        offset=data['next_offset']
    assert ''.join(parts)==text


def test_redaction_expansion_keeps_paging_metadata_and_never_splits_secret():
    r,t,_=setup({'TASK.md':('Bearer SECRET_TOKEN ' * 500)})
    offset=0;parts=[]
    while True:
        raw=t(path='TASK.md',offset=offset);data=json.loads(raw)
        assert len(raw.encode())<=8000 and 'content' in data
        assert data['offset_basis']=='sanitized_text_characters'
        parts.append(data['content'])
        if data['next_offset'] is None:break
        assert data['next_offset']>offset
        offset=data['next_offset']
    assert 'SECRET_TOKEN' not in ''.join(parts)
    assert ''.join(parts).count('[REDACTED:bearer]')==500
