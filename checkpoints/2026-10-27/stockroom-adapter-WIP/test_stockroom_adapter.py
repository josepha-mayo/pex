"""Authored offline data/protocol tests. No VM/provider/candidate code execution."""
import asyncio
import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import stockroom_task
from stockroom_task import FILES,MANIFEST_SHA256,PROTECTED,load_package,stage
from stockroom_grade import RemoteGrade
PACKAGE=Path(__file__).resolve().parent.parent/'pex-hard-task-candidate-20261027-1421'

class FakeFiles:
    def __init__(self):self.writes={};self.dirs=[]
    def make_dir(self,path,**kwargs):self.dirs.append(path)
    def write(self,path,data,**kwargs):self.writes[path]=data
    def write_files(self,files,**kwargs):self.writes.update(files)
class FakeRemote:
    def __init__(self,files=None):
        self.data=files or {n:(PACKAGE/'public'/n).read_bytes() for n in FILES}
        self._sandbox=SimpleNamespace(files=FakeFiles());self.calls=[]
        self.grade={'schema':'stockroom.grade.v1','checks':17,'passed':17,'failed':0,'failure_instances':0,'complete':True,'all_pass':True}
        self.grade_exit=0;self.public_exit=0;self.export_exit=0
    def run(self,command,timeout=None):
        self.calls.append(command)
        if 'pex.stockroom-upload-verified.v1' in command:
            import shlex
            spec=json.loads(shlex.split(command)[-1])
            assert all(hashlib.sha256(self._sandbox.files.writes[spec['root']+'/'+n]).hexdigest()==h for n,h in spec['files'].items())
            receipt='PEX_SNAPSHOT_VERIFIED:'+hashlib.sha256((json.dumps(spec['files'],sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()+'\n'
            if spec['mode']=='protected':return dict(exit_code=self.grade_exit,stdout=receipt+json.dumps(self.grade),stderr='Authored hidden result')
            assert all(n.startswith('candidate/') for n in spec['files'])
            return dict(exit_code=self.public_exit,stdout=receipt,stderr='Authored public result')
        if command.startswith('python3 -I -B -c '):
            return dict(exit_code=self.export_exit,stderr='',stdout=json.dumps({'schema':'pex.stockroom-export.v1','files':{n:base64.b64encode(b).decode() for n,b in self.data.items()}}))
        if 'run_grade.py' in command:return dict(exit_code=self.grade_exit,stdout=json.dumps(self.grade),stderr='Authored hidden result')
        return dict(exit_code=self.public_exit,stdout='',stderr='Authored public result')

class DataTests(unittest.TestCase):
    def test_stage_exact_public_only_and_independent(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'stage';frozen,prompt=stage(PACKAGE,dest)
            self.assertEqual(frozen['suite_manifest_sha256'],MANIFEST_SHA256)
            self.assertEqual(prompt,(PACKAGE/'INITIAL_PROMPT.txt').read_text())
            for arm in ('baseline','pex'):
                paths={str(p.relative_to(dest/'workers'/arm)) for p in (dest/'workers'/arm).rglob('*') if p.is_file()}
                self.assertEqual(paths,set(FILES))
            for n in FILES:self.assertEqual((dest/'workers/baseline'/n).read_bytes(),(dest/'workers/pex'/n).read_bytes())
            (dest/'workers/baseline/stockroom/db.py').write_text('Authored change')
            self.assertNotEqual((dest/'workers/baseline/stockroom/db.py').read_bytes(),(dest/'workers/pex/stockroom/db.py').read_bytes())
    def test_task_tamper_refused(self):
        with tempfile.TemporaryDirectory() as td:
            copy=Path(td)/'package';shutil.copytree(PACKAGE,copy)
            (copy/'public/TASK.md').write_text('tamper')
            with self.assertRaises(ValueError):stage(copy,Path(td)/'dest')
            self.assertFalse((Path(td)/'dest').exists())
    def test_protected_tamper_refused(self):
        with tempfile.TemporaryDirectory() as td:
            copy=Path(td)/'package';shutil.copytree(PACKAGE,copy)
            (copy/PROTECTED[0]).write_text('tamper')
            with self.assertRaises(ValueError):load_package(copy)
    def test_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td:
            copy=Path(td)/'package';shutil.copytree(PACKAGE,copy)
            f=copy/'public/stockroom/db.py';f.unlink();f.symlink_to(PACKAGE/'public/stockroom/db.py')
            with self.assertRaises(ValueError):load_package(copy)
    def test_export_trusted_program_is_readonly_and_covers_added_files(self):
        # Executes the trusted exporter, NOT candidate or imported implementation.
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td);shutil.copytree(PACKAGE/'public',dest,dirs_exist_ok=True)
            (dest/'stockroom/new_helper.py').write_text("raise RuntimeError('must never execute')")
            (dest/'tests/new_test.py').write_text("raise RuntimeError('must never execute')")
            script=Path(__file__).parent/'export_candidate.py'
            result=subprocess.run([sys.executable,'-I','-B',str(script)],cwd=dest,capture_output=True,text=True,check=True)
            names=set(json.loads(result.stdout)['files'])
            self.assertEqual(names,set(FILES)|{'stockroom/new_helper.py','tests/new_test.py'})
    def test_public_diff_includes_new_helper_contents(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td);shutil.copytree(PACKAGE/'public',dest,dirs_exist_ok=True)
            subprocess.run(['git','init','-q'],cwd=dest,check=True)
            subprocess.run(['git','add','.'],cwd=dest,check=True)
            subprocess.run(['git','-c','user.name=Authored','-c','user.email=authored@example.invalid','commit','-qm','starter'],cwd=dest,check=True)
            (dest/'stockroom/new_helper.py').write_text("UNTRACKED_PUBLIC_MARKER = 7")
            script=Path(__file__).parent/'public_diff.py'
            result=subprocess.run([sys.executable,'-I','-B',str(script)],cwd=dest,capture_output=True,text=True,check=True)
            self.assertIn('UNTRACKED_PUBLIC_MARKER = 7',result.stdout)
            self.assertIn('--- NEW stockroom/new_helper.py ---',result.stdout)

    def test_export_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td);shutil.copytree(PACKAGE/'public',dest,dirs_exist_ok=True)
            (dest/'stockroom/link.py').symlink_to(dest/'stockroom/db.py')
            result=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).parent/'export_candidate.py')],cwd=dest,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)

