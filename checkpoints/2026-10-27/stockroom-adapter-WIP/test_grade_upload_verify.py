"""Trusted verifier with mocked exec only: no candidate code execution."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import uuid
import pytest

@pytest.fixture
def tree():
    root=Path('/tmp')/('pex-stockroom-evaluation-'+uuid.uuid4().hex);root.mkdir(mode=0o700)
    (root/'candidate').mkdir();(root/'candidate/safe.txt').write_bytes(b'AUTHORED-NONEXECUTABLE')
    yield root
    shutil.rmtree(root)

def execute(root,monkeypatch,mode='public'):
    expected={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    monkeypatch.setattr(sys,'argv',['verifier',json.dumps({'root':str(root),'mode':mode,'files':expected})])
    calls=[]
    def no_exec(binary,args):calls.append((binary,args));raise SystemExit(0)
    monkeypatch.setattr(os,'execv',no_exec)
    cwd=os.getcwd()
    try:
        with pytest.raises(SystemExit) as stop:runpy.run_path(str(Path(__file__).with_name('grade_upload_verify.py')))
        assert stop.value.code==0
    finally:os.chdir(cwd)
    return calls

def test_readback_then_unchanged_public_command(tree,monkeypatch,capsys):
    calls=execute(tree,monkeypatch)
    assert calls[0][1][1:]==['-B','-m','unittest','discover','-s','tests','-v']
    assert capsys.readouterr().out.startswith('PEX_SNAPSHOT_VERIFIED:')

def test_readback_then_all_checks_runner_unchanged(tree,monkeypatch):
    for n in ('run_grade.py','test_acceptance.py'):(tree/n).write_bytes(b'AUTHORED-NONEXECUTABLE')
    assert execute(tree,monkeypatch,'protected')[0][1][1:]==['-I','-B','run_grade.py','candidate']

@pytest.mark.parametrize('damage',['extra','symlink','hardlink','changed'])
def test_modified_snapshot_cannot_reach_exec(tree,monkeypatch,damage):
    name='candidate/safe.txt';expected={name:hashlib.sha256((tree/name).read_bytes()).hexdigest()}
    if damage=='extra':(tree/'unexpected').write_bytes(b'no')
    elif damage=='symlink':(tree/name).unlink();(tree/name).symlink_to('/dev/null')
    elif damage=='hardlink':os.link(tree/name,tree/'duplicate')
    else:(tree/name).write_bytes(b'wrong')
    monkeypatch.setattr(sys,'argv',['verifier',json.dumps({'root':str(tree),'mode':'public','files':expected})])
    monkeypatch.setattr(os,'execv',lambda *a:pytest.fail('candidate execution forbidden'))
    with pytest.raises(AssertionError):runpy.run_path(str(Path(__file__).with_name('grade_upload_verify.py')))
