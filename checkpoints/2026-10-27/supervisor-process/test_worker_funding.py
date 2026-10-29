"""Pure local authored accounting and raw-wire parser checks; no provider calls."""
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
import worker_funding as wf


def ledger(path, arm="baseline", **changes):
    path.parent.chmod(0o700)
    args=dict(arm=arm,approved_config_digest="a"*64,approval_ref="authored-not-authorization",pricing_provenance_sha256=wf.PRICING_SHA)
    args.update(changes)
    return wf._WorkerLedger(path,**args)


def request(**changes):
    value=dict(model=wf.MODEL,max_completion_tokens=4096,n=1,stream=True,
               stream_options={"include_usage":True},messages=[{"role":"user","content":"Authored task"}],
               tools=[{"type":"function","function":{"name":"pex_remote_run","parameters":{"type":"object"}}}])
    value.update(changes)
    raw=json.dumps(value,separators=(",",":")).encode()
    return raw,hashlib.sha256(raw).hexdigest()


def usage(i=1000,o=100):
    return {"prompt_tokens":i,"completion_tokens":o,"total_tokens":i+o,
            "prompt_tokens_details":{"cached_tokens":10},"completion_tokens_details":{"reasoning_tokens":20}}


def stream(*, used=None):
    base={"id":"authored-stream","model":wf.MODEL}
    chunks=[dict(base,choices=[{"index":0,"delta":{"content":"authored"},"finish_reason":None}]),
            dict(base,choices=[{"index":0,"delta":{},"finish_reason":"stop"}]),
            dict(base,choices=[],usage=used or usage())]
    return ("".join("data: "+json.dumps(c)+"\n\n" for c in chunks)+"data: [DONE]\n\n").encode()


def complete():
    return json.dumps({"model":wf.MODEL,"choices":[{"index":0,"finish_reason":"stop","message":{"role":"assistant","content":"synthetic-private-body-do-not-persist"}}],"usage":usage()}).encode()


def test_optional_paid_worker_rejects_unrecognized_approval(tmp_path):
    with pytest.raises(PermissionError,match="not_authorized"):
        wf.WorkerFunding(tmp_path/"worker.sqlite",arm="baseline",approved_config_digest="a"*64,
            approval_ref="authored-not-authorization",pricing_provenance_sha256=wf.PRICING_SHA)
    assert not (tmp_path/"worker.sqlite").exists()


@pytest.mark.parametrize("kind,body",[("text/event-stream",stream()),("application/json",complete())])
def test_six_small_raw_settlements_fit_each_separate_arm(tmp_path,kind,body):
    path=tmp_path/"worker.sqlite";raw,sha=request()
    for arm in wf.ARMS:
        db=ledger(path,arm)
        for n in range(6):
            call=f"{arm}-{n}"
            receipt=db.reserve(call,sha,raw)
            assert receipt["reserved_nano_usd"]==319488000
            settled=db.settle_raw(call,sha,200,kind,body)
            assert settled["state"]=="settled_raw_wire"
            assert settled["charged_nano_usd"]==420000
        db.close()
    db=ledger(path)
    assert db.summary()["charged_nano_usd"]=={"baseline":2520000,"pex":2520000}
    text=str(db.db.execute("SELECT * FROM calls").fetchall())
    assert "synthetic-private-body-do-not-persist" not in text and "Authored task" not in text
    db.close()


def test_unknown_reservation_blocks_same_arm_not_other_arm(tmp_path):
    path=tmp_path/"worker.sqlite";raw,sha=request()
    baseline=ledger(path);baseline.reserve("baseline-unknown",sha,raw);baseline.close()
    baseline=ledger(path)
    with pytest.raises(wf.WorkerBudgetExhausted) as e: baseline.reserve("second",sha,raw)
    assert e.value.code=="worker_budget_reservation_refused"
    pex=ledger(path,"pex");pex.reserve("pex-unknown",sha,raw)
    assert pex.summary()["charged_nano_usd"]=={"baseline":319488000,"pex":319488000}
    with pytest.raises(wf.WorkerBudgetExhausted): pex.reserve("pex-second",sha,raw)
    baseline.close();pex.close()


