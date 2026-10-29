"""Closed worker construction validation only; no CLI launch or inference."""
import pytest
from types import SimpleNamespace
from test_staged_accounting import funded
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
from staged_worker_admission import *
from staged_funding import PhaseFunding
import nebius_worker as cw


def test_closed_worker_capability_before_any_credential():
    with pytest.raises(AdmissionRefused):validate_worker(None,{},private_root='/none',binary='/none',modules='/none',key_path='/none')

def test_authored_label_cannot_open_production_phase_mode():
    with pytest.raises(PermissionError):PhaseFunding(object(),mode='closed-admitted')


def test_wrong_paths_or_phase_mode_refused_with_synthetic_cap(funded):
    accounting,scope=funded;cfg=scope.cfg
    kwargs=dict(private_root=accounting.root/'cli',binary=cfg['cli']['binary']['path'],modules=cfg['cli']['modules_path'],key_path=cfg['nebius_key']['path'])
    funding={c:PhaseFunding(l) for c,l in accounting.workers.items()}
    with pytest.raises(AdmissionRefused,match='funding'):validate_worker(scope,funding,**kwargs)
    funding={c:PhaseFunding(l,mode='closed-admitted') for c,l in accounting.workers.items()}
    kwargs['key_path']='/unrelated/key'
    with pytest.raises(AdmissionRefused,match='paths'):validate_worker(scope,funding,**kwargs)


def test_closed_worker_refuses_authored_route_override_before_key(funded,monkeypatch):
    accounting,scope=funded;cfg=scope.cfg
    monkeypatch.setattr(cw,'BASE','http://127.0.0.1:1/v1')
    with pytest.raises(PermissionError,match='exact_route'):
        cw.NebiusCLIWorker(remotes={'baseline':None,'pex':None},private_root=accounting.root/'cli',
            binary=cfg['cli']['binary']['path'],modules=cfg['cli']['modules_path'],key_path=cfg['nebius_key']['path'],
            pool=SimpleNamespace(close=lambda:None),activate=True,
            funding={c:PhaseFunding(l,mode='closed-admitted') for c,l in accounting.workers.items()},
            task_profile='stockroom-v1',public_check_command='python -m unittest discover -s tests -v',staged_binding=scope)


@pytest.mark.parametrize('free_mib,memory_mib,allowed',[(1536,1024,True),(1535,2048,False),(2048,1023,False)])
def test_local_storage_preflight_before_resources(tmp_path,monkeypatch,free_mib,memory_mib,allowed):
    import shutil,staged_worker_admission as s
    tmp_path.chmod(0o700)
    monkeypatch.setattr(shutil,'disk_usage',lambda _:SimpleNamespace(free=free_mib*1024*1024))
    monkeypatch.setattr(s,'_available_memory_bytes',lambda:memory_mib*1024*1024)
    if allowed:assert s.storage_readiness(tmp_path)['qualification']=='sampled_soft_guard_not_hard_quota_or_exact_aggregate_bound'
    else:
        with pytest.raises(s.StorageInfrastructureLimit):s.storage_readiness(tmp_path)

def test_storage_preflight_refuses_symlink_prefix(tmp_path):
    tmp_path.chmod(0o700);target=tmp_path/'real';target.mkdir(mode=0o700);link=tmp_path/'link';link.symlink_to(target,target_is_directory=True)
    with pytest.raises(StorageInfrastructureLimit,match='unlinked'):storage_readiness(link)

def test_storage_monitor_counts_owned_files_not_external_symlink(tmp_path,monkeypatch):
    import shutil,staged_worker_admission as s
    tmp_path.chmod(0o700);(tmp_path/'owned').write_bytes(b'abc');(tmp_path/'not-owned').symlink_to('/usr')
    monkeypatch.setattr(shutil,'disk_usage',lambda _:SimpleNamespace(free=2048*1024*1024))
    monkeypatch.setattr(s,'_available_memory_bytes',lambda:2048*1024*1024)
    assert s.storage_readiness(tmp_path,running=True)['owned_regular_file_bytes']==3

@pytest.mark.asyncio
async def test_storage_monitor_cancels_only_owned_run_and_preserves_typed_failure(tmp_path,monkeypatch):
    import asyncio,staged_worker_admission as s
    closed=[]
    async def owned():
        try:await asyncio.Event().wait()
        finally:closed.append(True)
    def exhausted(*args,**kwargs):raise s.StorageInfrastructureLimit('authored exhausted')
    monkeypatch.setattr(s,'storage_readiness',exhausted)
    with pytest.raises(s.StorageInfrastructureLimit,match='authored exhausted'):
        await s.run_with_storage_monitor(owned(),tmp_path,interval=.001)
    assert closed==[True]

@pytest.mark.asyncio
async def test_storage_monitor_returns_real_run_result(tmp_path):
    async def owned():return {'actual':'authored result'}
    assert await run_with_storage_monitor(owned(),tmp_path)=={'actual':'authored result'}
