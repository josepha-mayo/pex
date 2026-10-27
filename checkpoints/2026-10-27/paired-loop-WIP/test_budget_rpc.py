"""Authored private IPC tests: no real funding admission or provider calls."""
import base64
import json
import urllib.request
import urllib.error
import pytest
from budget_rpc import serve_budget

class Ledger:
    def __init__(self): self.calls=[]
    def reserve(self,*args):self.calls.append(('reserve',args));return {'reserved':319488000}
    def settle_raw(self,*args):self.calls.append(('settle',args));return {'settled':4500}

def post(config,payload,token=None):
    req=urllib.request.Request(config['url'],data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+(config['token'] if token is None else token),'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req,timeout=3) as r:return r.status,json.load(r)
    except urllib.error.HTTPError as e:return e.code,json.load(e)

def test_private_reserve_and_settle_exact_bytes():
    ledger=Ledger()
    with serve_budget(ledger) as cfg:
        body=b'{"authored":true}'
        status,reply=post(cfg,{'operation':'reserve','call_id':'one','request_sha256':'a'*64,'request_base64':base64.b64encode(body).decode()})
        assert status==200 and reply['ok']
        status,reply=post(cfg,{'operation':'settle','call_id':'one','request_sha256':'a'*64,'status':200,'content_type':'text/event-stream','raw_base64':base64.b64encode(b'AUTHORED').decode()})
        assert status==200 and reply['ok']
    assert ledger.calls==[('reserve',('one','a'*64,body)),('settle',('one','a'*64,200,'text/event-stream',b'AUTHORED'))]

@pytest.mark.parametrize('payload,token',[
 ({'operation':'reserve','call_id':'one','request_sha256':'a'*64,'request_base64':''},'wrong'),
 ({'operation':'run','command':'not-a-tool'},None),
 ({'operation':'reserve','call_id':'one','request_sha256':'a'*64,'request_base64':'notbase64!'},None),
 ({'operation':'reserve','call_id':'one','request_sha256':'a'*64,'request_base64':'','extra':True},None),
])
def test_non_guard_or_invalid_operation_never_reaches_ledger(payload,token):
    ledger=Ledger()
    with serve_budget(ledger) as cfg:
        status,reply=post(cfg,payload,token)
        assert status==403 and reply['ok'] is False and set(reply)=={'ok','category'}
    assert not ledger.calls
