"""Authored offline monitor/worker fixtures. Never a model or provider response."""
import base64
import datetime as dt
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).parent))
import record_support as r
from reviewed_excerpts import verify_selection, drain_approved
from supervisor_excerpts import MODEL,ENDPOINT,PROTOCOL_PINS,FINAL,final_arguments,monitor_content
from safe_feed_writer import SafeFeedWriter
import test_reviewed_excerpts as worker_fixtures


class SupervisorExcerptTests(unittest.TestCase):
    def setUp(self):
        self.f=worker_fixtures.ReviewedExcerptTests()
        if hasattr(self,'external_fixture_root'):self.f.external_fixture_root=self.external_fixture_root
        self.f.setUp();self.root=self.f.root
        self.f.put(self.root/'pair.json',{'AUTHORED_FIXTURE_ONLY':True,'sources':{k:{'sha256':v} for k,v in PROTOCOL_PINS.items()}})
        self.f.config=r.sha((self.root/'pair.json').read_bytes());self.f.source['config_sha256']=self.f.config
        self.f.manifest['config_sha256']=self.f.config
        with sqlite3.connect(self.f.db) as c:c.execute('UPDATE config SET digest=?',(self.f.config,))
        self.f.install_sse()
        self.db=self.root/'run/supervisor.sqlite';(self.root/'run/supervisor-wire').mkdir(mode=0o700)
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE config(ir,outr)');c.execute('INSERT INTO config VALUES (300,900)')
            c.execute('CREATE TABLE approved_route_identity(fingerprint,endpoint,model,role)')
            c.execute('CREATE TABLE calls(id,route,reserve,charged,state,receipt)')
            c.execute('CREATE TABLE staged_supervisor_wire(invocation_id,kind,role,route,body_sha256,artifact_path,artifact_sha256)')
        self.db.chmod(0o600);self.install_monitor('planner')

    def tearDown(self):self.f.tearDown()

    def install_monitor(self,role,kind='final_tool_arguments'):
        invocation='authored-'+role;route=r.sha(role.encode())
        self.excerpt='AUTHORED '+role.upper()+' FIXTURE — NOT REAL MONITOR INFERENCE'
        args={'action_type':'NOOP','rationale':self.excerpt} if role=='planner' else {'approved':False,'rationale':self.excerpt}
        # Noncanonical whitespace/key ordering must survive exact selection.
        self.arguments=json.dumps(args,ensure_ascii=False,indent=1)
        message={'role':'assistant','content':None,'tool_calls':[{'id':'authored_call','type':'function',
                 'function':{'name':FINAL[role],'arguments':self.arguments}}]}
        if kind=='assistant_content':message={'role':'assistant','content':self.excerpt}
        body={'object':'chat.completion','model':MODEL,'choices':[{'index':0,'finish_reason':'tool_calls' if kind=='final_tool_arguments' else 'stop','message':message}],
              'usage':{'prompt_tokens':3,'completion_tokens':2,'total_tokens':5}}
        body_raw=r.canonical(body).encode();now=time.time()
        captured=dt.datetime.fromtimestamp(now-1,dt.timezone.utc).isoformat()
        source={'schema':'pex.staged.private-supervisor-wire.v1','kind':'response','run_id':self.root.name,
            'config_sha256':self.f.config,'role':role,'invocation_id':invocation,'route_fingerprint':route,'model_id':MODEL,
            'endpoint':ENDPOINT,'body_sha256':r.sha(body_raw),'raw_body_base64':base64.b64encode(body_raw).decode(),
            'HTTP_status':200,'content_type':'application/json','captured_at_utc':captured,'complete_bounded_body':True,
            'request_headers_captured':False,'qualification':'AUTHORED FIXTURE ONLY; not received/server time'}
        artifact=self.root/'run/supervisor-wire'/(r.sha(r.canonical([invocation,'response']).encode())+'.json')
        self.f.put(artifact,source);digest=r.sha(artifact.read_bytes())
        receipt={'invocation_id':invocation,'route_fingerprint':route,'model_id':MODEL,'role':role,
            'attempts':1,'dispatch_state':'response_complete','outcome':'succeeded','reason':'validated_response','http_status':200,
            'usage':{'input_tokens':3,'output_tokens':2,'total_tokens':5}}
        with sqlite3.connect(self.db) as c:
            c.execute('DELETE FROM calls WHERE id=?',(invocation,));c.execute('DELETE FROM staged_supervisor_wire WHERE invocation_id=?',(invocation,))
            c.execute('DELETE FROM approved_route_identity WHERE fingerprint=?',(route,))
            c.execute('INSERT INTO approved_route_identity VALUES (?,?,?,?)',(route,ENDPOINT,MODEL,role))
            c.execute('INSERT INTO calls VALUES (?,?,?,?,?,?)',(invocation,route,262144*300+4096*900,2700,'settled_raw_wire',json.dumps(receipt)))
            # Request metadata proves prior capture; the request file deliberately
            # does not exist, so this test catches any request-body read.
            c.execute('INSERT INTO staged_supervisor_wire VALUES (?,?,?,?,?,?,?)',(invocation,'request',role,route,'a'*64,str(self.root/'MUST_NOT_READ_REQUEST'),'b'*64))
            c.execute('INSERT INTO staged_supervisor_wire VALUES (?,?,?,?,?,?,?)',(invocation,'response',role,route,r.sha(body_raw),str(artifact),digest))
        selected=self.arguments if kind=='final_tool_arguments' else self.excerpt
        manifest={'schema':'pex-reviewed-supervisor-selection/v1','run_id':self.root.name,'config_sha256':self.f.config,
            'source_relative_path':str(artifact.relative_to(self.root)),'source_sha256':digest,'model_excerpt_sha256':r.sha(selected.encode()),
            'start_byte':0,'end_byte':len(selected.encode()),'reviewed_utc':r.utc(),'selection_kind':kind}
        path=self.f.inbox/('reviewed-'+role+'.json');self.f.put(path,manifest)
        approvals=json.loads((self.root/'reviewed-excerpts.json').read_text());approvals['approvals'].append(
            dict(run_id=self.root.name,source_sha256=digest,model_excerpt_sha256=manifest['model_excerpt_sha256']))
        self.f.put(self.root/'reviewed-excerpts.json',approvals)
        self.manifest=manifest;self.path=path;self.artifact=artifact;self.source=source;self.receipt=receipt;self.invocation=invocation

    def verify(self):
        return verify_selection(self.root,self.path,run_id=self.root.name,config_sha=self.f.config,
            approvals=r.read_approvals(self.root/'reviewed-excerpts.json'),started=self.f.started,now=time.time())

    def test_planner_final_exact_arguments_and_no_request_read(self):
        before=self.db.read_bytes();out=self.verify()
        self.assertEqual(out['model_excerpt'],self.arguments);self.assertEqual(out['supervisor_role'],'planner')
        self.assertEqual(out['excerpt_origin'],'supervisor_json_final_tool_arguments');self.assertEqual(before,self.db.read_bytes())

    def test_verifier_final_and_plain_monitor_text(self):
        self.install_monitor('verifier');self.assertEqual(self.verify()['supervisor_role'],'verifier')
        self.install_monitor('planner','assistant_content');self.assertEqual(self.verify()['model_excerpt'],self.excerpt)

    def test_auxiliary_state_route_and_receipt_binding_refused(self):
        for sql,args in [("UPDATE calls SET state='uncertain'",()),
                         ('UPDATE staged_supervisor_wire SET artifact_sha256=? WHERE kind=\'response\'',('0'*64,)),
                         ('DELETE FROM staged_supervisor_wire WHERE kind=\'request\'',())]:
            with sqlite3.connect(self.db) as c:c.execute(sql,args)
            with self.assertRaises(ValueError):self.verify()
            self.install_monitor('planner')

    def test_archive_time_is_observation_not_received_and_ordered(self):
        fields=self.verify();self.assertIn('source_captured_utc',fields);self.assertNotIn('source_received_utc',fields)
        self.manifest['reviewed_utc']='2020-01-01T00:00:00Z';self.f.put(self.path,self.manifest)
        with self.assertRaises(ValueError):self.verify()

    def test_narrow_final_argument_validation(self):
        for value,role in [({'action_type':'NOOP','rationale':'AUTHORED','extra':1},'planner'),
                           ({'approved':1,'rationale':'AUTHORED'},'verifier'),
                           ({'action_type':'NOOP','rationale':'AUTHORED','confidence':True},'planner')]:
            with self.assertRaises(ValueError):final_arguments(json.dumps(value),role)
        with self.assertRaises(ValueError):final_arguments('{"action_type":"NOOP","rationale":"AUTHORED","confidence":1e999}','planner')

    def test_monitor_requires_root_approval_and_no_after_terminal(self):
        with self.assertRaises(ValueError):verify_selection(self.root,self.path,run_id=self.root.name,config_sha=self.f.config,
            approvals=set(),started=self.f.started,now=time.time())
        self.f.put(self.root/'launcher-terminal.json',{'AUTHORED_ONLY':True})
        with self.assertRaises(ValueError):self.verify()

    def test_full_authored_worker_planner_verifier_driver(self):
        import qualification_fixture
        with tempfile.TemporaryDirectory(prefix='AUTHORED-recorder-integration-') as name:
            root=Path(name)/'authored-recorder-offline-qualification';root.mkdir(mode=0o700)
            session=root/'recording-live';session.mkdir();(session/'video').mkdir()
            command=[sys.executable,'-B',str(Path(r.__file__)),'follow','--run-id',root.name,
                '--feed',str(root/'safe-display.jsonl'),'--output-dir',str(session/'display'),
                '--approvals',str(root/'reviewed-excerpts.json'),'--authored-fixture','--max-seconds','10']
            proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            sleep=time.sleep
            try:
                deadline=time.monotonic()+3
                while not (session/'display/follower-start.json').exists() and time.monotonic()<deadline:sleep(.01)
                # This is offline authored capture-readiness metadata, not a video.
                # Delay >1s so fixture archive observation is after follower start.
                sleep(1.05)
                (session/'video/capture-start.json').write_text(json.dumps({'qualification':'authored_fixture_window_capture_NOT_REAL_INFERENCE','max_seconds':25}))
                (session/'video/capture-ready.json').write_text('{"AUTHORED_OFFLINE_ONLY":true}')
                with mock.patch.object(qualification_fixture.time,'sleep',lambda seconds:sleep(min(seconds,.02))):
                    qualification_fixture.run(root)
                deadline=time.monotonic()+3
                trace=session/'display/safe-trace.jsonl'
                while len(trace.read_text().splitlines())<3 and time.monotonic()<deadline:sleep(.02)
                proc.terminate();stdout,stderr=proc.communicate(timeout=3)
                self.assertEqual(stderr,'');self.assertIn('AUTHORED FIXTURE — NOT REAL INFERENCE',stdout)
                self.assertNotIn('LIVE CURRENT RUN',stdout)
                self.assertIn('AUTHORED PLANNER FIXTURE',stdout);self.assertIn('AUTHORED VERIFIER FIXTURE',stdout)
                records=[json.loads(s) for s in trace.read_text().splitlines()]
                self.assertEqual([x['event'] for x in records],['worker_response','supervisor_response','supervisor_response'])
                self.assertTrue(all(x['qualification']=='authored_fixture_reviewed_excerpt' for x in records))
                self.assertFalse((root/'launcher-terminal.json').exists())
            finally:
                if proc.poll() is None:proc.terminate();proc.wait(timeout=3)


if __name__=='__main__':unittest.main()
