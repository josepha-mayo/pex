"""AUTHORED closed-grant integration; actual SDK serialization only uses mocks."""
import json
from pathlib import Path
import pytest
from test_staged_admission import candidate
from test_staged_sdk_binding import bound
from test_staged_accounting import funded
import staged_admission as admission
from staged_composition import build_composition,source_pins
from asyncpool_adapter import MANIFEST_SHA256,PUBLIC_SHA256
import asyncpool_history as history


def test_new_task_gate_default_closed_before_any_read(monkeypatch):
    monkeypatch.setattr(admission,'APPROVED_ASYNCPOOL_GRANT',None)
    assert admission.APPROVED_ASYNCPOOL_GRANT is None
    grant=admission.Grant('AUTHORED','asyncpool-staged-pair-authored','/absent/pair.json',*(['a'*64]*5),'2099-01-01T00:00:00+00:00')
    monkeypatch.setattr(admission,'read_pin',lambda *a,**k:pytest.fail('closed gate must precede reads'))
    with pytest.raises(admission.AdmissionRefused,match='approval_pending'):admission.load(grant)


@pytest.mark.parametrize('bound',['composition-asyncpool'],indirect=True)
def test_exact_asyncpool_composition_same_science_no_external_effect(funded,bound):
    accounting,scope=funded;composition=build_composition(accounting)
    try:
        composition.verify(composition.arms,composition.worker,composition.review,composition.grader)
        assert accounting.cfg['task']['sha256']==MANIFEST_SHA256
        assert composition.worker.worker.task_profile=='asyncpool-v1'
        assert composition.worker.lifecycle.evaluation_task=='asyncpool'
        assert composition.grader.grade_impl.task=='asyncpool_v1_cancel_safe_dual_limit'
        assert composition.grader.grade_impl.check_count==8
        assert composition.supervisor.config['public_sha256']==PUBLIC_SHA256
        assert 'Pool' in composition.supervisor.objective and 'Stockroom' not in composition.supervisor.objective
        assert accounting.prior==history.PRIOR_PROVIDER
        assert scope.compute.total()==history.PRIOR_COMPUTE
        assert not bound[2] and not bound[3] and not scope.creates
        assert accounting.summary()['supervisor_wire_attempts']==0
        assert all(a['public_sha256']==PUBLIC_SHA256 for a in composition.arms.values())
        for arm in ('baseline','pex'):
            root=accounting.root/'staged/workers'/arm
            assert {str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}=={'TASK.md','README.md','asyncpool/__init__.py','tests/test_public.py'}
        assert set(source_pins())>=set(('asyncpool_history','asyncpool_adapter','asyncpool_integration','asyncpool_setup','asyncpool_request','asyncpool_grade','asyncpool_export_candidate','asyncpool_grade_upload_verify','asyncpool_public_diff'))
    finally:composition.supervisor.close()

@pytest.mark.parametrize('bound',['composition-asyncpool'],indirect=True)
def test_actual_composed_planner_and_verifier_accept_exact_new_task(funded,bound):
    from test_asyncpool_adapter import package,snapshot
    from asyncpool_adapter import PUBLIC_CHECK_COMMAND
    from pex_protocol.actions import ProposedAction,InterventionType
    accounting,scope=funded;composition=build_composition(accounting)
    try:
        observation={'assistant_final':'AUTHORED fixture only','public_check':{'command':PUBLIC_CHECK_COMMAND,'exit_code':1,'output':'AUTHORED','receipt_sha256':'a'*64},'public_diff':'AUTHORED','receipt_sha256':'b'*64,'public_candidate_snapshot':snapshot(package())}
        request=composition.review.request_builder(composition.arms['pex'],observation,'authored-worker-session')
        assert request.goal.objective==composition.supervisor.objective
        main=composition.supervisor.model_factory('planner',request,None)
        proposal=ProposedAction(type=InterventionType.SEND_NUDGE,session_id=request.session.id,goal_id=request.goal.id,rationale='AUTHORED',payload={'text':'AUTHORED'})
        verifier=composition.supervisor.model_factory('verifier',request,proposal)
        for model in (main,verifier):assert 'inspect_public_snapshot' in {d.name for d in model.protocol.definitions}
        assert not bound[2] and not bound[3] and accounting.summary()['supervisor_wire_attempts']==0
    finally:composition.supervisor.close()


@pytest.mark.parametrize('change',['prefix','legacy_manifest','missing_prior','changed_prior'])
def test_new_task_identity_and_retained_history_are_mandatory(candidate,change):
    cfg,freeze=candidate
    task=Path(__file__).resolve().parents[1]/'pex-asyncpool-benchmark-WIP-20261030/MANIFEST.json'
    cfg['task']={'path':str(task),'sha256':MANIFEST_SHA256};cfg['run_id']='asyncpool-staged-pair-authored'
    cfg['profile']['compute_cap']=history.COMPUTE_ENVELOPE
    if change=='prefix':cfg['run_id']='stockroom-staged-pair-authored'
    elif change=='legacy_manifest':cfg['task']['sha256']='a'*64
    elif change=='changed_prior':
        prior=json.loads(Path(cfg['predecessor']['path']).read_bytes());prior['provider_nano_usd']=0
        Path(cfg['predecessor']['path']).write_bytes(admission.canonical(prior));cfg['predecessor']['sha256']=admission.sha(admission.canonical(prior))
    raw,grant=freeze()
    with pytest.raises(admission.AdmissionRefused):admission.inspect_candidate(raw,grant)


def test_retry_retains_unknown_compute_and_next_pair(tmp_path):
    from cumulative_compute import ComputeBudget
    tmp_path.chmod(0o700)
    b=ComputeBudget(tmp_path/'compute.sqlite',prior_upper_bound_nano_usd=history.PRIOR_COMPUTE,evidence_sha256='a'*64,cap_nano_usd=history.COMPUTE_ENVELOPE,vm_seconds=750)
    assert b.total()==968370000
    b.reserve('first');b.reserve('second')
    assert b.total()==1190370000
    assert 'asyncpool05_compute.sqlite' in history.required_predecessors(set())

    assert "asyncpool09_preserved__compute.sqlite" in history.required_predecessors(set())

    assert "asyncpool10_preserved__compute.sqlite" in history.required_predecessors(set())