def test_wire_reason_is_allowlisted_without_persisting_exception_text(tmp_path,monkeypatch):
    db=ledger(tmp_path/'worker.sqlite');raw,sha=request();db.reserve('call',sha,raw)
    def failed(*_):raise ValueError('AUTHORED_PRIVATE_EXCEPTION_MUST_NOT_LEAK')
    monkeypatch.setattr(wf,'_wire_usage',failed)
    result=db.settle_raw('call',sha,200,'text/event-stream',stream())
    row=db.db.execute('SELECT receipt FROM calls').fetchone()[0]
    assert result['state']=='uncertain' and result['charged_nano_usd']==wf.RESERVATION
    assert json.loads(row)['usage_validation_code']=='wire_validation_unclassified'
    assert 'AUTHORED_PRIVATE_EXCEPTION_MUST_NOT_LEAK' not in row
    assert 'wire_evidence' not in json.loads(row)  # No legacy raw-body archival.
    db.close()


def test_wire_sink_failure_never_reduces_pending_reservation(tmp_path):
    def failed(*_):raise OSError('AUTHORED evidence persistence failure')
    db=ledger(tmp_path/'worker.sqlite',wire_evidence_sink=failed);raw,sha=request();db.reserve('call',sha,raw)
    with pytest.raises(OSError):db.settle_raw('call',sha,200,'text/event-stream',stream())
    assert db.db.execute('SELECT charged,state,receipt FROM calls').fetchone()==(wf.RESERVATION,'reserved_uncertain',None)
    db.close()


def test_oversized_wire_never_reaches_sink_or_refunds(tmp_path):
    observed=[];db=ledger(tmp_path/'worker.sqlite',wire_evidence_sink=lambda *args:observed.append(args))
    raw,sha=request();db.reserve('call',sha,raw)
    with pytest.raises(ValueError):db.settle_raw('call',sha,200,'text/event-stream',b'x'*(wf.MAX_BYTES+1))
    assert not observed and db.db.execute('SELECT charged,state FROM calls').fetchone()==(wf.RESERVATION,'reserved_uncertain')
    db.close()


def test_global_db_concurrent_requests_do_not_cross_subsidize(tmp_path):
    path=tmp_path/"worker.sqlite";ledger(path).close();raw,sha=request();barrier=Barrier(6)
    def attempt(index):
        db=ledger(path,wf.ARMS[index%2])
        try:
            barrier.wait(timeout=10)
            try: db.reserve(f"parallel-{index}",sha,raw);return True
            except wf.WorkerBudgetExhausted:return False
        finally:db.close()
    with ThreadPoolExecutor(max_workers=6) as pool: assert sum(pool.map(attempt,range(6)))==2
    db=ledger(path);assert db.summary()["attempts"]=={"baseline":1,"pex":1};db.close()


def test_each_arm_attempt_cap_survives_reopen(tmp_path):
    path=tmp_path/"worker.sqlite";raw,sha=request();db=ledger(path)
    for n in range(12):
        db.reserve(f"call-{n}",sha,raw);db.settle_raw(f"call-{n}",sha,200,"text/event-stream",stream())
    db.close();db=ledger(path)
    with pytest.raises(wf.WorkerBudgetExhausted) as e:db.reserve("thirteenth",sha,raw)
    assert e.value.code=="worker_attempt_cap_refused"
    pex=ledger(path,"pex");pex.reserve("first-pex",sha,raw);pex.close();db.close()


@pytest.mark.parametrize("body",[
    stream().replace(b"data: [DONE]\n\n",b""),
    stream()+b"data: {}\n\n",
    stream().replace(wf.MODEL.encode(),b"other/model"),
    stream().replace(b'"total_tokens": 1100',b'"total_tokens": 1099'),
    stream().replace(b'"reasoning_tokens": 20',b'"reasoning_tokens": 101'),
    stream().replace(b'"choices": [], "usage"',b'"choices": [{"index":0}], "usage"'),
    b"data: [DONE]\n\n",b"invalid",b"",
])
def test_missing_or_ambiguous_sse_usage_retains_full(tmp_path,body):
    db=ledger(tmp_path/"worker.sqlite");raw,sha=request();db.reserve("call",sha,raw)
    result=db.settle_raw("call",sha,200,"text/event-stream",body)
    assert result["state"]=="uncertain" and result["charged_nano_usd"]==319488000
    with pytest.raises(wf.WorkerBudgetExhausted):db.reserve("second",sha,raw)
    db.close()


