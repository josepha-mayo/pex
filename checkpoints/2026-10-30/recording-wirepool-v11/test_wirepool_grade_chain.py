"""Exact frozen V11 grade-chain fixtures; AUTHORED, never inference evidence."""
import copy
import json
from pathlib import Path

import pytest

import grade_summaries as g
from test_grade_summaries import Fixture


TASK_SHA = '65763af6bd289cfc7bcffe8f855ab5b0f748cc234a0f296345a57738ad83d733'
TASK = 'wirepool_v1_cancel_safe_resp_client'


def test_frozen_v11_identity_and_two_arm_final_grade_chain(tmp_path):
    assert TASK_SHA in g.CONTRACTS
    contract = g.CONTRACTS[TASK_SHA]
    assert contract['task'] == TASK
    assert contract['expected'] == contract['public_expected'] == 8
    assert contract['schema'] == 'pex.wirepool-same-vm-grade.v1'
    assert contract['tests_schema'] == 'pex.wirepool-grade.v1'
    assert contract['import_schema'] == 'pex.wirepool-import-grade.v1'
    assert set(contract['producer_pins']) == {'staged_composition', 'staged_worker', 'nebius_worker'}
    assert set(contract['sources']) == {'wirepool_adapter', 'wirepool_grade',
        'wirepool_integration', 'wirepool_setup', 'wirepool_request', 'wirepool_history',
        'wirepool_export_candidate', 'wirepool_grade_upload_verify', 'wirepool_public_diff'}
    f = Fixture(tmp_path, wirepool=True, outcome='complete_all_pass')
    before = {str(p): p.read_bytes() for p in f.root.rglob('*') if p.is_file()}
    rows, proof = f.read()
    assert [row['arm'] for row in rows] == ['baseline', 'pex']
    assert proof['task_manifest_sha256'] == TASK_SHA and not proof['withheld_arms']
    assert all(row['task_id'] == TASK and row['expected_checks'] == 8
               and row['expected_public_checks'] == 8 and row['executed_checks'] == 8
               and row['passed_checks'] == 8 and row['grade_outcome'] == 'complete_all_pass'
               for row in rows)
    assert before == {str(p): p.read_bytes() for p in f.root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('outcome', ['candidate_import_failure', 'grader_import_infrastructure'])
def test_wirepool_import_grades_have_zero_executed_and_no_passed_counter(tmp_path, outcome):
    f = Fixture(tmp_path, wirepool=True, outcome=outcome)
    rows, proof = f.read()
    assert len(rows) == 2 and not proof['withheld_arms']
    assert all(row['grade_outcome'] == outcome and row['expected_checks'] == 8
               and row['expected_public_checks'] == 8 and row['executed_checks'] == 0
               and 'passed_checks' not in row for row in rows)


@pytest.mark.parametrize('tamper', [
    'task_sha', 'producer_composition', 'producer_adapter', 'producer_export',
    'producer_nebius', 'outer_report', 'terminal_config',
])
def test_wirepool_wrong_outer_identity_or_producer_never_emits_grade(tmp_path, tamper):
    f = Fixture(tmp_path, wirepool=True)
    if tamper == 'task_sha':
        f.cfg['task']['sha256'] = next(k for k,v in g.CONTRACTS.items() if v['task'] != TASK)
    elif tamper.startswith('producer_'):
        key = {'producer_composition': 'staged_composition',
               'producer_adapter': 'wirepool_adapter',
               'producer_export': 'wirepool_export_candidate',
               'producer_nebius': 'nebius_worker'}[tamper]
        f.cfg['sources'][key]['sha256'] = '0' * 64
    elif tamper == 'outer_report':
        (f.root / 'run/report.json').write_text('{}')
    else:
        f.terminal['config_sha256'] = '0' * 64
        f.proof['launcher_terminal_sha256'] = f.put(f.root / 'launcher-terminal.json', f.terminal)
    if tamper == 'task_sha' or tamper.startswith('producer_'):
        f.config = f.put(f.root / 'pair.json', f.cfg)
    with pytest.raises(ValueError):
        f.read()


@pytest.mark.parametrize('source_name', [
    'staged_composition', 'staged_worker', 'nebius_worker',
    'wirepool_adapter', 'wirepool_grade', 'wirepool_integration', 'wirepool_setup',
    'wirepool_request', 'wirepool_history', 'wirepool_export_candidate',
    'wirepool_grade_upload_verify', 'wirepool_public_diff',
])
def test_each_exact_wirepool_producer_pin_is_required(tmp_path, source_name):
    f = Fixture(tmp_path, wirepool=True)
    f.cfg['sources'][source_name]['sha256'] = '0' * 64
    f.config = f.put(f.root / 'pair.json', f.cfg)
    with pytest.raises(ValueError, match='unreviewed_grade_producer'):
        f.read()


@pytest.mark.parametrize('tamper', [
    'missing', 'partial', 'artifact_bytes', 'wrong_task_in_payload',
    'wrong_protected_hash', 'wrong_inner_schema', 'wrong_public_exit',
    'partial_count', 'forged_summary', 'phase0_only',
])
def test_wirepool_invalid_arm_receipt_is_withheld_not_zero(tmp_path, tamper):
    f = Fixture(tmp_path, wirepool=True)
    artifact = f.artifacts['baseline']
    payload = artifact['payload']
    if tamper == 'wrong_task_in_payload':
        payload['task'] = 'asyncpool_v1_cancel_safe_dual_limit'
    elif tamper == 'wrong_protected_hash':
        payload['protected_input_sha256'] = dict(payload['protected_input_sha256'])
        payload['protected_input_sha256']['test_acceptance.py'] = '0' * 64
    elif tamper == 'wrong_inner_schema':
        payload['tests']['schema'] = 'pex.asyncpool-grade.v1'
        payload['stdout'] = json.dumps(payload['tests'])
    elif tamper == 'wrong_public_exit':
        payload['public_tests']['exit_code'] = 2
    elif tamper == 'partial_count':
        payload['tests']['checks'] = 7
        payload['stdout'] = json.dumps(payload['tests'])
    elif tamper == 'forged_summary':
        payload['summary']['passed'] = 8
    f.save_artifacts()
    path = f.root / 'run/evidence/baseline-grade-report.json'
    if tamper == 'missing':
        path.unlink()
    elif tamper == 'partial':
        path.write_text('{')
    elif tamper == 'artifact_bytes':
        path.write_text('{}')
    elif tamper == 'phase0_only':
        f.report['arms']['baseline'].pop('protected_grade')
        f.report['arms']['baseline']['pre_intervention_grade'] = copy.deepcopy(payload)
    f.save_report()
    rows, proof = f.read()
    assert [row['arm'] for row in rows] == ['pex']
    assert proof['withheld_arms'] == ['baseline']
    assert 'baseline' not in proof['verified_grades']
