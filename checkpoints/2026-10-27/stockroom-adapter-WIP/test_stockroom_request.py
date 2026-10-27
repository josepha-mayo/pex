"""Real PEX protocol types with authored public receipts only; no models."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from controller import PublicEvidenceInfrastructureError
from stockroom_request import build_public_request,make_public_request,collect_public_observation
from stockroom_task import PUBLIC_CHECK_COMMAND
PACKAGE=Path(__file__).resolve().parent.parent/'pex-hard-task-candidate-20261027-1421'
class Remote:
    def __init__(self,check=0,diff=0,output='Authored public output'):
        self.check,self.diff,self.output=check,diff,output;self.commands=[]
    def run(self,command):
        self.commands.append(command)
        return dict(exit_code=self.check if command==PUBLIC_CHECK_COMMAND else self.diff,stdout=self.output,stderr='')
class RequestTests(unittest.TestCase):
    def inputs(self,code=0,output='Authored public output'):
        remote=Remote(code,output=output)
        receipt=SimpleNamespace(messages=['Authored final'],stdout_sha256='a'*64)
        arm=dict(public_sha256='b'*64,worker_identity='authored/worker',prompt='Implement TASK.md')
        observation=collect_public_observation(remote,receipt)
        return arm,observation,remote
    def test_exact_command_and_uncertain_acceptance(self):
        for code,status in [(0,'supported'),(1,'contradicted')]:
            arm,observation,remote=self.inputs(code)
            request=build_public_request(arm,observation,'session')
            self.assertEqual(remote.commands[0],PUBLIC_CHECK_COMMAND)
            self.assertEqual(request.scores.features['verification']['status'],status)
            self.assertEqual(request.scores.features['verification']['acceptance_status'],'uncertain')
    def test_public_spec_available_no_reference_or_hidden(self):
        arm,observation,_=self.inputs()
        request=make_public_request(PACKAGE)(arm,observation,'session')
        self.assertIn((PACKAGE/'public/TASK.md').read_text(),request.goal.objective)
        self.assertNotIn('test_17_seeded_permutations_match_model',request.model_dump_json())
        self.assertNotIn('import uuid',request.goal.objective)
        self.assertEqual(arm['prompt'],'Implement TASK.md')
    def test_legacy_or_arbitrary_command_rejected(self):
        for command in ('python -m unittest discover -s tests -p test_smoke.py','cat protected/test_acceptance.py'):
            arm,observation,_=self.inputs();observation['public_check']['command']=command
            with self.assertRaises(ValueError):build_public_request(arm,observation,'session')
    def test_non_test_exit_infrastructure(self):
        for code in (124,127,-9,True):
            with self.subTest(code=code):
                with self.assertRaises(PublicEvidenceInfrastructureError):self.inputs(code)
    def test_diff_failure_infrastructure(self):
        with self.assertRaises(PublicEvidenceInfrastructureError):collect_public_observation(Remote(0,128),SimpleNamespace(messages=[],stdout_sha256='a'*64))
    def test_multibyte_truncation_is_bounded_and_labeled(self):
        arm,observation,_=self.inputs(output='é'*30000)
        self.assertLessEqual(len(observation['public_diff'].encode()),16000)
        self.assertIn('[public evidence truncated]',observation['public_check']['output'])
        request=build_public_request(arm,observation,'session')
        self.assertEqual(request.scores.features['verification']['acceptance_status'],'uncertain')
    def test_receipt_digest_covers_public_output(self):
        _,obs,_=self.inputs();check=dict(obs['public_check']);digest=check.pop('receipt_sha256')
        self.assertEqual(digest,hashlib.sha256(json.dumps(check,sort_keys=True).encode()).hexdigest())
if __name__=='__main__':unittest.main()
