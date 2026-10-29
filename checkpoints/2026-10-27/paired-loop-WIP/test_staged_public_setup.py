"""Authored local filesystem/process fixtures only; never VM/provider authority."""
import asyncio
import hashlib
from pathlib import Path
import subprocess
from types import SimpleNamespace
import pytest
from staged_public_setup import stage_public_files,FILES,MAX_BYTES
from staged_async_remote import BoundedAsyncRemote,BoundedRemoteError
from e2b_transport import TransportError
import time

@pytest.fixture
def setup(tmp_path):
    source=tmp_path/'source';source.mkdir();dest=tmp_path/'remote';dest.mkdir();events=[];records=[]
    for n in FILES:
        p=source/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('public '+n+'\n').encode())
    hashes={n:hashlib.sha256((source/n).read_bytes()).hexdigest() for n in FILES}
    class Remote:
        def __init__(self):self._sandbox=SimpleNamespace(files=SimpleNamespace(make_dir=self.mkdir))
        def mkdir(self,*a,**kw):events.append('mkdir')
        def write_files(self,values):
            events.append('batch')
            for n,b in values.items():
                p=dest/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
        def run(self,command):
            events.append('verify')
            result=subprocess.run(['bash','-c',command],cwd=dest,capture_output=True,text=True,timeout=10)
            return dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
    return source,dest,hashes,Remote(),events,records

def test_exact_ten_file_batch_one_readback_and_git_snapshot(setup):
    source,dest,hashes,remote,events,records=setup
    stage_public_files(remote,source,hashes,records.append)
    assert events==['mkdir','batch','verify']
    assert (dest/'.git').is_dir() and records[0]['setup_complete']
    assert records[0]['logical_attempt_count']==records[0]['logical_completed_count']==3
    assert records[0]['wire_request_count'] is None and not records[0]['setup_deadline_extended']
    assert {n:(dest/n).read_bytes() for n in FILES}=={n:(source/n).read_bytes() for n in FILES}

@pytest.mark.parametrize('damage',['symlink','changed','oversized','extra_set'])
def test_local_integrity_refuses_before_any_remote_operation(setup,damage):
    source,dest,hashes,remote,events,records=setup
    p=source/'TASK.md'
    if damage=='symlink':p.unlink();p.symlink_to(source/'README.md')
    elif damage=='changed':p.write_text('wrong')
    elif damage=='oversized':p.write_bytes(b'x'*(MAX_BYTES+1))
    else:hashes['protected/test_acceptance.py']='a'*64
    with pytest.raises(ValueError):stage_public_files(remote,source,hashes,records.append)
    assert events==[] and not records[0]['setup_complete']

@pytest.mark.parametrize('damage',['bytes','extra','symlink','hardlink'])
def test_single_remote_readback_detects_tampering(setup,damage):
    source,dest,hashes,remote,events,records=setup;write=remote.write_files
    def tamper(values):
        write(values);p=dest/'TASK.md'
        if damage=='bytes':p.write_text('wrong')
        elif damage=='extra':(dest/'unexpected').write_text('no')
        elif damage=='symlink':p.unlink();p.symlink_to(dest/'README.md')
        else:
            import os
            p.unlink();os.link(dest/'README.md',p)
    remote.write_files=tamper
    with pytest.raises(RuntimeError,match='unproven'):stage_public_files(remote,source,hashes,records.append)
    assert not records[0]['setup_complete'] and not (dest/'.git').exists()

@pytest.mark.asyncio
async def test_batch_is_one_sdk_call_and_cancellation_poison_is_preserved():
    rows=[]
    async def batch(entries,**kw):rows.append((entries,kw));return []
    remote=BoundedAsyncRemote(SimpleNamespace(files=SimpleNamespace(write_files=batch)),vm_deadline=time.monotonic()+2)
    remote.set_scope_deadline(time.monotonic()+1)
    await asyncio.to_thread(remote.write_files,{'safe/a':b'abc','safe/b':b'def'})
    assert len(rows)==1 and len(rows[0][0])==2 and rows[0][1]['user']=='user'
    with pytest.raises(TransportError):remote.write_files({'../escape':b'no'})
    with pytest.raises(ValueError):remote.write_files({'large':b'x'*(MAX_BYTES+1)})
    await remote.end_scope()
    async def wait(*a,**kw):await asyncio.Event().wait()
    remote._sdk.files.write_files=wait;remote.set_scope_deadline(time.monotonic()+.03)
    with pytest.raises(BoundedRemoteError):await asyncio.to_thread(remote.write_files,{'safe':b'bytes'})
    await remote.end_scope();assert remote.poisoned


def local_runtime(dest):
    import json
    return json.loads(subprocess.check_output(['python3','-I','-c',"import json,platform,sqlite3,os;print(json.dumps({'python_implementation':platform.python_implementation(),'python_version':platform.python_version(),'sqlite_version':sqlite3.sqlite_version,'workspace':os.getcwd()}))"],cwd=dest,text=True))

def test_runtime_probe_records_actual_matching_contract_before_worker(setup):
    source,dest,hashes,remote,events,records=setup;contract=local_runtime(dest)
    stage_public_files(remote,source,hashes,records.append,runtime_contract=contract)
    assert records[0]['setup_complete'] and records[0]['runtime_contract_verified']==contract

@pytest.mark.parametrize('field',['python_implementation','python_version','sqlite_version','workspace'])
def test_runtime_mismatch_fails_before_git_snapshot_or_worker(setup,field):
    source,dest,hashes,remote,events,records=setup;contract=local_runtime(dest);contract[field]='WRONG'
    with pytest.raises(RuntimeError,match='unproven'):stage_public_files(remote,source,hashes,records.append,runtime_contract=contract)
    assert not records[0]['setup_complete'] and records[0]['runtime_contract_verified'] is None and not (dest/'.git').exists()
