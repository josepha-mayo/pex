"""All evidence here is authored SIMULATED data, never provider or benchmark output."""
import copy
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import grade_summaries as g
import ledger_sidecar as sidecar
import record_support as r
from safe_feed_writer import SafeFeedWriter


class Fixture:
    def __init__(self, path, stockroom=False, wirepool=False, outcome='complete_some_failed'):
        assert not (stockroom and wirepool)
        fixture_name = ('authored-recorder-stockroom40' if stockroom else
                        'authored-recorder-wirepool8' if wirepool else 'authored-recorder-asyncpool8')
        self.root = path / fixture_name
        self.root.mkdir(mode=0o700)
        (self.root / 'run/evidence').mkdir(mode=0o700, parents=True)
        task_id = ('stockroom_v3_atomic_reservations' if stockroom else
                   'wirepool_v1_cancel_safe_resp_client' if wirepool else
                   'asyncpool_v1_cancel_safe_dual_limit')
        self.task_sha = next(k for k, v in g.CONTRACTS.items() if v['task'] == task_id)
        self.contract = copy.deepcopy(g.CONTRACTS[self.task_sha])
        self.cfg = {'schema': 'pex.staged.closed-candidate.v1', 'run_id': self.root.name,
            'task': {'sha256': self.task_sha}, 'profile': {'worker_output_per_call': 16384},
            'sources': {k: {'sha256': v} for k, v in (self.contract.get('producer_pins', g.PRODUCER_PINS) | self.contract['sources']).items()},
            'sdk_sources': {}, 'AUTHORED_FIXTURE_ONLY': True}
        self.config = self.put(self.root / 'pair.json', self.cfg)
        self.report = {'mode': 'closed-admitted', 'config_sha256': self.config, 'arms': {}}
        self.artifacts = {}
        for arm in ('baseline', 'pex'):
            n = self.contract['expected']
            tests = {'schema': self.contract['tests_schema'], 'checks': n,
                'passed': n if outcome == 'complete_all_pass' else n-1,
                'failed': 0 if outcome == 'complete_all_pass' else 1,
                'complete': True, 'all_pass': outcome == 'complete_all_pass'}
            if stockroom: tests['failure_instances'] = tests['failed']
            payload = {'schema': self.contract['schema'], 'task': self.contract['task'],
                'condition': arm, 'snapshot_kind': 'final', 'presentation_eligible': False,
                'anti_tamper_limits': g.LIMITS[:], 'protected_input_sha256': self.contract['protected'],
                'public_tests': {'exit_code': 0, 'stdout': 'SIMULATED DO NOT DISPLAY', 'stderr': ''},
                'returncode': 0 if tests['all_pass'] else 1, 'tests': tests,
                'stdout': json.dumps(tests), 'status': 'graded_with_limits', 'task_tests_measured': True,
                'summary': {'passed': tests['passed'], 'total': n, 'all_pass': tests['all_pass'], 'public_tests_pass': True},
                'task_success': tests['all_pass']}
            if outcome in ('candidate_import_failure', 'grader_import_infrastructure'):
                tests = {'schema': self.contract['import_schema'], 'outcome': outcome,
                    'checks': 0, 'passed': 0, 'failed': 0, 'expected_checks': 8,
                    'loader_errors': 1, 'complete': False, 'all_pass': False}
                payload.update(tests=tests, stdout=json.dumps(tests), task_tests_measured=False,
                    failure_category=outcome, returncode=1 if outcome == 'candidate_import_failure' else 2)
                if outcome == 'candidate_import_failure':
                    payload.update(summary={'passed': 0, 'total': 8, 'executed': 0, 'all_pass': False,
                        'public_tests_pass': True}, task_success=False)
                else:
                    payload.update(status='inconclusive');payload.pop('summary');payload.pop('task_success')
            artifact = {'schema': 'pex.staged.grade-artifact.v1', 'run_id': self.root.name,
                'config_sha256': self.config, 'task_sha256': self.task_sha,
                'sources_sha256': r.sha(r.canonical({k: self.cfg[k] for k in ('sources', 'sdk_sources')}).encode()),
                'condition': arm, 'kind': 'grade-report', 'payload': payload, 'partial_pair_evidence_only': True}
            self.artifacts[arm] = artifact
            self.report['arms'][arm] = {'protected_grade': copy.deepcopy(payload),
                'grade_qualification': 'same_VM_grade_with_explicit_anti_tamper_limits'}
        self.save_artifacts()
        self.save_report()

    def put(self, path, value):
        raw = r.canonical(value).encode();path.write_bytes(raw);path.chmod(0o600)
        return r.sha(raw)

    def save_artifacts(self):
        for arm, artifact in self.artifacts.items():
            path = self.root / ('run/evidence/' + arm + '-grade-report.json')
            digest = self.put(path, artifact)
            self.report['arms'][arm]['protected_grade'] = dict(copy.deepcopy(artifact['payload']),
                durable_grade_report={'path': str(path), 'sha256': digest})

    def save_report(self):
        digest = self.put(self.root / 'run/report.json', self.report)
        self.terminal = {'schema': 'pex.staged.launcher-terminal.v1', 'run_id': self.root.name,
            'config_sha256': self.config, 'report_sha256': digest, 'status': 'inconclusive',
            'comparison_complete': False, 'cleanup_confirmed': True, 'failure_category': None}
        terminal_sha = self.put(self.root / 'launcher-terminal.json', self.terminal)
        self.proof = {'launcher_terminal_sha256': terminal_sha, 'report_sha256': digest}

    def read(self):
        return g.final_grade_records(self.root, run_id=self.root.name, config_sha=self.config,
                                    terminal_proof=self.proof)


