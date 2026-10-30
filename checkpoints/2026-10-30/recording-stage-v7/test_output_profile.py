"""Authored offline output-profile fixtures; no real model or credentials."""
import json,sqlite3
import pytest
from reviewed_excerpts import assistant_content,WORKER_MODEL
from ledger_sidecar import worker_metrics,snapshot_db

def body(n,content='AUTHORED FIXTURE'):
 return json.dumps({'model':WORKER_MODEL,'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':content}}],'usage':{'prompt_tokens':3,'completion_tokens':n,'total_tokens':3+n}}).encode()

def row(n=12000):
 receipt={'call_id':'authored','arm':'baseline','request_sha256':'1'*64,'response_sha256':'2'*64,'status':200,'usage':{'input_tokens':3,'output_tokens':n,'total_tokens':3+n}}
 return ['authored','baseline','1'*64,1048576*300+16384*1200,900+n*1200,'settled_raw_wire',json.dumps(receipt)]

def test_explicit16k_keeps_legacy4k_closed():
 assert assistant_content(body(12000),'application/json',output_bound=16384)[1]['output_tokens']==12000
 with pytest.raises(ValueError):assistant_content(body(12000),'application/json')
 with pytest.raises(ValueError):assistant_content(body(16385),'application/json',output_bound=16384)
 with pytest.raises(ValueError):assistant_content(body(1),'application/json',output_bound=8192)

def test_response_bytes_bound_is_profile_bound():
 raw=body(12000,'A'*(2*1024*1024+1))
 assert len(assistant_content(raw,'application/json',output_bound=16384)[0])==2*1024*1024+1
 with pytest.raises(ValueError):assistant_content(raw,'application/json')
 with pytest.raises(ValueError):assistant_content(body(1,'A'*(8*1024*1024)),'application/json',output_bound=16384)

def test_sidecar_exact_new_reservation_and_usage():
 assert worker_metrics([row()],16384)['baseline']['worker_output_tokens']==12000
 with pytest.raises(ValueError):worker_metrics([row()])
 bad=row();bad[3]=1048576*300+4096*1200
 with pytest.raises(ValueError):worker_metrics([bad],16384)

def test_snapshot_new_bound_requires_matching_frozen_identity(tmp_path):
 p=tmp_path/'authored.sqlite'
 with sqlite3.connect(p) as db:
  db.execute('CREATE TABLE config(digest,ir,outr,input_bound,output_bound)')
  db.execute('INSERT INTO config VALUES (?,300,1200,1048576,16384)',('a'*64,))
  db.execute('CREATE TABLE calls(id,arm,request_sha,reserved,charged,state,receipt)')
  db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)',row())
 before=p.read_bytes()
 assert snapshot_db(p,config_sha='a'*64,worker=True,output_bound=16384)[0]['baseline']['worker_requests']==1
 assert p.read_bytes()==before
 with pytest.raises(ValueError):snapshot_db(p,config_sha='a'*64,worker=True)

def test_setup_check_proves_actual_config_not_inference(tmp_path):
 from ledger_sidecar import emit_setup,sha
 from types import SimpleNamespace
 root=tmp_path/'authored';root.mkdir();out=root/'proof';out.mkdir()
 raw=b'{"profile":{"worker_output_per_call":16384}}';(root/'pair.json').write_bytes(raw)
 records=[];w=SimpleNamespace(emit=lambda **x:records.append(x)or x)
 emit_setup(w,root,out,sha(raw),16384)
 assert records[0]['event']=='setup' and records[0]['qualification']=='setup_only_no_inference'
 assert not any('tokens' in k or 'requests' in k for k in records[0])
 assert (out/'setup-binding.json').stat().st_mode & 0o077 == 0
 with pytest.raises(ValueError):emit_setup(w,root,out,'0'*64,16384)
