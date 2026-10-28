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
