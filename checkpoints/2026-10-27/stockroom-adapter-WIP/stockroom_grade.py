"""Post-stop, post-MCP-revocation SAME-VM isolated-copy grader.
No candidate code executes on controller. Not an adversarial sandbox guarantee.
"""
import asyncio
import base64
import json
from pathlib import Path,PurePosixPath
import shlex
import uuid
from stockroom_task import TASK,FILES,PROTECTED,load_package,package_contract,digest,encoded
LIMITS=('same_vm_not_adversarially_hardened','candidate_can_inspect_grading_process','escaped_background_processes_not_proven_absent','default_user_sudo_not_removed','not_original_bwrap_grader','no_candidate_execution_on_controller_or_as_root')

class RemoteGrade:
    def __init__(self,remotes,package,stopped,*,revoked,evidence_sink=None,saved_phase0=None):
        if evidence_sink is not None and not callable(evidence_sink):raise ValueError('trusted_evidence_sink_required')
        if saved_phase0 is not None and not callable(saved_phase0):raise ValueError("trusted_phase0_source_required")
        self.saved_phase0=saved_phase0;self.phase0_used=set()
        self.evidence_sink=evidence_sink
        self.remotes,self.stopped,self.revoked=remotes,stopped,revoked
        data=load_package(package);contract=package_contract(package)
        self.task=contract['task'];self.check_count=contract['protected_check_count']
        self.public={n:data['public/'+n] for n in FILES}
        self.protected={Path(n).name:data[n] for n in PROTECTED}
        self.exporter=(Path(__file__).parent/'export_candidate.py').read_text()
        self.verifier=(Path(__file__).parent/'grade_upload_verify.py').read_text()
        self.used=set()
    async def grade(self,arm):
        c=arm['condition']
        if c in self.used or self.stopped(c) is not True or self.revoked(c) is not True:raise ValueError('single_post_stop_post_revoke_grade_required')
        self.used.add(c)
        return await asyncio.to_thread(self._grade,c)
    async def grade_phase0(self,arm):
        c=arm['condition']
        if (c!='pex' or c not in self.used or c in self.phase0_used or self.saved_phase0 is None
                or any(self.stopped(a) is not True or self.revoked(a) is not True for a in ('baseline','pex'))):
            raise ValueError('single_phase0_after_all_workers_revoked_required')
        self.phase0_used.add(c)
        # Trusted caller validates the durable archive pin/config before returning.
        actual=self._decode_export(self.saved_phase0(c))
        return await asyncio.to_thread(self._grade,c,actual,'pre_intervention_phase0')
    def _export(self,remote):
        result=remote.run('python3 -I -B -c '+shlex.quote(self.exporter),timeout=15)
        if result['exit_code']!=0:raise ValueError('candidate_export_inconclusive')
        if len(result['stdout'].encode())>200000:raise ValueError('candidate_export_bound')
        return self._decode_export(json.loads(result['stdout']))
    def _decode_export(self,obj):
        if len(json.dumps(obj).encode())>200000:raise ValueError('candidate_export_bound')
        if type(obj) is not dict or set(obj)!={'schema','files'} or obj['schema']!='pex.stockroom-export.v1' or type(obj['files']) is not dict:raise ValueError('invalid_export')
        required={n for n in FILES if n=='TASK.md' or n.startswith('tests/')}
        if not required<=set(obj['files']) or len(obj['files'])>128:raise ValueError('export_file_set')
        actual={}
        for name,value in obj['files'].items():
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or str(p)!=name or '\x00' in name or (name not in FILES and p.parts[0] not in ('stockroom','tests')):raise ValueError('invalid_export_path')
            if type(value) is not str:raise ValueError('invalid_export_encoding')
            actual[name]=base64.b64decode(value,validate=True)
        if sum(map(len,actual.values()))>131072:raise ValueError('candidate_size_bound')
        return actual
    def _quiescent(self,condition,snapshot_kind):
        arms=('baseline','pex') if snapshot_kind=='pre_intervention_phase0' else (condition,)
        return all(self.stopped(c) is True and self.revoked(c) is True for c in arms)
    def _grade(self,condition,actual_override=None,snapshot_kind="final"):
        report={'schema':'pex.stockroom-same-vm-grade.v1','task':self.task,'condition':condition,'status':'inconclusive','presentation_eligible':False,'task_tests_measured':False,'anti_tamper_limits':list(LIMITS),'protected_input_sha256':{n:digest(b) for n,b in self.protected.items()}}
        report['snapshot_kind']=snapshot_kind
        evidence_condition=condition if snapshot_kind=='final' else condition+'-phase0'
        try:
            # Recheck before any snapshot/grading action, not only await boundary.
            if not self._quiescent(condition,snapshot_kind):raise ValueError('stop_or_revocation_changed')
            remote=self.remotes[condition];actual=self._export(remote) if actual_override is None else actual_override
            hashes={n:digest(b) for n,b in actual.items()}
            report['candidate_file_sha256']=hashes;report['candidate_sha256']=digest(encoded(hashes))
            if self.evidence_sink is not None:
                report['durable_candidate_export']=self.evidence_sink(evidence_condition,'candidate-export',{
                    'schema':'pex.stockroom-captured-export.v1','candidate_file_sha256':hashes,
                    'candidate_sha256':report['candidate_sha256'],
                    'files_base64':{n:base64.b64encode(b).decode('ascii') for n,b in actual.items()},
                    'capture_boundary':('post_stop_post_MCP_revocation_before_protected_upload' if snapshot_kind=='final' else 'saved_pre_intervention_bytes_graded_after_all_workers_revoked'),
                    'candidate_code_executed_on_controller':False})
            changed=[n for n in FILES if (n=='TASK.md' or n.startswith('tests/')) and actual[n]!=self.public[n]]
            if changed:
                report.update(status='public_contract_changed',changed_public_files=changed)
                return report
            base='/tmp/pex-stockroom-evaluation-'+uuid.uuid4().hex
            uploads={'candidate/'+n:b for n,b in actual.items()}
            # Capture bytes once; the SDK serializes each bounded batch in one
            # request. One remote stdlib verifier precedes each unchanged test
            # command. No candidate code/import executes on this controller.
            def verify_command(mode,values):
                spec={'root':base,'mode':mode,'files':{n:digest(b) for n,b in values.items()}}
                return 'python3 -I -B -c '+shlex.quote(self.verifier)+' '+shlex.quote(json.dumps(spec,sort_keys=True,separators=(',',':')))
            def verified_result(result,values):
                prefix='PEX_SNAPSHOT_VERIFIED:'+digest(encoded({n:digest(b) for n,b in values.items()}))+'\n'
                if not result['stdout'].startswith(prefix):raise ValueError('snapshot_readback_unproven')
                return {**result,'stdout':result['stdout'][len(prefix):]}
            if not self._quiescent(condition,snapshot_kind):raise ValueError('revocation_required_before_snapshot_upload')
            remote._sandbox.files.write_files({base+'/'+n:b for n,b in uploads.items()},user='user',request_timeout=15)
            public=verified_result(remote.run(verify_command('public',uploads),timeout=15),uploads)
            report['public_tests']={'stdout':public['stdout'],'stderr':public['stderr'],'exit_code':public['exit_code']}
            if public['exit_code'] not in (0,1):raise ValueError('public_test_infrastructure_terminal')
            if not self._quiescent(condition,snapshot_kind):raise ValueError('revocation_required_before_hidden_upload')
            remote._sandbox.files.write_files({base+'/'+n:b for n,b in self.protected.items()},user='user',request_timeout=15)
            result=verified_result(remote.run(verify_command('protected',{**uploads,**self.protected}),timeout=30),{**uploads,**self.protected})
            report.update(stdout=result['stdout'],stderr=result['stderr'],returncode=result['exit_code'],uploaded_sha256={**{n:digest(b) for n,b in uploads.items()},**{n:digest(b) for n,b in self.protected.items()}})
            tests=json.loads(result['stdout'])
            required={'schema','checks','passed','failed','failure_instances','complete','all_pass'}
            if type(tests) is not dict or set(tests)!=required or tests['schema']!='stockroom.grade.v1':raise ValueError('invalid_grade_schema')
            if any(type(tests[k]) is not int or tests[k]<0 for k in ('checks','passed','failed','failure_instances')):raise ValueError('invalid_grade_counts')
            if type(tests['complete']) is not bool or type(tests['all_pass']) is not bool or tests['checks']!=self.check_count or tests['complete'] is not True:raise ValueError('incomplete_grade')
            if tests['passed']+tests['failed']!=self.check_count or tests['failure_instances']<tests['failed'] or tests['all_pass']!=(tests['failed']==0) or (tests['failed']==0)!=(tests['failure_instances']==0):raise ValueError('inconsistent_grade')
            if result['exit_code'] not in (0,1) or (result['exit_code']==0)!=tests['all_pass']:raise ValueError('inconsistent_grade_exit')
            report.update(status='graded_with_limits',task_tests_measured=True,tests=tests,summary={'passed':tests['passed'],'total':self.check_count,'all_pass':tests['all_pass'],'public_tests_pass':public['exit_code']==0},task_success=tests['all_pass'] and public['exit_code']==0)
        except Exception as error:report.update(status='inconclusive',error_type=type(error).__name__)
        finally:
            if self.evidence_sink is not None:
                report['durable_grade_report']=self.evidence_sink(evidence_condition,'grade-report',dict(report))
        return report
