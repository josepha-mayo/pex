"""Closed production composition construction only; no CLI/model/VM execution."""
import pytest
import json
import os
import stat
from dataclasses import replace
from test_staged_accounting import funded
from test_staged_sdk_binding import bound
from test_staged_admission import candidate
from staged_composition import *
from staged_controller import run_staged_pair


def test_build_closed_before_everything():
    with pytest.raises(AdmissionRefused):build_composition(None)


def test_private_atomic_publication_is_complete_exclusive_private(tmp_path):
    tmp_path.chmod(0o700);target=tmp_path/'actual.json'
    pin=private_atomic_json(target,{'actual':'observed'})
    assert json.loads(target.read_bytes())=={'actual':'observed'}
    assert pin['sha256']==sha(target.read_bytes()) and stat.S_IMODE(target.stat().st_mode)==0o600
    assert target.stat().st_nlink==1 and not list(tmp_path.glob('*.pending-*'))
    with pytest.raises(FileExistsError):private_atomic_json(target,{'replacement':'forbidden'})
    assert json.loads(target.read_bytes())=={'actual':'observed'}


def test_private_atomic_failure_never_publishes_partial(tmp_path,monkeypatch):
    tmp_path.chmod(0o700);target=tmp_path/'absent.json'
    def failed(_):raise OSError('AUTHORED fsync failure')
    monkeypatch.setattr(os,'fsync',failed)
    with pytest.raises(OSError):private_atomic_json(target,{'actual':'not durable'})
    assert not target.exists() and not list(tmp_path.iterdir())


def test_private_atomic_bound_and_nonprivate_parent_refused(tmp_path):
    tmp_path.chmod(0o700)
    with pytest.raises(ValueError):private_atomic_json(tmp_path/'too-large.json',{'x':'long'},limit=1)
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError):private_atomic_json(tmp_path/'public.json',{})

@pytest.mark.asyncio
async def test_explicit_run_requires_sealed_owned_composition():
    with pytest.raises(AdmissionRefused):await run_composition(None)
    with pytest.raises(PermissionError):await run_staged_pair({},None,None,None,mode='closed-admitted')

@pytest.mark.parametrize('bound',['composition'],indirect=True)
def test_production_shape_build_has_no_provider_or_VM_effect(funded,bound):
    accounting,scope=funded;_,_,wire,pools,behavior=bound
    composition=build_composition(accounting)
    try:
        composition.verify(composition.arms,composition.worker,composition.review,composition.grader)
        assert composition.worker.mode=='closed-admitted'
        assert all(f.mode=='closed-admitted' for f in composition.worker.worker.funding.values())
        assert not wire and not pools and not scope.creates
        assert accounting.summary()['supervisor_wire_attempts']==0
        assert (accounting.root/'frozen-staged-inputs.json').is_file()
        assert not (accounting.root/'report.json').exists()
    finally:composition.supervisor.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('bound',['composition'],indirect=True)
async def test_authored_entry_cannot_mislabel_admitted_worker(funded):
    accounting,scope=funded;composition=build_composition(accounting)
    try:
        with pytest.raises(PermissionError):
            await run_staged_pair(composition.arms,composition.worker,composition.review,composition.grader)
        forged=replace(composition,seal=object())
        with pytest.raises(AdmissionRefused):await run_composition(forged)
    finally:composition.supervisor.close()

@pytest.mark.parametrize('bound',['composition'],indirect=True)
def test_mutated_arms_refused_before_setup(funded,bound):
    accounting,scope=funded;composition=build_composition(accounting)
    try:
        composition.arms['pex']['prompt']='altered'
        with pytest.raises(AdmissionRefused):composition.verify(composition.arms,composition.worker,composition.review,composition.grader)
        assert not bound[2]
    finally:composition.supervisor.close()
