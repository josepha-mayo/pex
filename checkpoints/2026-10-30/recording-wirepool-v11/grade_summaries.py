"""WIP read-only final-grade observer. No grading, candidate execution or prose output.

A hash chain is evidence custody, not adversarial authenticity: the exact admitted
producer and root-controlled artifacts are trusted, with the original same-VM
limits retained. Never infer paired lift, publication eligibility, or missing tests.
"""
from pathlib import Path

from record_support import HEX, canonical, sha
from reviewed_excerpts import private_bytes, strict_json

CONTRACTS = {
    'dcfdef0ac5790762e8b27639e8c3c8b47eb2a3cca24c4ed57603cadba5e72c76': {
        'task': 'asyncpool_v1_cancel_safe_dual_limit', 'expected': 8, 'public_expected': 4,
        'schema': 'pex.asyncpool-same-vm-grade.v1', 'tests_schema': 'pex.asyncpool-grade.v1',
        'import_schema': 'pex.asyncpool-import-grade.v1',
        'sources': {
            'asyncpool_grade': '70a3db9e9519522c97754988d4a56fcb5bbd546cc163047cb6eb7a4c265de941',
            'asyncpool_adapter': '8280c7d24e65d634fd4834d03b6d0a7d3689dcb6df92ce0b4716e1fd72148e9c'},
        'protected': {'run_grade.py': 'af2e7eecdb41de54441aabdb4d97f35ff41e11e6fd29ddc8c7939c9024f61e09',
            'test_acceptance.py': '0c62f39babaf0e0791466514d924e0b562206f4c4ce399a85ce168cc0ffff3ce'}},
    '90b1d9042ba5b223c75820dd70989c0d227216b884503d76926af21b1cbc5d60': {
        'task': 'stockroom_v3_atomic_reservations', 'expected': 40, 'public_expected': 6,
        'schema': 'pex.stockroom-same-vm-grade.v1', 'tests_schema': 'stockroom.grade.v1',
        'sources': {'stockroom_grade': '6520c9c5999f795ea9eba9035f0cb4113965ce36d872ea92dfa8156b67aaf2e2',
            'stockroom_task': '890697e97815ed4c399c9ec2d951c096dd4d54f3e59247da0a1ed2fa9d7eb43c'},
        'protected': {'run_grade.py': '39805d2bd455058fdcae84b1d7babb4abbd88ec34036a22b1fa1d19faf114f3a',
            'test_acceptance.py': 'e2954f9a2f126639d14d2877cd2bde3ed46ce1d42a53ecf08d0e630dc893494e'}},
    '65763af6bd289cfc7bcffe8f855ab5b0f748cc234a0f296345a57738ad83d733': {
        'task': 'wirepool_v1_cancel_safe_resp_client', 'expected': 8, 'public_expected': 8,
        'schema': 'pex.wirepool-same-vm-grade.v1', 'tests_schema': 'pex.wirepool-grade.v1',
        'import_schema': 'pex.wirepool-import-grade.v1',
        'producer_pins': {
            'staged_composition': '0d72a207ba1bf4213f2791dcef9601141189e201af044908d1fb6a47c3ee9575',
            'staged_worker': 'ed2704cf162e59815731041a16c4f6fde72da87e4229de0b7ea936a2a52a5aca',
            'nebius_worker': '8a02fdf2b75701faad865d481e9f5f2d041e67889a7a6d23f1fc01e0169e3349'},
        'sources': {
            'wirepool_adapter': '84504ec13f4489b93963325db9a79dfec15f5c47df630ec7544d61d9ec5b18d8',
            'wirepool_grade': '3f280a257e1a92657f58fcf3295bb10481e8e88ca3e9de0f510f97b7de2493c4',
            'wirepool_integration': 'db4ea365aee8a30026ba4a7a52972007b10a6a70d5dd26a22d9dead1203c56b5',
            'wirepool_setup': '6dbeec6021ad969aafc7f019394569a32c465ad007b365eb42d12531f6ecef31',
            'wirepool_request': '74935fd850908d0fad43476fc8a47e986718f6b100b61b22c3da692e13c71bfd',
            'wirepool_history': '5a0a07bd57899a1f99e575e8ac90891723a89e7fc7a76f62d544e4bec49d5c32',
            'wirepool_export_candidate': '287108650397364da32cf19007c1b883b7a7d6cb28716559dd716319fe409cff',
            'wirepool_grade_upload_verify': '652b4752b35f0e03a498b66a40277c9fcb63cf27c3f797015f144ed4564008f8',
            'wirepool_public_diff': 'e9ac4761cc392a4db69c56a41a4a38d20cf86905360a3d7cd812871830fa6961'},
        'protected': {
            'run_grade.py': '87cbe6c2c02a9769dcb24fb3ee848ad27d0adbaddc3c397e927adda946b1ad80',
            'test_acceptance.py': 'a9e7d8a75e0f2e839f08b751d510f8764965162bde64dddfa03bd05acd6ef2b3'}}}