@pytest.mark.parametrize("changes",[{"n":2},{"n":True},{"max_completion_tokens":4097},
    {"model":"other/model"},{"extra_body":{}},{"best_of":2},{"service_tier":"priority"},
    {"stream_options":{}},{"max_tokens":4096},
    {"tools":[{"type":"function","function":{"name":"local_shell"}}]}])
def test_bad_request_refused_before_reservation(tmp_path,changes):
    db=ledger(tmp_path/"worker.sqlite");raw,sha=request(**changes)
    with pytest.raises(ValueError):db.reserve("bad",sha,raw)
    assert db.summary()["attempts"]=={"baseline":0,"pex":0};db.close()


def test_cross_arm_and_duplicate_settlement_refused(tmp_path):
    path=tmp_path/"worker.sqlite";raw,sha=request();baseline=ledger(path);pex=ledger(path,"pex")
    baseline.reserve("call",sha,raw)
    with pytest.raises(ValueError):pex.settle_raw("call",sha,200,"text/event-stream",stream())
    baseline.settle_raw("call",sha,200,"text/event-stream",stream())
    with pytest.raises(ValueError):baseline.settle_raw("call",sha,200,"text/event-stream",stream())
    baseline.close();pex.close()


@pytest.mark.parametrize("body",[
    json.dumps({"model":wf.MODEL,"choices":["bad"],"usage":usage()}).encode(),
    json.dumps({"model":wf.MODEL,"choices":[{"index":False,"finish_reason":"stop"}],"usage":usage()}).encode(),
])
def test_malformed_json_choices_cannot_refund(tmp_path,body):
    db=ledger(tmp_path/"worker.sqlite");raw,sha=request();db.reserve("call",sha,raw)
    result=db.settle_raw("call",sha,200,"application/json",body)
    assert result["state"]=="uncertain" and result["charged_nano_usd"]==319488000
    db.close()


def test_corrupt_unknown_charge_and_changed_identity_refused(tmp_path):
    path=tmp_path/"worker.sqlite";db=ledger(path);raw,sha=request();db.reserve("call",sha,raw)
    db.db.execute("UPDATE calls SET charged=0")
    with pytest.raises(ValueError):db.reserve("next",sha,raw)
    db.close()
    with pytest.raises(ValueError):ledger(path)
    with pytest.raises(ValueError):ledger(path,approved_config_digest="b"*64)


def test_same_ledger_instance_is_safe_for_rpc_threads(tmp_path):
    db=ledger(tmp_path/"worker.sqlite");raw,sha=request();barrier=Barrier(6)
    def admit(index):
        barrier.wait(timeout=10)
        try:db.reserve(f"rpc-{index}",sha,raw);return f"rpc-{index}"
        except wf.WorkerBudgetExhausted:return None
    with ThreadPoolExecutor(max_workers=6) as pool: admitted=[x for x in pool.map(admit,range(6)) if x]
    assert len(admitted)==1
    def settle(_):
        try:return db.settle_raw(admitted[0],sha,200,"text/event-stream",stream())["state"]
        except ValueError:return "refused"
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(settle,range(2)))==["refused","settled_raw_wire"]
    assert db.summary()["charged_nano_usd"]["baseline"]==420000
    db.close()


def test_429_and_duplicate_final_usage_hold_full_reservation(tmp_path):
    raw,sha=request()
    for index in (0,1):
        path=tmp_path/f"ledger-{index}.sqlite";db=ledger(path);db.reserve("call",sha,raw)
        body=stream()
        if index:
            final=body.split(b"\n\n")[-3]+b"\n\n"
            body=body.replace(b"data: [DONE]",final+b"data: [DONE]")
        result=db.settle_raw("call",sha,429 if index==0 else 200,"text/event-stream",body)
        assert result["state"]=="uncertain" and result["charged_nano_usd"]==319488000
        db.close()



