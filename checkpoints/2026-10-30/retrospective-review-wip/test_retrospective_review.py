"""Authored offline admission/request fixtures; no providers or candidate execution."""
import base64,json,hashlib,socket
import pytest
import retrospective_review as r

@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*a,**k):raise AssertionError('network forbidden')
    monkeypatch.setattr(socket,'getaddrinfo',denied);monkeypatch.setattr(socket.socket,'connect',denied)


def checkpoint():
    from stockroom_request import snapshot_digest
    text='Authored public task for request-shape testing only.\n'
    files={'TASK.md':{'content':text,'sha256':r.sha(text.encode())}}
    return {'schema':'pex.public-pre-intervention-checkpoint.v1','condition':'baseline',
        'capture_boundary':'after_phase0_before_monitor_before_any_protected_upload','config_sha256':'a'*64,
        'public_export':{'schema':'pex.stockroom-export.v1','files':{'TASK.md':base64.b64encode(text.encode()).decode()}},
        'snapshot_sha256':snapshot_digest(files)}


def test_default_closed_before_even_config_parsing_or_credential_reads():
    assert r.APPROVED_DIAGNOSTIC == "retrospective-pair20-baseline-phase0-20261030-01"
    with pytest.raises(PermissionError,match='retrospective_root_review_pending'):r.inspect(b'not json',None)


def test_request_is_explicit_retrospective_not_live_and_never_invents_test_result():
    from pex_protocol.enums import HarnessType,SessionStatus
    from pex_supervisor.evidence_tools import select_evidence_tool_names
    request=r.build_request(json.dumps(checkpoint()).encode(),run_id='retrospective-authored-test',created_utc='2026-10-30T05:00:00+00:00')
    assert request.session.harness_type==HarnessType.SYNTHETIC and request.session.status==SessionStatus.STOPPED
    assert request.session.cwd is None and request.session.repo is None and request.session.external_url is None
    assert request.session.metadata['live_worker'] is False
    assert request.scores.features['verification']['status']=='unavailable'
    assert request.scores.features['verification']['acceptance_status']=='uncertain'
    assert set(select_evidence_tool_names(request))<=r.ALLOWED_TOOLS
    assert request.goal.objective=='Authored public task for request-shape testing only.\n'

@pytest.mark.parametrize('field,value',[('capture_boundary','after_final'),('condition','pex'),('snapshot_sha256','0'*64)])
def test_changed_capture_or_snapshot_is_refused(field,value):
    d=checkpoint();d[field]=value
    with pytest.raises(ValueError):r.build_request(json.dumps(d).encode(),run_id='retrospective-authored-test',created_utc='2026-10-30T05:00:00+00:00')


def test_hidden_export_not_transferred_and_snapshot_hash_still_required():
    d=checkpoint();d['public_export']['files']['.hidden']=base64.b64encode(b'NEVER_TRANSFER').decode()
    request=r.build_request(json.dumps(d).encode(),run_id='retrospective-authored-test',created_utc='2026-10-30T05:00:00+00:00')
    assert 'NEVER_TRANSFER' not in request.model_dump_json()

@pytest.fixture
def offline_runtime(tmp_path,monkeypatch):
    """Authored admission substitution only; real ledger and semantic composition."""
    from opentelemetry import trace,metrics
    trace.set_tracer_provider(trace.NoOpTracerProvider())
    metrics.set_meter_provider(metrics.NoOpMeterProvider())
    tmp_path.chmod(0o700)
    request=r.build_request(json.dumps(checkpoint()).encode(),run_id='retrospective-authored-test',created_utc='2026-10-30T05:00:00+00:00')
    grant=r.Grant(request.session.id,'a'*64,r.sha(request.model_dump_json().encode()),'b'*64,'c'*64)
    cfg={'output_dir':str(tmp_path/request.session.id),'key':{'path':'/DO_NOT_READ','sha256':'d'*64},
         'platform_proxy':{'proxy_sha256':'e'*64,'ca_path':'/DO_NOT_READ','ca_sha256':'f'*64},'pricing_provenance_sha256':'1'*64}
    monkeypatch.setattr(r,'inspect',lambda raw,g,**kw:(cfg,request,{}))
    runtime=r.RetrospectiveRuntime(b'authored offline admission',grant)
    yield runtime
    runtime.close()


