"""Authored exact request persistence before any model factory/dispatch."""
import asyncio
import pytest
from public_request import build_public_request
from review import OwnedReview
from pex_protocol.supervisor import SupervisorRequest,supervisor_request_digest


def inputs():
    arm={'prompt':'Authored public task','public_sha256':'a'*64,'worker_identity':'authored/model'}
    observation={'assistant_final':'Authored final','public_diff':'Authored diff','receipt_sha256':'b'*64,
      'public_check':{'command':'python -m unittest discover -s tests -p test_smoke.py','exit_code':0,'output':'Authored smoke','receipt_sha256':'c'*64}}
    return arm,observation

def test_exact_request_survives_model_factory_failure():
    saved=[]
    def factory(*args):
        assert len(saved)==1
        raise RuntimeError('authored transport failure')
    reviewer=OwnedReview(build_public_request,factory,request_recorder=lambda digest,raw:saved.append((digest,raw)))
    arm,observation=inputs()
    with pytest.raises(RuntimeError):asyncio.run(reviewer.review(arm,observation,session_id='actual-authored-session'))
    digest,raw=saved[0];request=SupervisorRequest.model_validate_json(raw)
    assert supervisor_request_digest(request)==digest
    assert request.session.vendor_session_id=='actual-authored-session'
    assert request.scores.features['verification']['acceptance_status']=='uncertain'
    assert any('Authored smoke' in (event.message_delta or '') for event in request.recent_events)

def test_persistence_failure_prevents_dispatch():
    calls=[]
    def recorder(*args):raise OSError('authored private store failure')
    reviewer=OwnedReview(build_public_request,lambda *a:calls.append(a),request_recorder=recorder)
    arm,observation=inputs()
    with pytest.raises(OSError):asyncio.run(reviewer.review(arm,observation,session_id='authored-session'))
    assert calls==[]