def test_exact_current_approval_opens_only_fixed_funding_profile(tmp_path):
    tmp_path.chmod(0o700)
    db=wf.WorkerFunding(tmp_path/"approved.sqlite",arm="baseline",approved_config_digest="a"*64,
        approval_ref="Sentinel_9df859db703081919786cd38c9678f05",pricing_provenance_sha256=wf.PRICING_SHA)
    assert db.summary()=={"charged_nano_usd":{"baseline":0,"pex":0},"attempts":{"baseline":0,"pex":0},"per_arm_budget_nano_usd":375000000}
    assert wf.MAX_ATTEMPTS==12 and wf.RESERVATION==319488000
    db.close()


@pytest.mark.parametrize("approval",[None,"Sentinel_a6f9e81f1aa88191a915b10436a3cb06",
    "Sentinel_5d0953f8f7c081919c23779c578048b9"])
def test_prior_scope_or_request_is_not_new_approval(tmp_path,approval):
    with pytest.raises(PermissionError,match="not_authorized"):
        wf.WorkerFunding(tmp_path/"refused.sqlite",arm="baseline",approved_config_digest="a"*64,
            approval_ref=approval,pricing_provenance_sha256=wf.PRICING_SHA)
    assert not (tmp_path/"refused.sqlite").exists()


def test_successor_retains_prior_charges_and_has_bounded_new_attempts(tmp_path):
    path=tmp_path/'successor.sqlite';raw,sha=request()
    prior={'baseline':10081800,'pex':9382800}
    db=ledger(path,prior_charged_nano_usd=prior,predecessor_sha256='b'*64)
    for n in range(12):
        db.reserve(f'new-{n}',sha,raw)
        db.settle_raw(f'new-{n}',sha,200,'application/json',complete())
    assert db.summary()['charged_nano_usd']['baseline']==10081800+12*420000
    with pytest.raises(wf.WorkerBudgetExhausted,match='attempt_cap'):
        db.reserve('new-13',sha,raw)
    db.close()
    with pytest.raises(ValueError,match='predecessor identity'):
        ledger(path)


def test_successor_cannot_spend_prior_retained_dollars(tmp_path):
    path=tmp_path/'successor.sqlite';raw,sha=request()
    db=ledger(path,prior_charged_nano_usd={'baseline':60000000,'pex':0},predecessor_sha256='b'*64)
    with pytest.raises(wf.WorkerBudgetExhausted,match='budget_reservation'):
        db.reserve('would-exceed-original-cap',sha,raw)
    assert db.summary()['attempts']['baseline']==0
    db.close()


def test_successor_requires_pinned_prior_identity(tmp_path):
    with pytest.raises(ValueError,match='digest'):
        ledger(tmp_path/'invalid.sqlite',prior_charged_nano_usd={'baseline':1,'pex':0})


def test_successor_350m_pool_has_equal_fresh_phase_allowance(tmp_path):
    path=tmp_path/'new-split.sqlite';raw,sha=request();prior={'baseline':10081800,'pex':9382800}
    for arm in wf.ARMS:
        db=ledger(path,arm,prior_charged_nano_usd=prior,predecessor_sha256='b'*64,arm_budget_nano_usd=350000000,phase_limit_nano_usd=339918200)
        assert db.phase_limit==339918200
        db.reserve(arm+'-one',sha,raw)
        assert db.summary()['charged_nano_usd'][arm]==prior[arm]+wf.RESERVATION
        db.close()
    with pytest.raises(ValueError):
        ledger(tmp_path/'bad-split.sqlite',prior_charged_nano_usd=prior,predecessor_sha256='b'*64,arm_budget_nano_usd=250000000)
    with pytest.raises(ValueError):
        ledger(tmp_path/'bad-phase.sqlite',prior_charged_nano_usd=prior,predecessor_sha256='b'*64,arm_budget_nano_usd=350000000,phase_limit_nano_usd=340000000)


def cumulative_chunks():
    """Authored structural fixture, not copied provider output or inference proof."""
    base = {"id": "authored-cumulative-stream", "model": wf.MODEL}
    chunks = []
    for n in (0, 2, 2, 7):
        used = {"prompt_tokens": 37, "completion_tokens": n, "total_tokens": 37+n,
                "completion_tokens_details": {"reasoning_tokens": n}}
        chunks.append(dict(base, choices=[{"index": 0, "delta": {"reasoning": "authored"},
            "finish_reason": "length" if n == 7 else None}], usage=used))
    final = dict(chunks[-1]["usage"], prompt_tokens_details={"cached_tokens": 0, "created_cache_tokens": 32})
    chunks.append(dict(base, choices=[], usage=final))
    return chunks