PRODUCER_PINS = {
    'staged_composition': '4a64e26f9cf66808fa5977f30d0a054ea3871f23290e641d3b6a26f45a819a8e',
    'staged_worker': 'ed2704cf162e59815731041a16c4f6fde72da87e4229de0b7ea936a2a52a5aca'}
LIMITS = ['same_vm_not_adversarially_hardened', 'candidate_can_inspect_grading_process',
          'escaped_background_processes_not_proven_absent', 'default_user_sudo_not_removed',
          'not_original_bwrap_grader', 'no_candidate_execution_on_controller_or_as_root']


def _load(path):
    raw = private_bytes(path, 4 * 1024 * 1024)
    value = strict_json(raw)
    if type(value) is not dict:
        raise ValueError('grade_object_required')
    return value, sha(raw)


def _pin(pin, expected):
    if (type(pin) is not dict or set(pin) != {'path', 'sha256'} or pin['path'] != str(expected)
            or type(pin['sha256']) is not str or not HEX.fullmatch(pin['sha256'])):
        raise ValueError('exact_grade_artifact_pin_required')
    value, digest = _load(expected)
    if digest != pin['sha256']:
        raise ValueError('grade_artifact_hash_mismatch')
    return value, digest


def _count(value, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('grade_count_type_or_bound')
    return value


def verify_grade_payload(payload, contract, arm):
    """Return a finite summary only from the exact complete grader contract."""
    if (type(payload) is not dict or payload.get('schema') != contract['schema']
            or payload.get('task') != contract['task'] or payload.get('condition') != arm
            or payload.get('snapshot_kind') != 'final' or payload.get('presentation_eligible') is not False
            or payload.get('anti_tamper_limits') != LIMITS
            or payload.get('protected_input_sha256') != contract['protected']):
        raise ValueError('final_grade_identity_or_limits')
    public = payload.get('public_tests')
    if (type(public) is not dict or type(public.get('exit_code')) is not int
            or public['exit_code'] not in (0, 1)):
        raise ValueError('public_test_status_required')
    rc = payload.get('returncode')
    if type(rc) is not int:
        raise ValueError('grade_returncode_required')
    tests = strict_json(payload.get('stdout'))
    if canonical(tests) != canonical(payload.get('tests')) or type(tests) is not dict:
        raise ValueError('raw_grade_payload_mismatch')
    n = contract['expected']
    result = dict(arm=arm, task_id=contract['task'], expected_checks=n,
                  expected_public_checks=contract['public_expected'],
                  public_test_status='passed' if public['exit_code'] == 0 else 'failed',
                  grade_limits='same_vm_not_adversarially_hardened')
    if tests.get('schema') == contract.get('import_schema') and contract.get('import_schema') is not None:
        fields = {'schema', 'outcome', 'checks', 'passed', 'failed', 'expected_checks',
                  'loader_errors', 'complete', 'all_pass'}
        outcome = tests.get('outcome')
        if (set(tests) != fields or outcome not in {'candidate_import_failure', 'grader_import_infrastructure'}
                or any(type(tests[k]) is not int or tests[k] != 0 for k in ('checks', 'passed', 'failed'))
                or type(tests['expected_checks']) is not int or tests['expected_checks'] != n
                or type(tests['loader_errors']) is not int or tests['loader_errors'] != 1
                or tests['complete'] is not False or tests['all_pass'] is not False
                or payload.get('task_tests_measured') is not False or payload.get('failure_category') != outcome
                or rc != (1 if outcome == 'candidate_import_failure' else 2)):
            raise ValueError('import_grade_contract')
        if outcome == 'candidate_import_failure':
            if (payload.get('status') != 'graded_with_limits' or payload.get('task_success') is not False
                    or canonical(payload.get('summary')) != canonical({'passed': 0, 'total': n, 'executed': 0,
                        'all_pass': False, 'public_tests_pass': public['exit_code'] == 0})):
                raise ValueError('candidate_import_summary')
        elif payload.get('status') != 'inconclusive' or 'summary' in payload or 'task_success' in payload:
            raise ValueError('grader_import_summary')
        # No passed counter: protected acceptance checks were NOT measured.
        return dict(result, executed_checks=0, grade_outcome=outcome)
    fields = {'schema', 'checks', 'passed', 'failed', 'complete', 'all_pass'}
    if n == 40:
        fields.add('failure_instances')
    if (set(tests) != fields or tests.get('schema') != contract['tests_schema']
            or _count(tests.get('checks'), n) != n or tests.get('complete') is not True
            or type(tests.get('all_pass')) is not bool):
        raise ValueError('complete_grade_required')
    passed, failed = (_count(tests[k], n) for k in ('passed', 'failed'))
    if passed + failed != n or tests['all_pass'] != (failed == 0):
        raise ValueError('grade_count_consistency')
    if n == 40 and (_count(tests['failure_instances'], 1000000) < failed
                   or (tests['failure_instances'] == 0) != (failed == 0)):
        raise ValueError('stockroom_failure_instances')
    if (rc not in (0, 1) or (rc == 0) != tests['all_pass']
            or payload.get('status') != 'graded_with_limits' or payload.get('task_tests_measured') is not True
            or canonical(payload.get('summary')) != canonical({'passed': passed, 'total': n, 'all_pass': tests['all_pass'],
                'public_tests_pass': public['exit_code'] == 0})
            or type(payload.get('task_success')) is not bool
            or payload['task_success'] != (tests['all_pass'] and public['exit_code'] == 0)
            or 'failure_category' in payload):
        raise ValueError('grade_summary_or_exit_consistency')
    return dict(result, executed_checks=n, passed_checks=passed,
                grade_outcome='complete_all_pass' if tests['all_pass'] else 'complete_some_failed')


def final_grade_records(root, *, run_id, config_sha, terminal_proof):
    """Only before feed terminal: missing/invalid arm leaves unknown, never zero.

    Return safe rows plus private custody proof. Caller must not retry after the
    terminal event; late evidence belongs to a separately identified later view.
    """
    root = Path(root).absolute()
    if root.resolve() != root or root.name != run_id:
        raise ValueError('grade_run_prefix')
    cfg, actual_config = _load(root / 'pair.json')
    if (type(cfg) is not dict or actual_config != config_sha or cfg.get('schema') != 'pex.staged.closed-candidate.v1'
            or cfg.get('run_id') != run_id):
        raise ValueError('grade_config_binding')
    if any(type(cfg.get(k)) is not dict for k in ('task', 'sources', 'sdk_sources')):
        raise ValueError('grade_config_shape')
    task_sha = cfg['task'].get('sha256')
    if type(task_sha) is not str or not HEX.fullmatch(task_sha):
        raise ValueError('grade_task_digest')
    contract = CONTRACTS.get(task_sha)
    if contract is None:
        raise ValueError('unsupported_grade_task')
    for name, expected in (contract.get('producer_pins', PRODUCER_PINS) | contract['sources']).items():
        pin = cfg['sources'].get(name)
        if type(pin) is not dict or pin.get('sha256') != expected:
            raise ValueError('unreviewed_grade_producer')
    sources_sha = sha(canonical({k: cfg[k] for k in ('sources', 'sdk_sources')}).encode())
    terminal, terminal_sha = _load(root / 'launcher-terminal.json')
    if (type(terminal) is not dict or terminal_sha != terminal_proof.get('launcher_terminal_sha256')
            or terminal.get('schema') != 'pex.staged.launcher-terminal.v1'
            or terminal.get('run_id') != run_id or terminal.get('config_sha256') != config_sha):
        raise ValueError('grade_terminal_binding')
    report, report_sha = _load(root / 'run/report.json')
    if (type(report) is not dict or report_sha != terminal.get('report_sha256') or report_sha != terminal_proof.get('report_sha256')
            or report.get('config_sha256') != config_sha or report.get('mode') != 'closed-admitted'
            or type(report.get('arms')) is not dict or set(report['arms']) - {'baseline', 'pex'}):
        raise ValueError('grade_report_binding')
    rows = []
    proof = dict(launcher_terminal_sha256=terminal_sha, report_sha256=report_sha,
                 task_manifest_sha256=task_sha, verified_grades={}, withheld_arms=[])
    for arm in ('baseline', 'pex'):
        try:
            state = report['arms'].get(arm)
            if type(state) is not dict or state.get('grade_qualification') != 'same_VM_grade_with_explicit_anti_tamper_limits':
                raise ValueError('authentic_grade_qualification_required')
            grade = state.get('protected_grade')
            if type(grade) is not dict:
                raise ValueError('grade_missing')
            artifact, artifact_sha = _pin(grade.get('durable_grade_report'), root / ('run/evidence/' + arm + '-grade-report.json'))
            identity = {'schema': 'pex.staged.grade-artifact.v1', 'run_id': run_id,
                        'config_sha256': config_sha, 'sources_sha256': sources_sha,
                        'task_sha256': task_sha, 'condition': arm, 'kind': 'grade-report',
                        'partial_pair_evidence_only': True}
            if (type(artifact) is not dict or set(artifact) != set(identity) | {'payload'}
                    or any(type(artifact.get(k)) is not type(v) or artifact[k] != v for k, v in identity.items())):
                raise ValueError('grade_artifact_identity')
            payload = {k: v for k, v in grade.items() if k not in {'durable_grade_report', 'pre_intervention_grade'}}
            if canonical(payload) != canonical(artifact['payload']):
                raise ValueError('grade_payload_disagreement')
            fields = verify_grade_payload(payload, contract, arm)
            rows.append(fields)
            proof['verified_grades'][arm] = artifact_sha
        except (ValueError, OSError, KeyError, TypeError, UnicodeError, RecursionError):
            proof['withheld_arms'].append(arm)
    return rows, proof
