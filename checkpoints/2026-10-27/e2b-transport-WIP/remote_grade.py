"""Post-stop SAME-VM evaluation, explicitly anti-tamper-limited.

Candidate bytes are data on the controller; execution occurs only in E2B as
unprivileged default user. This is NOT the original bwrap isolation guarantee.
Hidden tests enter the VM only after the model's remote-tool channel is closed.
"""
import asyncio
import ast
import hashlib
import json
from pathlib import Path
import shlex
import uuid

TASK = '05_uncertain_commit'
MANIFEST = '533c7e055167fe6a86c6ed8fed481605405fab96db45bc7dd60f9705fea3d019'
PUBLIC = ('.gitignore', 'TASK.md', 'pyproject.toml', 'reliable.py', 'tests/test_smoke.py')
LIMITS = ('same_vm_not_adversarially_hardened', 'candidate_can_inspect_grading_process',
          'escaped_background_processes_not_proven_absent', 'default_user_sudo_not_removed',
          'not_original_bwrap_grader', 'no_candidate_execution_on_controller_or_as_root')

def sha(data):
    return hashlib.sha256(data).hexdigest()

class RemoteGrade:
    def __init__(self, remotes, package: Path, stopped):
        self.remotes, self.package, self.stopped = remotes, Path(package), stopped
        raw = (self.package/'MANIFEST.json').read_bytes()
        if sha(raw) != MANIFEST:
            raise ValueError('frozen_manifest_mismatch')
        manifest = json.loads(raw)['files']
        self.public, self.protected = {}, {}
        for name in PUBLIC:
            rel=f'public/{TASK}/{name}'
            data=(self.package/rel).read_bytes()
            if sha(data)!=manifest[rel]:raise ValueError('frozen_public_mismatch')
            self.public[name]=data
        for name,rel in {'runner.py':'evaluator/run_tests.py',
                         'hidden.py':f'evaluator/acceptance/test_{TASK}.py'}.items():
            data=(self.package/rel).read_bytes()
            if sha(data)!=manifest[rel]:raise ValueError('frozen_protected_mismatch')
            self.protected[name]=data
        self.protected['smoke.py']=self.public['tests/test_smoke.py']
        # Parse trusted test source as data; never import it or candidate on host.
        self.expected_tests=sum(sum(isinstance(n,ast.FunctionDef) and n.name.startswith('test_')
                                   for n in ast.walk(ast.parse(self.protected[name])))
                                for name in ('smoke.py','hidden.py'))
        self.used=set()

    async def grade(self, arm):
        condition=arm['condition']
        if condition in self.used or not self.stopped(condition):
            raise ValueError('single_post_stop_grade_required')
        self.used.add(condition)
        return await asyncio.to_thread(self._grade,condition)

    def _grade(self, condition):
        remote=self.remotes[condition]
        report={'schema':'pex.same-vm-grade.v1','task':TASK,'condition':condition,
                'status':'inconclusive','presentation_eligible':False,
                'task_tests_measured':False,'anti_tamper_limits':list(LIMITS),
                'protected_input_sha256':{n:sha(b) for n,b in self.protected.items()}}
        try:
            actual={n:remote.read(n).encode('utf-8') for n in PUBLIC}
            report['public_file_sha256']={n:sha(b) for n,b in actual.items()}
            changed=[n for n in PUBLIC if n!='reliable.py' and actual[n]!=self.public[n]]
            if changed:
                report.update(status='public_contract_changed',changed_public_files=changed)
                return report
            candidate=actual['reliable.py']
            if len(candidate)>131072:
                raise ValueError('candidate_size_bound')
            report['candidate_sha256']=sha(candidate)
            base='/tmp/pex-evaluation-'+uuid.uuid4().hex
            # Trusted controller-only API; never exposed as a model tool.
            remote._sandbox.files.make_dir(base+'/candidate',user='user',request_timeout=15)
            uploads={**self.protected,'candidate/reliable.py':candidate}
            for name,data in uploads.items():
                remote._sandbox.files.write(base+'/'+name,data,user='user',request_timeout=15)
            command='cd '+shlex.quote(base)+' && python3 -I -B runner.py candidate smoke.py hidden.py'
            result=remote.run(command,timeout=30)
            report.update(stdout=result['stdout'],stderr=result['stderr'],returncode=result['exit_code'],
                          uploaded_sha256={n:sha(b) for n,b in uploads.items()})
            tests=json.loads(result['stdout'])
            required={'tests_run','failures','errors','skipped','unexpected_successes','expected_failures','success'}
            if type(tests) is not dict or set(tests)!=required or type(tests['tests_run']) is not int:
                raise ValueError('invalid_test_summary')
            if tests['tests_run']!=self.expected_tests or type(tests['success']) is not bool:
                raise ValueError('unexpected_test_count_or_result')
            for name in required-{'tests_run','success'}:
                if type(tests[name]) is not list or any(type(x) is not str for x in tests[name]):
                    raise ValueError('invalid_test_summary_list')
            if result['exit_code'] not in (0,1):raise ValueError('grader_not_terminal')
            claimed_success=not any(tests[n] for n in required-{'tests_run','success'})
            if tests['success']!=claimed_success or (result['exit_code']==0)!=tests['success']:
                raise ValueError('inconsistent_test_summary')
            report.update(status='graded_with_limits',task_tests_measured=True,tests=tests,
                          task_success=tests['success'])
        except Exception as error:
            report.update(status='inconclusive',error_type=type(error).__name__)
        return report