@pytest.mark.parametrize('stockroom,expected,public', [(False, 8, 4), (True, 40, 6)])
def test_explicit_task_counts_and_readonly_provenance(tmp_path, stockroom, expected, public):
    f = Fixture(tmp_path, stockroom)
    before = {str(p): p.read_bytes() for p in f.root.rglob('*') if p.is_file()}
    rows, proof = f.read()
    assert len(rows) == 2 and proof['withheld_arms'] == []
    assert all(x['expected_checks'] == expected and x['executed_checks'] == expected
        and x['passed_checks'] == expected-1 and x['expected_public_checks'] == public for x in rows)
    assert all('SIMULATED DO NOT DISPLAY' not in json.dumps(x) for x in rows)
    assert before == {str(p): p.read_bytes() for p in f.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('outcome', ['candidate_import_failure', 'grader_import_infrastructure'])
def test_import_failure_is_zero_executed_not_eight_failures(tmp_path, outcome):
    f = Fixture(tmp_path, outcome=outcome);rows, _ = f.read()
    assert len(rows) == 2
    for row in rows:
        assert row['expected_checks'] == 8 and row['executed_checks'] == 0
        assert 'passed_checks' not in row and row['grade_outcome'] == outcome
    view = r.EvidenceDisplay(f.root.name, True)
    text = view.update(dict(rows[0], event='grade_summary', at_utc=r.utc()))
    assert 'passed NOT MEASURED' in text and 'expected 8 | executed 0' in text
    assert 'LIVE CURRENT RUN' not in text


@pytest.mark.parametrize('tamper', ['cross_run', 'config', 'task', 'sources', 'arm', 'kind',
    'payload_disagreement', 'artifact_bytes', 'partial_artifact', 'deeply_nested_artifact', 'missing_artifact', 'pin_path',
    'raw_counts', 'raw_stdout', 'returncode', 'bool_returncode', 'expected_count',
    'partial_checks', 'summary', 'grade_qualification', 'snapshot', 'protected_input'])
def test_substituted_or_partial_arm_receipt_withheld_not_zero(tmp_path, tamper):
    f = Fixture(tmp_path);a = f.artifacts['baseline'];p = a['payload']
    if tamper == 'cross_run': a['run_id'] = 'other-run'
    elif tamper == 'config': a['config_sha256'] = '0'*64
    elif tamper == 'task': a['task_sha256'] = list(g.CONTRACTS)[1]
    elif tamper == 'sources': a['sources_sha256'] = '0'*64
    elif tamper == 'arm': a['condition'] = 'pex'
    elif tamper == 'kind': a['kind'] = 'candidate-export'
    elif tamper == 'raw_counts': p['tests']['passed'] = 8;p['stdout'] = json.dumps(p['tests'])
    elif tamper == 'raw_stdout': p['stdout'] = '{}'
    elif tamper == 'returncode': p['returncode'] = 0
    elif tamper == 'bool_returncode': p['returncode'] = True
    elif tamper == 'expected_count': p['tests']['checks'] = 40;p['stdout'] = json.dumps(p['tests'])
    elif tamper == 'partial_checks': p['tests']['checks'] = 7;p['tests']['complete'] = False;p['stdout'] = json.dumps(p['tests'])
    elif tamper == 'summary': p['summary']['passed'] = 0
    elif tamper == 'snapshot': p['snapshot_kind'] = 'pre_intervention_phase0'
    elif tamper == 'protected_input': p['protected_input_sha256'] = {}
    f.save_artifacts()
    path = f.root / 'run/evidence/baseline-grade-report.json'
    grade = f.report['arms']['baseline']['protected_grade']
    if tamper == 'payload_disagreement': grade['tests']['passed'] = 0
    elif tamper == 'artifact_bytes': path.write_text('{}')
    elif tamper == 'partial_artifact': path.write_text('{')
    elif tamper == 'deeply_nested_artifact': path.write_text('['*1500 + ']'*1500)
    elif tamper == 'missing_artifact': path.unlink()
    elif tamper == 'pin_path': grade['durable_grade_report']['path'] = str(f.root / 'run/evidence/pex-grade-report.json')
    elif tamper == 'grade_qualification': f.report['arms']['baseline']['grade_qualification'] = 'authored_only_not_task_success'
    f.save_report();rows, proof = f.read()
    assert [x['arm'] for x in rows] == ['pex']
    assert proof['withheld_arms'] == ['baseline']


@pytest.mark.parametrize('tamper', ['stale_config', 'producer_pin', 'task_pin', 'stale_report', 'terminal_run', 'authored_report'])
def test_invalid_outer_identity_refuses_all_grades(tmp_path, tamper):
    f = Fixture(tmp_path)
    if tamper in ('stale_config', 'producer_pin', 'task_pin'):
        if tamper == 'stale_config': f.cfg['run_id'] = 'other-run'
        if tamper == 'producer_pin': f.cfg['sources']['staged_worker']['sha256'] = '0'*64
        if tamper == 'task_pin': f.cfg['task']['sha256'] = '0'*64
        f.config = f.put(f.root / 'pair.json', f.cfg)
    elif tamper == 'stale_report': (f.root / 'run/report.json').write_text('{}')
    elif tamper == 'terminal_run':
        f.terminal['run_id'] = 'other-run';f.proof['launcher_terminal_sha256'] = f.put(f.root / 'launcher-terminal.json', f.terminal)
    elif tamper == 'authored_report': f.report['mode'] = 'authored-only';f.save_report()
    with pytest.raises(ValueError): f.read()


def test_missing_grade_stays_unknown_and_phase0_never_overrides_final(tmp_path):
    f = Fixture(tmp_path)
    f.report['arms']['baseline'].pop('protected_grade')
    f.report['arms']['pex']['protected_grade']['pre_intervention_grade'] = {'passed': 8, 'SIMULATED': True}
    f.save_report();rows, proof = f.read()
    assert rows[0]['arm'] == 'pex' and rows[0]['passed_checks'] == 7
    assert proof['withheld_arms'] == ['baseline']


@pytest.mark.parametrize('grade_state', ['complete', 'missing', 'partial'])
def test_simulated_sidecar_follower_grade_precedes_terminal_and_never_reopens(tmp_path, grade_state):
    f = Fixture(tmp_path);terminal_bytes = (f.root / 'launcher-terminal.json').read_bytes()
    (f.root / 'launcher-terminal.json').unlink()
    late_path = f.root / 'run/evidence/baseline-grade-report.json'
    late_bytes = late_path.read_bytes()
    if grade_state == 'missing': late_path.unlink()
    elif grade_state == 'partial': late_path.write_text('{')
    f.put(f.root / 'launcher-admission.json', {'run_id': f.root.name, 'config_sha256': f.config})
    session = f.root / 'recording-live';session.mkdir();out = session / 'display'
    cmd = [sys.executable, str(Path(r.__file__)), 'follow', '--run-id', f.root.name,
        '--feed', str(f.root / 'safe-display.jsonl'), '--output-dir', str(out),
        '--authored-fixture', '--max-seconds', '10']
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic()+3
        while not (out / 'follower-start.json').exists() and time.monotonic()<deadline: time.sleep(.01)
        args = SimpleNamespace(run_prefix=str(f.root), run_id=f.root.name, config_sha256=f.config,
            follower_start=str(out / 'follower-start.json'), max_seconds=5, final_grades=True)
        def complete(_):
            (f.root / 'launcher-terminal.json').write_bytes(terminal_bytes)
            (f.root / 'launcher-terminal.json').chmod(0o600)
        with patch.object(sidecar.time, 'sleep', side_effect=complete): assert sidecar.run(args) == 0
        stdout, stderr = proc.communicate(timeout=4)
        assert stderr == '' and proc.returncode == 0
        assert 'SIMULATED' in stdout and 'LIVE CURRENT RUN' not in stdout
        assert 'Protected expected 8 | executed 8 | passed 7' in stdout
        rows = [json.loads(x) for x in (out / 'safe-trace.jsonl').read_text().splitlines()]
        assert [x['event'] for x in rows] == ['setup'] + ['grade_summary']*(2 if grade_state == 'complete' else 1) + ['run_terminal']
        if grade_state != 'complete':
            assert [x['arm'] for x in rows if x['event'] == 'grade_summary'] == ['pex']
            assert 'BASELINE | final protected grade: not observed (not zero)' in stdout
        assert all(x['qualification'] == 'authored_fixture_grade' for x in rows if x['event'] == 'grade_summary')
        original = (f.root / 'safe-display.jsonl').read_bytes()
        # A late receipt cannot alter the already-terminated trace or reopen it.
        late_path.write_bytes(late_bytes);late_path.chmod(0o600)
        with pytest.raises(FileExistsError):
            SafeFeedWriter(run_id=f.root.name, feed_path=f.root / 'safe-display.jsonl',
                           follower_start_path=out / 'follower-start.json')
        assert (f.root / 'safe-display.jsonl').read_bytes() == original
    finally:
        if proc.poll() is None: proc.terminate();proc.wait(timeout=3)


@pytest.mark.parametrize('change', [
    {'expected_checks': 40}, {'expected_public_checks': 6}, {'executed_checks': 7},
    {'passed_checks': True}, {'passed_checks': 9}, {'grade_outcome': 'complete_all_pass'},
    {'event': 'measurement'}, {'qualification': 'live_current_run_grade_with_limits'},
    {'raw_stdout': 'SIMULATED DO NOT DISPLAY'}])
def test_feed_boundary_rejects_inconsistent_grade_summaries(tmp_path, change):
    f = Fixture(tmp_path);fields = f.read()[0][0]
    row = dict(fields, schema=r.SCHEMA, run_id=f.root.name, seq=1, at_utc=r.utc(),
        source_sha256='1'*64, event='grade_summary', qualification='authored_fixture_grade')
    row.update(change)
    with pytest.raises(ValueError):
        r.validate(row, run_id=f.root.name, expected_seq=1, not_before=time.time()-2,
                   now=time.time(), authored_fixture=True)


def test_import_feed_cannot_claim_passed_count_or_stockroom_identity(tmp_path):
    f = Fixture(tmp_path, outcome='candidate_import_failure');fields = f.read()[0][0]
    row = dict(fields, schema=r.SCHEMA, run_id=f.root.name, seq=1, at_utc=r.utc(),
        source_sha256='1'*64, event='grade_summary', qualification='authored_fixture_grade')
    for extra in ({'passed_checks': 0}, {'executed_checks': 8},
                  {'task_id': 'stockroom_v3_atomic_reservations', 'expected_checks': 40, 'expected_public_checks': 6}):
        with pytest.raises(ValueError):
            r.validate(dict(row, **extra), run_id=f.root.name, expected_seq=1,
                not_before=time.time()-2, now=time.time(), authored_fixture=True)


@pytest.mark.parametrize('field,value', [('task', []), ('sources', []), ('sdk_sources', []),
    ('task', {'sha256': []}), ('sources', {'staged_composition': []})])
def test_malformed_frozen_shapes_fail_closed_as_grade_error(tmp_path, field, value):
    f = Fixture(tmp_path);f.cfg[field] = value
    f.config = f.put(f.root / 'pair.json', f.cfg)
    with pytest.raises(ValueError): f.read()