def test_actual_ledger_retains_prior_without_VM_or_calls(offline_runtime):
    runtime=offline_runtime
    summary=runtime.summary()
    assert summary['provider_cumulative_nano_usd']==2_809_730_700
    assert summary['compute_retained_nano_usd']==610_245_000
    assert summary['calls']==[] and summary['VMs_created']==0
    assert not (runtime.root/'worker.sqlite').exists()
    runtime.ledger._validate_stored()


def test_main_composes_real_tool_protocol_and_refuses_duplicate_or_mutation(offline_runtime):
    runtime=offline_runtime
    model=runtime.model_factory('planner',runtime.request,None)
    assert model is not None
    with pytest.raises(ValueError,match='single_main'):runtime.model_factory('planner',runtime.request,None)
    changed=runtime.request.model_copy(deep=True);changed.notes='changed'
    with pytest.raises(ValueError,match='retrospective_request_changed'):runtime._bind('planner',changed,None)
    assert runtime.summary()['calls']==[]


def test_verifier_cannot_precede_main_and_does_not_execute_proposal(offline_runtime):
    from pex_supervisor import loop
    runtime=offline_runtime
    action=loop._action_from_proposal(runtime.request,{'action':'noop','reason':'Authored test only','confidence':0.5,'evidence':[]})
    with pytest.raises(ValueError,match='single_main'):runtime._bind('verifier',runtime.request,action)
    runtime.model_factory('planner',runtime.request,None)
    runtime.model_factory('verifier',runtime.request,action)
    with pytest.raises(ValueError,match='single_main'):runtime._bind('verifier',runtime.request,action)
    assert runtime.summary()['calls']==[] and runtime.summary()['worker_interventions']==0


def test_changed_pin_and_nonprivate_pin_rejected(tmp_path):
    p=tmp_path/'authored';p.write_bytes(b'authored fixture');p.chmod(0o600)
    pin={'path':str(p),'sha256':r.sha(p.read_bytes())}
    assert r.read_pin(pin,private=True)==b'authored fixture'
    p.write_bytes(b'changed')
    with pytest.raises(ValueError,match='pin_changed'):r.read_pin(pin)
    p.chmod(0o644)
    with pytest.raises(ValueError,match='private_pin_required'):r.read_pin(pin,private=True)


@pytest.mark.asyncio
async def test_failure_preserves_durable_accounting_and_does_not_retry(offline_runtime,monkeypatch):
    runtime=offline_runtime;calls=[]
    async def fail(runner):
        calls.append(1)
        runner.phase('main_before_model_and_credential')
        runner.ledger.reserve('authored-unknown-call',runner.routes[0])
        raise TimeoutError('AUTHORED timeout, no real provider')
    monkeypatch.setattr(r,'review_once',fail)
    with pytest.raises(TimeoutError):await r.execute_review(runtime)
    assert calls==[1] and runtime.closed
    summary=json.loads((runtime.root/'accounting-terminal.json').read_text())
    assert summary['fresh_supervisor_charged_nano_usd']==82329600
    assert summary['provider_cumulative_nano_usd']==r.PRIOR_PROVIDER+82329600
    assert (runtime.root/'main_before_model_and_credential.json').exists()
    assert (runtime.root/'review_failed.json').exists()
    assert json.loads((runtime.root/'failure.json').read_text())['error_type']=='TimeoutError'


def test_dependencies_match_existing_managed_runtime_and_drift_refuses(monkeypatch):
    r.check_packages()
    original=r.version
    monkeypatch.setattr(r,'version',lambda name:'0.0.0' if name=='httpx' else original(name))
    with pytest.raises(ValueError,match='dependency_identity'):r.check_packages()

def test_unreviewed_diagnostic_id_refused_before_config_parse():
    grant=r.Grant('retrospective-unreviewed','a'*64,'b'*64,'c'*64,'d'*64)
    with pytest.raises(PermissionError):r.inspect(b'not JSON',grant)