class GradeTests(unittest.TestCase):
    def grader(self,remote,stopped=True,revoked=True):
        return RemoteGrade({'baseline':remote},PACKAGE,lambda c:stopped,revoked=lambda c:revoked)
    def grade(self,g):return asyncio.run(g.grade({'condition':'baseline'}))
    def test_post_stop_and_revocation_required(self):
        for stopped,revoked in [(False,True),(True,False),(False,False)]:
            with self.subTest(stopped=stopped,revoked=revoked):
                r=FakeRemote();g=self.grader(r,stopped,revoked)
                with self.assertRaises(ValueError):self.grade(g)
                self.assertEqual(r.calls,[]);self.assertEqual(r._sandbox.files.writes,{})
    def test_complete_snapshot_and_hidden_only_after_stop(self):
        r=FakeRemote();r.data['stockroom/new.py']=b'Authored helper';r.data['tests/extra.py']=b'Authored test'
        g=self.grader(r);report=self.grade(g)
        self.assertEqual(report['status'],'graded_with_limits');self.assertTrue(report['task_success'])
        self.assertEqual(set(report['candidate_file_sha256']),set(r.data))
        uploaded=r._sandbox.files.writes
        self.assertTrue(any(n.endswith('/candidate/stockroom/new.py') for n in uploaded))
        self.assertTrue(any(n.endswith('/candidate/tests/extra.py') for n in uploaded))
        self.assertTrue(any(n.endswith('/test_acceptance.py') for n in uploaded))
        self.assertFalse(any('/reference/' in n for n in uploaded))
        self.assertLess(next(i for i,c in enumerate(r.calls) if 'discover' in c),next(i for i,c in enumerate(r.calls) if '\"mode\":\"protected\"' in c))
        with self.assertRaises(ValueError):self.grade(g)
    def test_protected_contract_change_prevents_hidden_upload(self):
        for name in ('TASK.md','tests/test_legacy.py','tests/test_v2_examples.py'):
            r=FakeRemote();r.data[name]=b'Changed';report=self.grade(self.grader(r))
            self.assertEqual(report['status'],'public_contract_changed');self.assertEqual(r._sandbox.files.writes,{})
    def test_implementation_changes_allowed(self):
        r=FakeRemote()
        for name in FILES:
            if name.startswith('stockroom/'):r.data[name]=b'Authored changed implementation'
        report=self.grade(self.grader(r));self.assertEqual(report['status'],'graded_with_limits')
    def test_refactored_removed_internal_module_allowed(self):
        r=FakeRemote();del r.data['stockroom/records.py']
        report=self.grade(self.grader(r));self.assertEqual(report['status'],'graded_with_limits')
    def test_invalid_export_paths_inconclusive(self):
        r=FakeRemote();r.data['stockroom/../../outside']=b'x'
        report=self.grade(self.grader(r));self.assertEqual(report['status'],'inconclusive');self.assertEqual(r._sandbox.files.writes,{})
    def test_export_failure_inconclusive(self):
        r=FakeRemote();r.export_exit=1
        report=self.grade(self.grader(r));self.assertEqual(report['status'],'inconclusive');self.assertFalse(report['task_tests_measured'])
    def test_evidence_sink_captures_exact_bytes_before_protected_and_actual_report(self):
        r=FakeRemote();events=[]
        def sink(c,kind,payload):
            if kind=='candidate-export':
                self.assertEqual(r._sandbox.files.writes,{})
                self.assertEqual({n:base64.b64decode(b) for n,b in payload['files_base64'].items()},r.data)
                self.assertEqual(payload['candidate_sha256'],hashlib.sha256((json.dumps(payload['candidate_file_sha256'],sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest())
            events.append((c,kind,payload));return {'path':'AUTHORED-private-'+kind,'sha256':'a'*64}
        report=self.grade(RemoteGrade({'baseline':r},PACKAGE,lambda c:True,revoked=lambda c:True,evidence_sink=sink))
        self.assertEqual([x[1] for x in events],['candidate-export','grade-report'])
        self.assertEqual(events[1][2]['tests'],report['tests'])
        self.assertEqual(report['status'],'graded_with_limits')
    def test_failed_export_never_fabricates_export_or_grade(self):
        r=FakeRemote();r.export_exit=1;events=[]
        def sink(c,kind,payload):events.append((kind,payload));return {'path':'AUTHORED','sha256':'a'*64}
        report=self.grade(RemoteGrade({'baseline':r},PACKAGE,lambda c:True,revoked=lambda c:True,evidence_sink=sink))
        self.assertEqual([x[0] for x in events],['grade-report'])
        self.assertEqual(report['status'],'inconclusive');self.assertNotIn('tests',events[0][1])
        self.assertNotIn('candidate_sha256',events[0][1])
    def test_invalid_summaries_inconclusive(self):
        patches=[{'checks':16},{'failed':-1},{'passed':18},{'complete':False},{'all_pass':False},{'failure_instances':True},{'schema':'other'}]
        for patch in patches:
            with self.subTest(patch=patch):
                r=FakeRemote();r.grade.update(patch);report=self.grade(self.grader(r))
                self.assertEqual(report['status'],'inconclusive');self.assertFalse(report['task_tests_measured'])
    def test_failure_is_graded_not_infrastructure(self):
        r=FakeRemote();r.grade.update(passed=16,failed=1,failure_instances=5,all_pass=False);r.grade_exit=1
        report=self.grade(self.grader(r));self.assertEqual(report['status'],'graded_with_limits');self.assertFalse(report['task_success'])
    def test_timeout_and_exit_mismatch_inconclusive(self):
        for code in (1,124,127):
            r=FakeRemote();r.grade_exit=code
            self.assertEqual(self.grade(self.grader(r))['status'],'inconclusive')
    def test_public_timeout_prevents_hidden_upload(self):
        r=FakeRemote();r.public_exit=124
        self.assertEqual(self.grade(self.grader(r))['status'],'inconclusive')
        self.assertFalse(any(n.endswith('/test_acceptance.py') for n in r._sandbox.files.writes))

class FrozenTaskRegistryTests(unittest.TestCase):
    def package(self,td,count=31):
        target=Path(td)/'authored-contract';shutil.copytree(PACKAGE,target)
        manifest=json.loads((target/'MANIFEST.json').read_bytes())
        manifest.update(task='authored-new-task-not-live',protected_check_count=count)
        raw=json.dumps(manifest,sort_keys=True).encode();(target/'MANIFEST.json').write_bytes(raw)
        identity=hashlib.sha256(raw).hexdigest()
        return target,identity,{'task':manifest['task'],'protected_check_count':count}
    def test_unknown_caller_metadata_cannot_admit_task(self):
        with tempfile.TemporaryDirectory()as td:
            target,identity,contract=self.package(td)
            with self.assertRaisesRegex(ValueError,'frozen_manifest_mismatch'):load_package(target)
    def test_source_pinned_new_contract_stage_and_count_are_exact(self):
        with tempfile.TemporaryDirectory()as td:
            target,identity,contract=self.package(td)
            with patch.dict(stockroom_task.FROZEN_TASKS,{identity:contract}):
                frozen,_=stage(target,Path(td)/'staged')
                self.assertEqual(frozen['task'],'authored-new-task-not-live');self.assertEqual(frozen['suite_manifest_sha256'],identity)
                r=FakeRemote();r.grade.update(checks=31,passed=31)
                g=RemoteGrade({'baseline':r},target,lambda c:True,revoked=lambda c:True)
                report=asyncio.run(g.grade({'condition':'baseline'}))
                self.assertEqual(report['status'],'graded_with_limits');self.assertEqual(report['summary']['total'],31)
                self.assertEqual(report['task'],'authored-new-task-not-live')
                r=FakeRemote();g=RemoteGrade({'baseline':r},target,lambda c:True,revoked=lambda c:True)
                self.assertEqual(asyncio.run(g.grade({'condition':'baseline'}))['status'],'inconclusive')
    def test_registry_count_and_manifest_metadata_cannot_disagree(self):
        with tempfile.TemporaryDirectory()as td:
            target,identity,contract=self.package(td)
            with patch.dict(stockroom_task.FROZEN_TASKS,{identity:dict(contract,protected_check_count=32)}):
                with self.assertRaisesRegex(ValueError,'contract_mismatch'):load_package(target)
    def test_legacy_exact_manifest_and_seventeen_checks_unchanged(self):
        contract=stockroom_task.package_contract(PACKAGE)
        self.assertEqual(contract['manifest_sha256'],MANIFEST_SHA256)
        self.assertEqual(contract['protected_check_count'],17)
        self.assertEqual(contract['task'],'stockroom_v2_replay_revision')

if __name__=='__main__':unittest.main()
