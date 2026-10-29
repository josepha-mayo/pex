"""Authored zero-network failure injection only; no real key/client/provider."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import receipt_diagnostic_owner as owner
from test_worker_funding import ledger,request,stream
import worker_funding as wf


class Response:
    status_code=200
    headers={'content-type':'text/event-stream'}
    def __init__(self,fail=None):self.fail=fail
    def __enter__(self):
        if self.fail=='open_response':raise RuntimeError('AUTHORED private response failure')
        return self
    def __exit__(self,*args):
        if self.fail=='response_close':raise RuntimeError('AUTHORED response close')
    def iter_bytes(self):
        if self.fail=='partial':
            yield b'data: AUTHORED partial\n\n'
            raise TimeoutError('AUTHORED no complete wire')
        yield stream()


class Client:
    def __init__(self,fail=None):self.fail=fail
    def close(self):
        if self.fail=='client_cleanup':raise RuntimeError('AUTHORED private close')


def rig(tmp_path,monkeypatch,fail=None):
    tmp_path.chmod(0o700);root=tmp_path/'owner';body,_=request();events=[];database=[]
    def step(name,result=None):
        # The phase must ALREADY be fully published before entering a callback.
        assert any(p.name.endswith('-'+name+'.json')for p in root.glob('phase-*.json'))
        events.append(name)
        if fail==name:raise RuntimeError('AUTHORED_SECRET_ERROR_MUST_NOT_APPEAR')
        return result
    def make_ledger(where):
        step('ledger_constructor');db=ledger(where/'ledger.sqlite');database.append(db)
        reserve=db.reserve;settle=db.settle_raw;close=db.close
        def reserved(*args):step('reserve');return reserve(*args)
        def settled(*args):
            step('settle_raw')
            assert (root/'response.body').read_bytes()==args[-1]  # BEFORE strict parser.
            return settle(*args)
        def closed():
            close();step('ledger_cleanup')
        db.reserve=reserved;db.settle_raw=settled;db.close=closed
        return db
    ops=SimpleNamespace(ledger_factory=make_ledger,
        key_metadata=lambda:step('key_metadata'),key_read=lambda:step('key_read',''if fail=='key_validate'else'INERT-NOT-A-KEY'),
        signal_start=lambda:step('signal_setup'),signal_stop=lambda:step('signal_cleanup'),
        client_factory=lambda secret:step('client_constructor',Client(fail)),
        open_response=lambda client:Response(fail))
    identity={'run_id':'authored-diagnostic','config_sha256':'a'*64,'call_id':'authored-one'}
    return root,body,events,database,ops,identity


@pytest.mark.parametrize('failure',['ledger_constructor','reserve','key_metadata','key_read','key_validate',
    'signal_setup','client_constructor','open_response','settle_raw'])
def test_each_pre_or_post_wire_exception_has_actual_durable_terminal(tmp_path,monkeypatch,failure):
    root,body,events,db,ops,identity=rig(tmp_path,monkeypatch,failure)
    result,persisted=owner.execute_once(root,identity,owner.BudgetProof(100,400000000),body,ops)
    assert persisted and json.loads((root/'terminal.json').read_bytes())==result
    assert (root/'terminal-before-cleanup.json').is_file() and result['primary_error']
    assert 'AUTHORED_SECRET_ERROR_MUST_NOT_APPEAR'not in(root/'terminal.json').read_text()
    if failure in('key_metadata','key_read','key_validate','signal_setup','client_constructor'):
        assert result['reserve_acknowledged'] and not result['wire_API_entered']
        assert result['charged_bound_nanoUSD']==wf.RESERVATION and result['state']=='reserved_uncertain'
    if failure=='settle_raw':assert (root/'response.body').is_file()and result['transport_complete']
    assert not result['automatic_retry'] and result['task_success_or_PEX_lift']is None


@pytest.mark.parametrize('failure',['partial','response_close','client_cleanup','signal_cleanup','ledger_cleanup'])
def test_response_or_cleanup_errors_preserve_actual_phase_and_no_fake_success(tmp_path,monkeypatch,failure):
    root,body,events,db,ops,identity=rig(tmp_path,monkeypatch,failure)
    result,persisted=owner.execute_once(root,identity,owner.BudgetProof(100,400000000),body,ops)
    assert persisted and result['wire_API_entered']
    if failure in('partial','response_close'):
        assert not result['transport_complete'] and result['charged_bound_nanoUSD']==wf.RESERVATION
        assert result['state']=='reserved_uncertain'
    if failure=='partial':assert (root/'response.partial').read_bytes()==b'data: AUTHORED partial\n\n'
    if failure.endswith('cleanup'):assert result['cleanup_results'][failure]['completed']is False


def test_complete_capture_precedes_exact_strict_parser_and_request_archive(tmp_path,monkeypatch):
    root,body,events,db,ops,identity=rig(tmp_path,monkeypatch)
    result,persisted=owner.execute_once(root,identity,owner.BudgetProof(100,400000000),body,ops)
    assert persisted and result['transport_complete']and result['state']=='settled_raw_wire'
    assert result['usage_validation_code']=='validated_complete_wire'
    assert (root/'request.body.json').read_bytes()==body
    assert result['request']['sha256']==hashlib.sha256(body).hexdigest()
    assert result['charged_bound_nanoUSD']==420000 and result['provider_cumulative_bound_nanoUSD']==420100
    assert all(p.stat().st_mode&0o077==0 for p in root.iterdir()if p.is_file())
    with pytest.raises(FileExistsError):owner.execute_once(root,identity,owner.BudgetProof(100,400000000),body,ops)


def test_current_real_remaining_cap_refused_before_any_callback(tmp_path,monkeypatch):
    root,body,events,db,ops,identity=rig(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='cannot_fit'):
        owner.execute_once(root,identity,owner.BudgetProof(1828210200,2000000000),body,ops)
    assert not events and not root.exists()


def test_atomic_phase_failure_aborts_before_boundary_but_records_terminal(tmp_path,monkeypatch):
    root,body,events,db,ops,identity=rig(tmp_path,monkeypatch)
    original=owner.atomic_private
    def fail(path,raw):
        if Path(path).name.endswith('-key_read.json'):raise OSError('AUTHORED storage failure')
        return original(path,raw)
    monkeypatch.setattr(owner,'atomic_private',fail)
    result,persisted=owner.execute_once(root,identity,owner.BudgetProof(100,400000000),body,ops)
    assert persisted and result['primary_error']['phase']=='key_read'
    assert 'key_read'not in events and not result['wire_API_entered']
    assert result['charged_bound_nanoUSD']==wf.RESERVATION


def test_base_exception_is_reraised_only_after_actual_terminal(tmp_path,monkeypatch):
    root,body,events,db,ops,identity=rig(tmp_path,monkeypatch)
    def interrupted():raise KeyboardInterrupt()
    ops.key_read=interrupted
    with pytest.raises(KeyboardInterrupt):owner.execute_once(root,identity,owner.BudgetProof(100,400000000),body,ops)
    result=json.loads((root/'terminal.json').read_bytes())
    assert result['primary_error']=={'phase':'key_read','error_class':'KeyboardInterrupt'}
    assert not result['wire_API_entered']and result['charged_bound_nanoUSD']==wf.RESERVATION


def test_missing_cleanup_method_cannot_escape_final_terminal(tmp_path,monkeypatch):
    root,body,events,db,ops,identity=rig(tmp_path,monkeypatch)
    ops.client_factory=lambda secret:object()
    result,persisted=owner.execute_once(root,identity,owner.BudgetProof(100,400000000),body,ops)
    assert persisted and result['cleanup_results']['client_cleanup']['error_class']=='AttributeError'
    assert (root/'terminal-before-cleanup.json').is_file()
