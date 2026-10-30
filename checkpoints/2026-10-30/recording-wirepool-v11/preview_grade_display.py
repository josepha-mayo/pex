"""SIMULATED display-fit preview only; no files, provider, VM, capture or benchmark."""
import time

from record_support import EvidenceDisplay, SCHEMA, sha, utc, validate


def preview():
    run_id = 'authored-recorder-asyncpool8-display-fit'
    now = utc()
    view = EvidenceDisplay(run_id, True)
    common = dict(schema=SCHEMA, run_id=run_id, at_utc=now, source_sha256='1'*64)
    text = '\n'.join('SIMULATED / AUTHORED display-fit line ' + str(n) + ' — not a model response.' for n in range(1, 11))
    digest = sha(text.encode())
    rows = [
        dict(event='measurement', qualification='setup_only_no_inference', arm='baseline',
             worker_requests=3, worker_input_tokens=300, worker_output_tokens=200, counts_validated=True),
        dict(event='measurement', qualification='setup_only_no_inference', arm='pex',
             worker_requests=4, worker_input_tokens=400, worker_output_tokens=300,
             supervisor_requests=2, supervisor_input_tokens=100, supervisor_output_tokens=50, counts_validated=True),
        dict(event='worker_response', qualification='authored_fixture_reviewed_excerpt', arm='pex',
             model_excerpt=text, model_excerpt_sha256=digest, reviewed_utc=now,
             excerpt_origin='worker_json_assistant_content'),
    ]
    for arm, outcome in [('baseline', 'complete_some_failed'), ('pex', 'candidate_import_failure')]:
        row = dict(event='grade_summary', qualification='authored_fixture_grade', arm=arm,
            task_id='asyncpool_v1_cancel_safe_dual_limit', expected_checks=8, expected_public_checks=4,
            public_test_status='failed', grade_limits='same_vm_not_adversarially_hardened',
            executed_checks=8 if arm == 'baseline' else 0, grade_outcome=outcome)
        if arm == 'baseline': row['passed_checks'] = 7
        rows.append(row)
    rows.append(dict(event='run_terminal', qualification='terminal_inconclusive',
        terminal='outcome_inconclusive', failure_category='unknown', cleanup_confirmed=False,
        comparison_complete=False))
    for seq, row in enumerate(rows, 1):
        value = validate(dict(common, seq=seq, **row), run_id=run_id, expected_seq=seq,
            not_before=time.time()-10, now=time.time(), authored_fixture=True,
            approvals={(run_id, '1'*64, digest)})
        view.update(value)
    return view.render()


if __name__ == '__main__':
    print('\033[2J\033[H' + preview(), flush=True)
