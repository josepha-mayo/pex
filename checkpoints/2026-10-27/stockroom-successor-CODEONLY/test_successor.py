"""Pure authored composition tests. No provider, SDK, real worker or VM construction."""
import asyncio
from dataclasses import dataclass
from datetime import datetime,timezone,timedelta
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from successor_admission import RootAdmission,AdmissionRefused,load,REQUIRED_SOURCES,TASK_SHA
from successor_runner import _compose,run_successor
TASK=Path(__file__).resolve().parent.parent/'pex-hard-task-candidate-20261027-1421'
def sha(b):return hashlib.sha256(b).hexdigest()
def write(p,b):
    p.write_bytes(b);p.chmod(0o600)
    return {'path':str(p),'sha256':sha(b)}
class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.approval_patch = patch('successor_admission.APPROVED_PAIR_REF', 'AUTHORED-RETRY')
        self.approval_patch.start()
        self.addCleanup(self.approval_patch.stop)
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.now=datetime.now(timezone.utc);expiry=(self.now+timedelta(hours=1)).isoformat()
        dummy=write(self.root/'source.py',b'# authored no-op source\n')
        key=write(self.root/'key',b'NOT-A-REAL-CREDENTIAL')
        ca=write(self.root/'ca.pem',b'AUTHORED CA NOT USED')
        supervisor=write(self.root/'supervisor-config.json',b'{}')
        self.prior={'schema':'pex.cumulative-predecessor.v1','closed':True,'worker_charged_nano_usd':{'baseline':100,'pex':200},'supervisor_charged_nano_usd':300,'compute_upper_bound_nano_usd':19965000,'closed_evidence_sha256':'a'*64}
        pred=write(self.root/'predecessor.json',json.dumps(self.prior).encode())
        self.cfg={'schema':'pex.stockroom-successor.v1','run_id':'authored','approval_ref':'AUTHORED-RETRY','funding_approval_ref':'AUTHORED-FUNDING','expires_at':expiry,'package_path':str(TASK),'output_dir':str(self.root/'output'),'nebius_key':key,'e2b_key':key,'binary':dummy,'modules_path':str(self.root),'sources':{n:dummy for n in REQUIRED_SOURCES},'predecessor':pred,'supervisor':{'entry':dummy,'config':supervisor},'network':{'proxy_sha256':sha(b'http://authored.invalid:8080'),'ca':ca}}
        self.env=patch.dict(os.environ,{'HTTPS_PROXY':'http://authored.invalid:8080','SSL_CERT_FILE':ca['path']});self.env.start()
        self.pin()
    def pin(self):
        self.path=self.root/'config.json';p=write(self.path,json.dumps(self.cfg).encode())
        self.admission=RootAdmission(p['sha256'],self.cfg['approval_ref'],self.cfg['funding_approval_ref'],self.cfg['expires_at'],self.cfg['predecessor']['sha256'],self.cfg['supervisor']['entry']['sha256'])
    def tearDown(self):self.env.stop();self.tmp.cleanup()
    def test_closed_gate_precedes_every_private_read(self):
        with patch('successor_admission.APPROVED_PAIR_REF', None), patch('successor_admission.private_read', side_effect=AssertionError('must not read credentials/config')):
            with self.assertRaisesRegex(AdmissionRefused, 'new_pair_approval_pending'):
                load(self.path, self.admission)
    def test_caller_cannot_substitute_other_approval(self):
        with patch('successor_admission.APPROVED_PAIR_REF', 'DIFFERENT-OWNER-APPROVAL'), patch('successor_admission.private_read', side_effect=AssertionError('must not read')):
            with self.assertRaisesRegex(AdmissionRefused, 'new_pair_approval_pending'):
                load(self.path, self.admission)
    def test_valid_authored_data_admission(self):
        cfg,prior=load(self.path,self.admission,now=self.now)
        self.assertEqual(cfg,self.cfg);self.assertEqual(prior,self.prior)
    def test_missing_root_refused(self):
        with self.assertRaises(AdmissionRefused):load(self.path,None)
    def test_config_digest_change_refused(self):
        self.path.write_text('{}')
        with self.assertRaises((AdmissionRefused,KeyError)):load(self.path,self.admission)
    def test_expired_config_refused(self):
        with self.assertRaises(AdmissionRefused):load(self.path,self.admission,now=self.now+timedelta(hours=2))
    def test_proxy_or_CA_change_refused(self):
        with patch.dict(os.environ,{'HTTPS_PROXY':'http://changed.invalid:8080'}):
            with self.assertRaises(AdmissionRefused):load(self.path,self.admission)
    def test_source_change_refused(self):
        Path(self.cfg['sources']['controller']['path']).write_text('changed')
        with self.assertRaises(AdmissionRefused):load(self.path,self.admission)
    def test_predecessor_mismatch_refused(self):
        a=RootAdmission(self.admission.config_sha256,self.admission.approval_ref,self.admission.funding_approval_ref,self.admission.expires_at,'0'*64,self.admission.supervisor_entry_sha256)
        with self.assertRaises(AdmissionRefused):load(self.path,a)
    def test_overbudget_or_bool_prior_refused(self):
        for bad in (350000001,True,-1):
            self.prior['worker_charged_nano_usd']['baseline']=bad
            self.cfg['predecessor']=write(self.root/'predecessor.json',json.dumps(self.prior).encode());self.pin()
            with self.assertRaises(AdmissionRefused):load(self.path,self.admission)
    def test_actual_missing_supervisor_factory_gate(self):
        # Reach the entry-schema check using an inert, correctly pinned module.
        with patch('successor_runner.assert_import_sources'), patch('successor_runner.runtime_dependencies',side_effect=AssertionError('resources forbidden')), patch('successor_runner.importlib.import_module',return_value=SimpleNamespace(initialize_process=lambda:None)):
            with self.assertRaisesRegex(AdmissionRefused,'separately_admitted_supervisor_successor_unavailable'):
                asyncio.run(run_successor(self.path,self.admission))
        self.assertFalse(Path(self.cfg['output_dir']).exists())
    def test_supervisor_close_failure_prevents_terminal_success(self):
        code=b"SUCCESSOR_ENTRY_SCHEMA='pex.managed-supervisor-successor.v1'\nclass Manager:\n def revalidate(self): pass\n def model_factory(self,*a): raise AssertionError('no provider')\n def summary(self): return {}\n def close(self): raise RuntimeError('authored close failure')\ndef admit_successor(**kwargs): return Manager()\n"
        self.cfg['supervisor']['entry']=write(self.root/'successor_entry.py',code);self.pin()
        async def composed(*args,**kwargs):
            output=args[6];(output/'report.json').write_text('{"comparison_complete":true}')
            return {'comparison_complete':True}
        with patch('successor_runner.assert_import_sources'), patch('successor_runner.runtime_dependencies',return_value=object()), patch('successor_runner._compose',side_effect=composed), patch('successor_runner.importlib.import_module',return_value=SimpleNamespace(initialize_process=lambda:None)):
            with self.assertRaisesRegex(RuntimeError,'authored close failure'):
                asyncio.run(run_successor(self.path,self.admission))
        output=Path(self.cfg['output_dir'])
        self.assertTrue((output/'report.json').exists())
        self.assertFalse((output/'terminal-failure.json').exists())
        self.assertTrue((output/'supervisor-cleanup-unconfirmed.json').exists())
        self.assertFalse((output/'terminal.json').exists())

    def test_missing_successor_factory_blocks_before_resources(self):
        # Stop before runtime import: module origins cannot match authored dummy pins.
        with patch('successor_runner.runtime_dependencies',side_effect=AssertionError('must not construct runtime')):
            with self.assertRaises(AdmissionRefused):asyncio.run(run_successor(self.path,self.admission))
        self.assertFalse(Path(self.cfg['output_dir']).exists())

