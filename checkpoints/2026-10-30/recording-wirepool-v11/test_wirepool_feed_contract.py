"""Authored-only V11 feed-boundary tests; never live benchmark evidence."""
import time

import pytest

import grade_summaries as g
import record_support as r


def grade(*, arm='baseline', outcome='complete_some_failed', executed=8, passed=7):
    row = dict(schema=r.SCHEMA, run_id='authored-recorder-wirepool8', seq=1,
               at_utc=r.utc(), event='grade_summary', arm=arm,
               qualification='authored_fixture_grade', source_sha256='1' * 64,
               task_id='wirepool_v1_cancel_safe_resp_client',
               grade_outcome=outcome, public_test_status='passed',
               grade_limits='same_vm_not_adversarially_hardened',
               expected_checks=8, expected_public_checks=8,
               executed_checks=executed)
    if passed is not None:
        row['passed_checks'] = passed
    return row


def checked(row):
    return r.validate(row, run_id='authored-recorder-wirepool8', expected_seq=1,
                      not_before=time.time() - 2, now=time.time(), authored_fixture=True)


def test_wirepool_complete_and_zero_executed_import_shapes():
    assert checked(grade())['expected_public_checks'] == 8
    assert checked(grade(outcome='candidate_import_failure', executed=0, passed=None))['executed_checks'] == 0


@pytest.mark.parametrize('field,value', [
    ('expected_checks', 40), ('expected_public_checks', 4), ('executed_checks', 7),
    ('passed_checks', 8), ('grade_outcome', 'complete_all_pass'),
    ('task_id', 'stockroom_v3_atomic_reservations'), ('qualification', 'live_current_run_grade_with_limits'),
])
def test_wirepool_mismatch_or_authored_as_live_is_rejected(field, value):
    row = grade()
    row[field] = value
    with pytest.raises(ValueError):
        checked(row)


def test_import_failure_cannot_report_a_passing_or_executed_check():
    row = grade(outcome='candidate_import_failure', executed=0, passed=None)
    for change in ({'passed_checks': 0}, {'executed_checks': 8}):
        with pytest.raises(ValueError):
            checked(dict(row, **change))


def test_wirepool_identity_is_not_an_authored_live_run():
    r.validate_fixture_mode('wirepool-staged-pair-20261030-01', False)
    with pytest.raises(ValueError, match='authored_fixture_namespace'):
        r.validate_fixture_mode('wirepool-staged-pair-20261030-01', True)
    with pytest.raises(ValueError, match='authored_fixture_flag_required'):
        r.validate_fixture_mode('authored-recorder-wirepool8', False)


def test_wirepool_render_is_bounded_for_1177x808_window():
    view = r.EvidenceDisplay('authored-recorder-wirepool8', True)
    for arm in ('baseline', 'pex'):
        view.update(grade(arm=arm))
    lines = view.render().splitlines()
    assert len(lines) <= 36
    assert max(map(len, lines)) <= 115
    assert 'SIMULATED / AUTHORED FIXTURE - NOT REAL INFERENCE' in lines
    assert any('Public expected 8' in line for line in lines)


def test_wirepool_exact_inner_schema_and_zero_executed_payload():
    # The full producer hash chain is exercised by test_wirepool_grade_chain
    # after source/task freeze; this checks the payload semantics independently.
    contract = dict(task='wirepool_v1_cancel_safe_resp_client', expected=8,
                    public_expected=8, schema='pex.wirepool-same-vm-grade.v1',
                    tests_schema='pex.wirepool-grade.v1',
                    import_schema='pex.wirepool-import-grade.v1',
                    protected={'run_grade.py': 'a'*64, 'test_acceptance.py': 'b'*64})
    tests = dict(schema=contract['tests_schema'], checks=8, passed=8, failed=0,
                 complete=True, all_pass=True)
    payload = dict(schema=contract['schema'], task=contract['task'], condition='baseline',
                   snapshot_kind='final', presentation_eligible=False,
                   anti_tamper_limits=g.LIMITS[:], protected_input_sha256=contract['protected'],
                   public_tests={'exit_code': 0}, returncode=0, stdout=r.canonical(tests),
                   tests=tests, status='graded_with_limits', task_tests_measured=True,
                   summary={'passed':8, 'total':8, 'all_pass':True, 'public_tests_pass':True},
                   task_success=True)
    fields = g.verify_grade_payload(payload, contract, 'baseline')
    assert fields['executed_checks'] == fields['passed_checks'] == 8
    assert fields['expected_public_checks'] == 8
    for changed in ({'task': 'asyncpool_v1_cancel_safe_dual_limit'},
                    {'protected_input_sha256': {}}, {'stdout': '{}'},
                    {'returncode': 1}):
        with pytest.raises(ValueError):
            g.verify_grade_payload(dict(payload, **changed), contract, 'baseline')
    import_tests = dict(schema=contract['import_schema'], outcome='candidate_import_failure',
                        checks=0, passed=0, failed=0, expected_checks=8, loader_errors=1,
                        complete=False, all_pass=False)
    imported = dict(payload, stdout=r.canonical(import_tests), tests=import_tests,
                    returncode=1, task_tests_measured=False,
                    failure_category='candidate_import_failure',
                    summary={'passed':0, 'total':8, 'executed':0, 'all_pass':False,
                             'public_tests_pass':True}, task_success=False)
    fields = g.verify_grade_payload(imported, contract, 'baseline')
    assert fields['executed_checks'] == 0 and 'passed_checks' not in fields
    assert fields['grade_outcome'] == 'candidate_import_failure'
    wrong = dict(import_tests, schema='pex.asyncpool-import-grade.v1')
    with pytest.raises(ValueError):
        g.verify_grade_payload(dict(imported, tests=wrong, stdout=r.canonical(wrong)), contract, 'baseline')