def cumulative_wire(chunks, done=True):
    return ("".join("data: "+json.dumps(c)+"\n\n" for c in chunks)
            + ("data: [DONE]\n\n" if done else "")).encode()


def test_authored_cumulative_stream_requires_distinct_terminal_receipt(tmp_path):
    body = cumulative_wire(cumulative_chunks())
    assert wf._wire_usage(200, "text/event-stream", body) == {
        "input_tokens": 37, "output_tokens": 7, "total_tokens": 44}
    db=ledger(tmp_path/'worker.sqlite'); raw,sha=request(); db.reserve('call',sha,raw)
    result=db.settle_raw('call',sha,200,'text/event-stream',body)
    assert result['state']=='settled_raw_wire' and result['charged_nano_usd']==19500
    db.close()


@pytest.mark.parametrize("mutation", [
    'regress', 'prompt-change', 'sum', 'boolean', 'float', 'negative', 'input-bound',
    'output-bound', 'details-bound', 'details-regress', 'details-missing', 'details-conflict',
    'terminal-decrease', 'terminal-increase', 'terminal-details-increase',
    'no-finish', 'no-terminal', 'no-done', 'double-terminal', 'post-finish-choice',
    'post-terminal-empty', 'post-done', 'mixed-id', 'wrong-model', 'duplicate-key',
    'truncated', 'terminal-before-finish', 'empty-without-usage',
])
def test_cumulative_invalid_stream_never_refunds(tmp_path, mutation):
    chunks=cumulative_chunks(); done=True; suffix=b''
    if mutation=='regress': chunks[2]['usage'].update(completion_tokens=1,total_tokens=38,
        completion_tokens_details={'reasoning_tokens':1})
    elif mutation=='prompt-change': chunks[1]['usage'].update(prompt_tokens=38,total_tokens=40)
    elif mutation=='sum': chunks[1]['usage']['total_tokens']=999
    elif mutation=='boolean': chunks[1]['usage']['completion_tokens']=True
    elif mutation=='float': chunks[1]['usage']['completion_tokens']=2.0
    elif mutation=='negative': chunks[1]['usage']['completion_tokens']=-1
    elif mutation=='input-bound': chunks[0]['usage'].update(prompt_tokens=wf.INPUT_BOUND+1,total_tokens=wf.INPUT_BOUND+1)
    elif mutation=='output-bound': chunks[1]['usage'].update(completion_tokens=wf.OUTPUT_BOUND+1,total_tokens=37+wf.OUTPUT_BOUND+1)
    elif mutation=='details-bound': chunks[1]['usage']['completion_tokens_details']['reasoning_tokens']=3
    elif mutation=='details-regress': chunks[2]['usage']['completion_tokens_details']['reasoning_tokens']=1
    elif mutation=='details-missing': del chunks[2]['usage']['completion_tokens_details']
    elif mutation=='details-conflict':
        chunks[0]['usage']['prompt_tokens_details']={'cached_tokens':1}
        chunks[1]['usage']['prompt_tokens_details']={'cached_tokens':2}
    elif mutation in ('terminal-decrease','terminal-increase'):
        n=6 if mutation=='terminal-decrease' else 8
        chunks[-1]['usage'].update(completion_tokens=n,total_tokens=37+n,
            completion_tokens_details={'reasoning_tokens':n})
    elif mutation=='terminal-details-increase':
        chunks[-2]['usage']['completion_tokens_details']={'reasoning_tokens':6}
    elif mutation=='no-finish': chunks[-2]['choices'][0]['finish_reason']=None
    elif mutation=='no-terminal': chunks.pop()
    elif mutation=='no-done': done=False
    elif mutation=='double-terminal': chunks.append(chunks[-1])
    elif mutation=='post-finish-choice': chunks.insert(-1,chunks[0])
    elif mutation=='post-terminal-empty': chunks.append(dict(chunks[-1],usage=None))
    elif mutation=='post-done': suffix=b'data: {}\n\n'
    elif mutation=='mixed-id': chunks[1]['id']='other-stream'
    elif mutation=='wrong-model': chunks[1]['model']='other-model'
    elif mutation=='terminal-before-finish': chunks.insert(0,chunks[-1])
    elif mutation=='empty-without-usage': chunks.insert(-1,dict(chunks[-1],usage=None))
    body=cumulative_wire(chunks,done=done)+suffix
    if mutation=='duplicate-key': body=body.replace(b'"completion_tokens": 2',b'"completion_tokens": 2, "completion_tokens": 2',1)
    elif mutation=='truncated': body=body[:-1]
    db=ledger(tmp_path/'worker.sqlite'); raw,sha=request(); db.reserve('call',sha,raw)
    result=db.settle_raw('call',sha,200,'text/event-stream',body)
    assert result['state']=='uncertain' and result['charged_nano_usd']==wf.RESERVATION
    db.close()