@dataclass
class Budget:
    calls:int
    input_tokens:object
    output_tokens:int
    active_seconds:int
class CompositionTests(unittest.TestCase):
    def test_authored_composition_and_cumulative_handoff(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);out.chmod(0o700)
            key=write(out/'key',b'AUTHORED-INERT')
            cfg={'package_path':str(TASK),'e2b_key':key,'nebius_key':key,'predecessor':{'sha256':'a'*64},'funding_approval_ref':'AUTHORED-FUNDING','binary':{'path':'/never/execute'},'modules_path':'/never/import'}
            prior={'worker_charged_nano_usd':{'baseline':101,'pex':202},'supervisor_charged_nano_usd':303,'compute_upper_bound_nano_usd':19965000,'closed_evidence_sha256':'b'*64}
            seen={};calls=[]
            class Compute:
                def __init__(self,path,**kw):seen['compute']=kw
                def total(self):return 19965000
                def close(self):calls.append('compute_close')
            class Funding:
                def __init__(self,path,**kw):seen.setdefault('funding',[]).append(kw)
                def summary(self):return {'charged_nano_usd':prior['worker_charged_nano_usd']}
                def close(self):calls.append('funding_close')
            class Pool:
                def __init__(self,*a,**kw):seen['pool']=kw
                def create(self,*a):raise AssertionError('no VM creation in authored test')
                def close(self):calls.append('pool_close')
            class Worker:
                def __init__(self,**kw):seen['worker']=kw;self.states={'baseline':{'stopped':True,'mcp_revoked':True},'pex':{'stopped':True,'mcp_revoked':False}}
                async def cleanup(self):calls.append('worker_cleanup')
            class Review:
                def __init__(self,*a,**kw):seen['review']=kw
            class Grade:
                def __init__(self,**kw):seen['grade']=kw
            async def run_pair(arms,worker,review,grade,**kw):
                seen['arms']=arms;seen['pair']=kw
                self.assertTrue(kw['admission'].authorize(arms,kw['budget']))
                self.assertTrue(seen['grade']['revoked']('baseline'));self.assertFalse(seen['grade']['revoked']('pex'))
                return {'arms':{'baseline':{'status':'natural_stop','protected_grade':{'status':'graded_with_limits'}},'pex':{'status':'no_intervention','protected_grade':{'status':'inconclusive'}}}}
            from stockroom_task import stage,FILES,PUBLIC_CHECK_COMMAND
            deps=SimpleNamespace(Compute=Compute,Funding=Funding,Pool=Pool,Worker=Worker,Review=Review,Grade=Grade,Budget=Budget,run_pair=run_pair,stage=stage,files=FILES,public_check=PUBLIC_CHECK_COMMAND,request_builder=lambda p:'AUTHORED-BUILDER',Sandbox='NEVER-CONSTRUCTED',pricing_sha='c'*64)
            supervisor=SimpleNamespace(summary=lambda:{'prior':303},model_factory=lambda *a:None)
            report=asyncio.run(_compose(cfg,prior,'d'*64,supervisor,lambda:calls.append('revalidate'),deps,out,mode='authored-only'))
            self.assertEqual(seen['compute']['prior_upper_bound_nano_usd'],19965000)
            self.assertIs(seen['pool']['cumulative_budget'].__class__,Compute)
            self.assertTrue(all(f['prior_charged_nano_usd']==prior['worker_charged_nano_usd'] and f['predecessor_sha256']=='a'*64 for f in seen['funding']))
            self.assertTrue(all(f['arm_budget_nano_usd']==350000000 and f['phase_limit_nano_usd']==339918200 for f in seen['funding']))
            self.assertEqual(seen['worker']['task_profile'],'stockroom-v1')
            self.assertEqual(seen['worker']['public_check_command'],PUBLIC_CHECK_COMMAND)
            self.assertEqual(report['arms']['pex']['status'],'grading_inconclusive');self.assertFalse(report['comparison_complete'])
            self.assertFalse(report['presentation_eligible']);self.assertIsNone(report['pex_lift'])
            self.assertEqual(report['predecessor_sha256'],'a'*64)
            self.assertEqual(calls.count('funding_close'),2);self.assertIn('worker_cleanup',calls);self.assertIn('compute_close',calls)
            self.assertTrue((out/'report.json').exists())
            self.assertNotIn('protected',str(list((out/'staged/workers').rglob('*'))))

if __name__=='__main__':unittest.main()
