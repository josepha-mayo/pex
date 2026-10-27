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
    value=dict(model=wf.MODEL,max_tokens=4096,n=1,stream=True,
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


def test_optional_paid_worker_public_admission_closed(tmp_path):
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


@pytest.mark.parametrize("changes",[{"n":2},{"n":True},{"max_tokens":4097},
    {"model":"other/model"},{"extra_body":{}},{"best_of":2},{"service_tier":"priority"},
    {"stream_options":{}},{"max_completion_tokens":4096},
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