def test_sparse_legacy_cumulative_and_final_only_usage_still_validate():
    chunks=cumulative_chunks()
    del chunks[-2]['usage']  # No frozen count: the final receipt may advance.
    assert wf._wire_usage(200,'text/event-stream',cumulative_wire(chunks))['output_tokens']==7
    assert wf._wire_usage(200,'text/event-stream',stream())['output_tokens']==100


def staged_ledger(path, **changes):
    return ledger(path,output_token_bound=wf.STAGED_OUTPUT_BOUND,
                  arm_budget_nano_usd=wf.STAGED_ARM_BUDGET,**changes)


def test_explicit_16k_profile_exact_request_reservation_and_usage(tmp_path):
    db=staged_ledger(tmp_path/'staged.sqlite');raw,sha=request(max_completion_tokens=16384)
    assert db.reservation==wf.STAGED_RESERVATION==334233600
    assert db.output_token_bound==16384 and db.max_response_bytes==8*1024*1024
    assert db.reserve('new',sha,raw)['reserved_nano_usd']==334233600
    result=db.settle_raw('new',sha,200,'text/event-stream',stream(used=usage(37,16384)))
    assert result['state']=='settled_raw_wire' and result['charged_nano_usd']==19671900
    assert db.usage_snapshot()==dict(calls=1,input_tokens=37,output_tokens=16384,uncertain_calls=0)
    assert db.db.execute('SELECT output_bound,budget FROM config').fetchall()==[(16384,750000000)]
    db.close()


