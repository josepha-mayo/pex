"""Authored offline fixtures only: no model, provider, capture, UI, or benchmark."""
import base64
import contextlib
import copy
import datetime as dt
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import record_support as r
from reviewed_excerpts import drain_approved, verify_selection, assistant_content, WORKER_MODEL
from safe_feed_writer import SafeFeedWriter


class ReviewedExcerptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pex-excerpt-AUTHORED-')
        self.root = getattr(self,'external_fixture_root',Path(self.temp.name) / 'authored-recorder-test-not-inference')
        if hasattr(self,'external_fixture_root'):
            if not self.root.name.startswith('authored-recorder-') or (self.root/'pair.json').exists():
                raise ValueError('fresh_authored_fixture_only')
        self.root.mkdir(mode=0o700,exist_ok=hasattr(self,'external_fixture_root'))
        (self.root / 'run/worker-wire').mkdir(parents=True, mode=0o700)
        self.put(self.root / 'pair.json', {'AUTHORED_FIXTURE_ONLY': True})
        self.config = r.sha((self.root / 'pair.json').read_bytes())
        self.call = 'authored-call'; self.text = 'AUTHORED FIXTURE ONLY — NOT A MODEL RESPONSE'
        body = {'model':WORKER_MODEL,'choices': [{'index':0,'finish_reason':'stop','message': {'role': 'assistant', 'content': self.text + '\nWITHHELD_FIXTURE_NOT_SELECTED'}}],
                'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}}
        raw = r.canonical(body).encode(); self.request = '1' * 64
        self.source = {'schema': 'pex.staged.private-worker-wire.v1', 'run_id': self.root.name,
            'config_sha256': self.config, 'arm': 'baseline', 'call_id': self.call,
            'request_sha256': self.request, 'HTTP_status': 200, 'content_type': 'application/json',
            'raw_response_base64': base64.b64encode(raw).decode(), 'response_sha256': r.sha(raw),
            'usage_validation_code': 'validated_complete_wire', 'request_body_or_headers_captured': False}
        self.wire = self.root / 'run/worker-wire' / (r.sha(r.canonical(['baseline', self.call]).encode()) + '.json')
        self.put(self.wire, self.source); self.source_sha = r.sha(self.wire.read_bytes())
        self.receipt = {'call_id': self.call, 'arm': 'baseline', 'request_sha256': self.request,
            'response_sha256': self.source['response_sha256'], 'status': 200,
            'usage': {'input_tokens': 3, 'output_tokens': 2, 'total_tokens': 5},
            'usage_validation_code': 'validated_complete_wire',
            'wire_evidence': {'path': str(self.wire), 'sha256': self.source_sha}}
        self.db = self.root / 'run/workers.sqlite'
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE config(digest,ir,outr,input_bound,output_bound)')
            c.execute('INSERT INTO config VALUES (?,?,?,?,?)', (self.config,300,1200,1048576,4096))
            c.execute('CREATE TABLE calls(id,arm,request_sha,reserved,charged,state,receipt)')
            c.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,?)', (self.call,'baseline',self.request,
                1048576*300+4096*1200,3300,'settled_raw_wire',json.dumps(self.receipt)))
        self.db.chmod(0o600)
        self.now = time.time(); self.started = self.now - 10
        self.reviewed = dt.datetime.fromtimestamp(self.now-1,dt.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
        self.manifest = {'schema':'pex-reviewed-worker-selection/v1','run_id':self.root.name,
            'config_sha256':self.config,'source_relative_path':str(self.wire.relative_to(self.root)),
            'source_sha256':self.source_sha,'model_excerpt_sha256':r.sha(self.text.encode()),
            'start_byte':0,'end_byte':len(self.text.encode()),'reviewed_utc':self.reviewed}
        self.inbox=self.root/'reviewed-excerpts-inbox';self.inbox.mkdir(mode=0o700)
        self.selection=self.inbox/'reviewed-001.json';self.put(self.selection,self.manifest)
        self.approvals={(self.root.name,self.source_sha,self.manifest['model_excerpt_sha256'])}
        self.put(self.root/'reviewed-excerpts.json',{'schema':'pex-excerpt-approvals/v1','approvals':[
            dict(run_id=a,source_sha256=b,model_excerpt_sha256=c) for a,b,c in self.approvals]})

    def tearDown(self): self.temp.cleanup()

    def put(self,path,value):
        path.write_text(r.canonical(value)+'\n');path.chmod(0o600)

    def verify(self, approvals=None):
        return verify_selection(self.root,self.selection,run_id=self.root.name,config_sha=self.config,
            approvals=self.approvals if approvals is None else approvals,started=self.started,now=self.now)

    def sse_frames(self):
        frames=[]
        for delta in [{'role':'assistant','content':''},{'content':self.text[:20]},
                      {'content':self.text[20:],'reasoning_content':'WITHHELD_REASONING_FIXTURE'},
                      {'tool_calls':[{'function':{'arguments':'WITHHELD_TOOL_FIXTURE'}}]},{}]:
            frames.append({'id':'AUTHORED_STREAM_NOT_PROVIDER','model':WORKER_MODEL,
                'choices':[{'index':0,'delta':delta,'finish_reason':None}]})
        frames[-1]['choices'][0]['finish_reason']='stop'
        frames.append({'id':'AUTHORED_STREAM_NOT_PROVIDER','model':WORKER_MODEL,'choices':[],
            'usage':{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5}})
        return frames

    def encode_sse(self,frames,done=True):
        return (': authored fixture heartbeat\r\n\r\n' + ''.join('data: '+r.canonical(f)+'\r\n\r\n' for f in frames)
                + ('data: [DONE]\r\n\r\n' if done else '')).encode()

    def install_sse(self):
        response=self.encode_sse(self.sse_frames());self.source['content_type']='text/event-stream; charset=utf-8'
        self.source['raw_response_base64']=base64.b64encode(response).decode();self.source['response_sha256']=r.sha(response)
        self.put(self.wire,self.source);self.source_sha=r.sha(self.wire.read_bytes())
        self.receipt['response_sha256']=self.source['response_sha256'];self.receipt['wire_evidence']['sha256']=self.source_sha
        with sqlite3.connect(self.db) as c:c.execute('UPDATE calls SET receipt=?',(json.dumps(self.receipt),))
        self.manifest['source_sha256']=self.source_sha;self.put(self.selection,self.manifest)
        self.approvals={(self.root.name,self.source_sha,self.manifest['model_excerpt_sha256'])}
        self.put(self.root/'reviewed-excerpts.json',{'schema':'pex-excerpt-approvals/v1','approvals':[
            dict(run_id=a,source_sha256=b,model_excerpt_sha256=c) for a,b,c in self.approvals]})

    def test_sse_exact_multichunk_selection_and_readonly(self):
        self.install_sse();before=self.db.read_bytes();fields=self.verify()
        self.assertEqual(fields['model_excerpt'],self.text);self.assertEqual(self.db.read_bytes(),before)
        self.assertNotIn('WITHHELD',fields['model_excerpt'])

    def test_sse_complete_framing_finish_and_terminal_usage_required(self):
        frames=self.sse_frames()
        bad=[self.encode_sse(frames,False),self.encode_sse(frames)[:-1],
             self.encode_sse(frames[:-1]),self.encode_sse(frames+[frames[-1]]),
             self.encode_sse([frames[-1]]+frames[:-1]),self.encode_sse(frames)+b'data: {}\n\n']
        unfinished=copy.deepcopy(frames);unfinished[-2]['choices'][0]['finish_reason']=None;bad.append(self.encode_sse(unfinished))
        after=copy.deepcopy(frames);after.insert(-1,copy.deepcopy(frames[1]));bad.append(self.encode_sse(after))
        for raw in bad:
            with self.subTest(raw_sha=r.sha(raw)),self.assertRaises(ValueError):assistant_content(raw,'text/event-stream')

    def test_sse_identity_role_index_and_duplicate_keys_refused(self):
        for field,value in [('id','DIFFERENT_AUTHORED_STREAM'),('model','wrong-model')]:
            frames=self.sse_frames();frames[1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):assistant_content(self.encode_sse(frames),'text/event-stream')
        for delta in [{'role':'user','content':'AUTHORED'},{'content':42}]:
            frames=self.sse_frames();frames[1]['choices'][0]['delta']=delta
            with self.assertRaises(ValueError):assistant_content(self.encode_sse(frames),'text/event-stream')
        frames=self.sse_frames();frames[1]['choices'][0]['index']=True
        with self.assertRaises(ValueError):assistant_content(self.encode_sse(frames),'text/event-stream')
        with self.assertRaises(ValueError):assistant_content(b'data: {"id":"a","id":"b"}\n\ndata: [DONE]\n\n','text/event-stream')

    def test_sse_role_may_be_omitted_but_never_rewritten(self):
        frames=self.sse_frames();frames[0]['choices'][0]['delta'].pop('role')
        frames[-2]['choices'][0].pop('delta')
        text,usage,origin=assistant_content(self.encode_sse(frames),'text/event-stream')
        self.assertEqual(text,self.text);self.assertEqual(usage,self.receipt['usage'])
        self.assertEqual(origin,'worker_sse_role_unspecified_delta_content')

    def test_sse_usage_must_match_bound_settled_receipt(self):
        self.install_sse();self.receipt['usage']={'input_tokens':4,'output_tokens':2,'total_tokens':6}
        with sqlite3.connect(self.db) as c:c.execute('UPDATE calls SET charged=?,receipt=?',(3600,json.dumps(self.receipt)))
        with self.assertRaises(ValueError):self.verify()

    def test_streamed_follower_integration(self):
        self.install_sse();self.test_follower_integration_labels_and_exact_selection_only()

    def test_exact_current_wire_receipt_selection_and_readonly(self):
        before=self.db.read_bytes(); out=self.verify()
        self.assertEqual(out['model_excerpt'],self.text)
        self.assertNotIn('WITHHELD_FIXTURE_NOT_SELECTED',out['model_excerpt'])
        self.assertEqual(self.db.read_bytes(),before)
        self.assertNotIn('source_received_utc',out)

    def test_no_automatic_unreviewed_prose(self):
        with self.assertRaises(ValueError):self.verify(approvals=set())

    def test_supervisor_raw_provenance_not_yet_supported(self):
        self.put(self.selection,dict(self.manifest,source_relative_path='run/supervisor-wire/'+'a'*64+'.json'))
        with self.assertRaises(ValueError):self.verify()

    def test_follower_must_opt_in_to_exact_approval_path(self):
        feed=self.root/'safe-display.jsonl';start=self.root/'follower-start.json'
        self.put(start,{'schema':'pex-recorder-follower/v1','run_id':self.root.name,'qualification':'setup_only_no_inference','authored_fixture':True,
            'started_utc':r.utc(),'feed_path_sha256':r.sha(str(feed).encode()),
            'source_code_sha256':r.sha(Path(r.__file__).read_bytes())})
        with SafeFeedWriter(run_id=self.root.name,feed_path=feed,follower_start_path=start) as writer:
            with self.assertRaises(ValueError):writer.emit_reviewed_excerpt(self.verify(),approvals=self.approvals)
        self.assertEqual(feed.read_bytes(),b'')

    def test_changed_source_or_selection_or_wrong_run_refused(self):
        for key,value in [('source_sha256','2'*64),('model_excerpt_sha256','3'*64),
                          ('run_id','old-run'),('config_sha256','4'*64),
                          ('source_relative_path','../private.json'),('end_byte',True),
                          ('schema','replay'),('reviewed_utc','2020-01-01T00:00:00Z')]:
            self.put(self.selection,dict(self.manifest,**{key:value}))
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify()
        self.put(self.selection,self.manifest)
        self.put(self.wire,dict(self.source,arm='pex'))
        with self.assertRaises(ValueError):self.verify()

    def test_uncertain_or_mismatched_receipt_refused(self):
        for state,receipt in [('uncertain',self.receipt),('settled_raw_wire',dict(self.receipt,response_sha256='0'*64)),
                              ('settled_raw_wire',dict(self.receipt,wire_evidence={'path':'wrong','sha256':self.source_sha}))]:
            with sqlite3.connect(self.db) as c:c.execute('UPDATE calls SET state=?,receipt=?',(state,json.dumps(receipt)))
            with self.subTest(state=state),self.assertRaises(ValueError):self.verify()

    def test_private_symlink_or_permissions_refused(self):
        self.wire.chmod(0o644)
        with self.assertRaises(ValueError):self.verify()
        self.wire.chmod(0o600); backup=self.wire.with_suffix('.backup');self.wire.rename(backup);self.wire.symlink_to(backup)
        with self.assertRaises(ValueError):self.verify()

    def test_after_terminal_refused(self):
        self.put(self.root/'launcher-terminal.json',{'AUTHORED_TERMINAL':True})
        with self.assertRaises(ValueError):self.verify()

    def test_no_replay_label_or_undated_excerpt(self):
        fields=self.verify()
        event=dict(fields,schema=r.SCHEMA,run_id=self.root.name,seq=1,at_utc=r.utc(),
                   event='worker_response',qualification='replay')
        with self.assertRaises(ValueError):r.validate(event,run_id=self.root.name,expected_seq=1,not_before=self.started,now=time.time(),approvals=self.approvals,authored_fixture=True)
        event['qualification']='authored_fixture_reviewed_excerpt';event.pop('reviewed_utc')
        with self.assertRaises(ValueError):r.validate(event,run_id=self.root.name,expected_seq=1,not_before=self.started,now=time.time(),approvals=self.approvals,authored_fixture=True)

    def test_one_writer_deduplicates_and_refuses_late_injection(self):
        feed=self.root/'safe-display.jsonl';start=self.root/'follower-start.json'
        self.put(start,{'schema':'pex-recorder-follower/v1','run_id':self.root.name,'qualification':'setup_only_no_inference','authored_fixture':True,
            'started_utc':dt.datetime.fromtimestamp(self.started,dt.timezone.utc).isoformat().replace('+00:00','Z'),
            'excerpt_mode':'root_reviewed_worker_wire','approvals_path_sha256':r.sha(str((self.root/'reviewed-excerpts.json').resolve()).encode()),
            'feed_path_sha256':r.sha(str(feed).encode()),'source_code_sha256':r.sha(Path(r.__file__).read_bytes())})
        with SafeFeedWriter(run_id=self.root.name,feed_path=feed,follower_start_path=start) as writer:
            seen=set();drain_approved(self.root,writer,config_sha=self.config,seen=seen,now=time.time())
            drain_approved(self.root,writer,config_sha=self.config,seen=seen,now=time.time())
            self.assertEqual(writer.seq,1)
            fields=self.verify();self.put(self.root/'launcher-terminal.json',{'AUTHORED_TERMINAL':True})
            with self.assertRaises(ValueError):writer.emit_reviewed_excerpt(fields,approvals=self.approvals)
            writer.emit(event='run_terminal',qualification='terminal_inconclusive',source_sha256='9'*64,terminal='outcome_inconclusive')
            with self.assertRaises(ValueError):writer.emit_reviewed_excerpt(fields,approvals=self.approvals)
        self.assertEqual([json.loads(s)['seq'] for s in feed.read_text().splitlines()],[1,2])

    def test_follower_integration_labels_and_exact_selection_only(self):
        feed=self.root/'safe-display.jsonl';out=self.root/'display'
        command=[sys.executable,'-B',str(Path(r.__file__)),'follow','--run-id',self.root.name,
            '--feed',str(feed),'--output-dir',str(out),'--approvals',str(self.root/'reviewed-excerpts.json'),'--authored-fixture','--max-seconds','10']
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+3
            while not (out/'follower-start.json').exists() and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue((out/'follower-start.json').exists())
            # Root review occurs after this fresh follower, not a replay.
            self.manifest['reviewed_utc']=r.utc();self.put(self.selection,self.manifest)
            with SafeFeedWriter(run_id=self.root.name,feed_path=feed,follower_start_path=out/'follower-start.json') as writer:
                drain_approved(self.root,writer,config_sha=self.config,seen=set(),now=time.time())
                writer.emit(event='run_terminal',qualification='terminal_inconclusive',source_sha256='9'*64,terminal='outcome_inconclusive')
            stdout,stderr=proc.communicate(timeout=4)
            self.assertEqual(proc.returncode,0);self.assertEqual(stderr,'')
            self.assertIn('SIMULATED / REVIEW-DELAYED EXACT EXCERPT',stdout)
            self.assertNotIn('LIVE CURRENT RUN',stdout)
            self.assertIn('Source received UTC: unavailable',stdout)
            self.assertIn('REPLAY UNSUPPORTED',stdout);self.assertIn(self.text,stdout)
            self.assertNotIn('WITHHELD_FIXTURE_NOT_SELECTED',stdout)
            self.assertEqual(json.loads((out/'follower-terminal.json').read_text())['accepted_records'],2)
        finally:
            if proc.poll() is None:proc.terminate();proc.wait(timeout=3)


if __name__=='__main__':unittest.main()

class CumulativeUsageRecorderTests(unittest.TestCase):
    def frames(self):
        def f(n,finish=None,content=''):
            return {'id':'AUTHORED-CUMULATIVE','model':WORKER_MODEL,'choices':[{'index':0,'delta':{'content':content},'finish_reason':finish}], 'usage':{'prompt_tokens':3,'completion_tokens':n,'total_tokens':3+n,'completion_tokens_details':{'reasoning_tokens':n}}}
        return [f(0,content='A'),f(1,content='B'),f(2,'stop',content='C'),{'id':'AUTHORED-CUMULATIVE','model':WORKER_MODEL,'choices':[],'usage':{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5,'completion_tokens_details':{'reasoning_tokens':2},'prompt_tokens_details':{'cached_tokens':0}}}]
    def encode(self,fs):return (''.join('data: '+json.dumps(f)+'\n\n' for f in fs)+'data: [DONE]\n\n').encode()
    def test_monotonic_interims_exact_content(self):
        text,usage,_=assistant_content(self.encode(self.frames()),'text/event-stream')
        self.assertEqual(text,'ABC');self.assertEqual(usage,{'input_tokens':3,'output_tokens':2,'total_tokens':5})
    def test_conflicting_cumulative_streams_rejected(self):
        bad=[]
        a=self.frames();a[1]['usage']['prompt_tokens']=4;a[1]['usage']['total_tokens']=5;bad.append(a)
        a=self.frames();a[1]['usage']['completion_tokens']=3;a[1]['usage']['total_tokens']=6;bad.append(a)
        a=self.frames();a[-1]['usage']['completion_tokens']=3;a[-1]['usage']['total_tokens']=6;bad.append(a)
        a=self.frames();a[-1]['usage']['completion_tokens_details']['reasoning_tokens']=1;bad.append(a)
        a=self.frames();a[1]['usage'].pop('completion_tokens_details');bad.append(a)
        a=self.frames();a.insert(-1,copy.deepcopy(a[1]));bad.append(a)
        a=self.frames();a.append({'id':'AUTHORED-CUMULATIVE','model':WORKER_MODEL,'choices':[]});bad.append(a)
        a=self.frames();a.insert(0,{'id':'AUTHORED-CUMULATIVE','model':WORKER_MODEL,'choices':[]});bad.append(a)
        for fs in bad:
            with self.subTest(raw=fs),self.assertRaises(ValueError):assistant_content(self.encode(fs),'text/event-stream')