@pytest.mark.parametrize('old_first',[False,True])
def test_16k_profile_cannot_relabel_or_reopen_4k_ledger(tmp_path,old_first):
    path=tmp_path/'bound.sqlite';first=ledger if old_first else staged_ledger
    second=staged_ledger if old_first else ledger
    db=first(path);db.close();before=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):second(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('changes',[
    {'output_token_bound':16384},{'arm_budget_nano_usd':750000000},
    {'output_token_bound':8192,'arm_budget_nano_usd':750000000},
    {'output_token_bound':32768,'arm_budget_nano_usd':750000000},
    {'output_token_bound':True,'arm_budget_nano_usd':750000000},
])
def test_only_exact_new_output_budget_pair_is_supported(tmp_path,changes):
    with pytest.raises(ValueError):ledger(tmp_path/'refused.sqlite',**changes)
    assert not (tmp_path/'refused.sqlite').exists()


def test_new_output_bound_does_not_reopen_legacy_public_approval(tmp_path):
    with pytest.raises(PermissionError):wf.WorkerFunding(tmp_path/'refused.sqlite',arm='baseline',
        approved_config_digest='a'*64,approval_ref=wf.APPROVED_WORKER_REF,
        pricing_provenance_sha256=wf.PRICING_SHA,output_token_bound=16384,arm_budget_nano_usd=750000000)
    assert not (tmp_path/'refused.sqlite').exists()


@pytest.mark.parametrize('maximum',[4096,16384])
def test_request_must_match_its_immutable_output_profile(tmp_path,maximum):
    db=ledger(tmp_path/'bound.sqlite') if maximum==4096 else staged_ledger(tmp_path/'bound.sqlite')
    for wrong in (4096 if maximum==16384 else 16384,maximum+1,True):
        raw,sha=request(max_completion_tokens=wrong)
        with pytest.raises(ValueError):db.reserve('wrong',sha,raw)
    assert db.usage_snapshot()['calls']==0
    db.close()


def test_16k_unknown_reservations_never_exceed_fresh_750m(tmp_path):
    db=staged_ledger(tmp_path/'bound.sqlite');raw,sha=request(max_completion_tokens=16384)
    for n in range(2):db.reserve(str(n),sha,raw)
    with pytest.raises(wf.WorkerBudgetExhausted):db.reserve('third',sha,raw)
    assert db.summary()['charged_nano_usd']['baseline']==2*334233600
    db.close()


@pytest.mark.parametrize('bad_output',[16385,True,16384.0,-1])
def test_16k_malformed_or_overflow_usage_stays_full(tmp_path,bad_output):
    db=staged_ledger(tmp_path/'bound.sqlite');raw,sha=request(max_completion_tokens=16384);db.reserve('one',sha,raw)
    u=usage(37,16384);u['completion_tokens']=bad_output
    result=db.settle_raw('one',sha,200,'text/event-stream',stream(used=u))
    assert result['state']=='uncertain' and result['charged_nano_usd']==334233600
    db.close()


def test_16k_cumulative_counters_still_require_consistent_terminal():
    chunks=cumulative_chunks()
    for index,n in enumerate((0,4097,8192,16384,16384)):
        chunks[index]['usage']['completion_tokens']=n
        chunks[index]['usage']['total_tokens']=37+n
        chunks[index]['usage']['completion_tokens_details']={'reasoning_tokens':n}
    body=cumulative_wire(chunks)
    assert wf._wire_usage(200,'text/event-stream',body,output_token_bound=16384)['output_tokens']==16384
    with pytest.raises(ValueError):wf._wire_usage(200,'text/event-stream',body)
    chunks[-1]['usage']['completion_tokens_details']['reasoning_tokens']=16383
    with pytest.raises(ValueError):wf._wire_usage(200,'text/event-stream',cumulative_wire(chunks),output_token_bound=16384)


def test_large_frame_limit_is_new_profile_only_and_remains_strict(tmp_path):
    base=stream(used=usage(37,16384))
    body=b':'+b'x'*(wf.STAGED_RESPONSE_BYTES-len(base)-3)+b'\n\n'+base
    assert len(body)==wf.STAGED_RESPONSE_BYTES
    assert wf._wire_usage(200,'text/event-stream',body,output_token_bound=16384)['output_tokens']==16384
    for invalid in (body+b'\n',body[:-1],body.replace(b'data: [DONE]\n\n',b''),body+base):
        with pytest.raises(ValueError):wf._wire_usage(200,'text/event-stream',invalid,output_token_bound=16384)
    with pytest.raises(ValueError):wf._wire_usage(200,'text/event-stream',body)
    observed=[];db=staged_ledger(tmp_path/'bound.sqlite',wire_evidence_sink=lambda *a:(observed.append(len(a[5])) or {'path':'AUTHORED','sha256':'b'*64}))
    raw,sha=request(max_completion_tokens=16384);db.reserve('one',sha,raw)
    assert db.settle_raw('one',sha,200,'text/event-stream',body)['state']=='settled_raw_wire'
    assert observed==[wf.STAGED_RESPONSE_BYTES]
    db.reserve('two',sha,raw)
    with pytest.raises(ValueError):db.settle_raw('two',sha,200,'text/event-stream',body+b'\n')
    assert observed==[wf.STAGED_RESPONSE_BYTES]
    assert db.db.execute("SELECT state,charged FROM calls WHERE id='two'").fetchone()==('reserved_uncertain',334233600)
    # Larger response allowance never enlarges the admitted request envelope.
    oversized=b'x'*(wf.MAX_BYTES+1)
    with pytest.raises(ValueError):db.reserve('request-too-large',hashlib.sha256(oversized).hexdigest(),oversized)
    db.close()


@pytest.mark.parametrize('field,value',[('output_token_bound',32768),('reservation',1),('max_response_bytes',16*1024*1024),('arm_budget',10**12)])
def test_new_profile_runtime_attribute_mutation_cannot_expand_authority(tmp_path,field,value):
    db=staged_ledger(tmp_path/'bound.sqlite');setattr(db,field,value)
    raw,sha=request(max_completion_tokens=16384)
    with pytest.raises(ValueError):db.reserve('changed',sha,raw)
    assert db.db.execute('SELECT COUNT(*) FROM calls').fetchone()==(0,)
    db.close()
