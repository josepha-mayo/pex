#!/usr/bin/env python3
"""Bounded read-only current-run usage recorder. No providers, prompts or model prose.

Only explicit root-approved new prefix/config are accepted. No phase inference,
behavior changes, grading reads, retries, spend authority or terminal fabrication.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import time

from record_support import HEX, RESERVE, canonical, sha, utc, ENUMS
from safe_feed_writer import SafeFeedWriter
from reviewed_excerpts import drain_approved

STATES = {'settled_raw_wire', 'uncertain', 'reserved_uncertain'}
WORKER_RESERVE = 1048576 * 300 + 4096 * 1200
SUPERVISOR_RESERVE = 262144 * 300 + 4096 * 900
MAX_ARTIFACT = 4 * 1024 * 1024


def strict_json(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result: raise ValueError('duplicate_field')
            result[k] = v
        return result
    def invalid(_): raise ValueError('nonfinite_json')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_file(path):
    if path.is_symlink() or path.resolve() != path.absolute() or not path.is_file():
        raise ValueError('artifact_path_refused')
    if path.stat().st_size > MAX_ARTIFACT:
        raise ValueError('artifact_bound')
    return path.read_bytes()


def integer(value, maximum=10**12):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('invalid_integer')
    return value


def digest(value):
    if type(value) is not str or not HEX.fullmatch(value): raise ValueError('invalid_digest')
    return value


def usage(receipt, input_bound, output_bound, charge, output_rate):
    u = receipt.get('usage')
    if type(u) is not dict: raise ValueError('missing_usage')
    i, o, total = [integer(u.get(k)) for k in ('input_tokens', 'output_tokens', 'total_tokens')]
    if i > input_bound or o > output_bound or i + o != total or charge != i * 300 + o * output_rate:
        raise ValueError('invalid_usage_charge')
    return i, o


def worker_metrics(rows, output_bound=4096):
    if type(output_bound) is not int or output_bound not in (4096,16384): raise ValueError('exact_output_profile_required')
    worker_reserve = 1048576 * 300 + output_bound * 1200
    if len(rows) > 24: raise ValueError('worker_rows_bound')
    result = {}
    for arm in ('baseline', 'pex'):
        group = [r for r in rows if r[1] == arm]
        if len(group) > 12: raise ValueError('worker_arm_bound')
        inputs = outputs = 0
        uncertain = False
        for call_id, actual_arm, request, reserve, charge, state, raw in group:
            if (type(call_id) is not str or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', call_id)
                    or state not in STATES or integer(reserve) != worker_reserve
                    or integer(charge) > reserve): raise ValueError('invalid_worker_row')
            digest(request)
            if state != 'settled_raw_wire':
                if charge != reserve: raise ValueError('uncertainty_refunded')
                uncertain = True
                continue
            if type(raw) is not str or len(raw) > 16384: raise ValueError('receipt_bound')
            receipt = strict_json(raw)
            if (type(receipt) is not dict or receipt.get('call_id') != call_id or receipt.get('arm') != arm
                    or receipt.get('request_sha256') != request or receipt.get('status') != 200):
                raise ValueError('worker_receipt_identity')
            digest(receipt.get('response_sha256'))
            i, o = usage(receipt, 1048576, output_bound, charge, 1200)
            inputs += i; outputs += o
        if group and not uncertain:
            result[arm] = dict(worker_requests=len(group), worker_input_tokens=inputs,
                               worker_output_tokens=outputs, counts_validated=True)
    if any(r[1] not in {'baseline', 'pex'} for r in rows): raise ValueError('wrong_arm')
    return result


def supervisor_metrics(rows, routes):
    if len(rows) > 12 or len(routes) != 2: raise ValueError('supervisor_rows_bound')
    roles = {}
    for fingerprint, _endpoint, model, role in routes:
        digest(fingerprint)
        if (_endpoint != 'https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions'
                or model != 'nvidia/nemotron-3-super-120b-a12b' or role not in {'planner', 'verifier'} or role in roles.values()):
            raise ValueError('route_identity')
        roles[fingerprint] = role
    inputs = outputs = 0
    uncertain = False
    for call_id, route, reserve, charge, state, raw in rows:
        if (type(call_id) is not str or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', call_id)
                or route not in roles or state not in STATES or integer(reserve) != SUPERVISOR_RESERVE
                or integer(charge) > reserve): raise ValueError('invalid_supervisor_row')
        if state != 'settled_raw_wire':
            if charge != reserve: raise ValueError('uncertainty_refunded')
            uncertain = True
            continue
        if type(raw) is not str or len(raw) > 16384: raise ValueError('receipt_bound')
        receipt = strict_json(raw)
        if (type(receipt) is not dict or receipt.get('invocation_id') != call_id
                or receipt.get('route_fingerprint') != route or receipt.get('role') != roles[route]
                or receipt.get('model_id') != 'nvidia/nemotron-3-super-120b-a12b'
                or receipt.get('outcome') != 'succeeded' or receipt.get('dispatch_state') != 'response_complete'
                or type(receipt.get('attempts')) is not int or receipt['attempts'] != 1
                or type(receipt.get('http_status')) is not int or receipt['http_status'] != 200):
            raise ValueError('supervisor_receipt_identity')
        i, o = usage(receipt, 262144, 1200 if roles[route] == 'planner' else 900, charge, 900)
        inputs += i; outputs += o
    if rows and not uncertain:
        return dict(supervisor_requests=len(rows), supervisor_input_tokens=inputs,
                    supervisor_output_tokens=outputs, counts_validated=True)
    return {}


def snapshot_db(path, *, config_sha, worker, output_bound=4096):
    read_file(path)  # Reject symlinks, oversize and nonregular artifacts.
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.05) as conn:
        conn.execute('PRAGMA query_only=ON')
        conn.set_progress_handler(lambda: 1, 100000)
        conn.execute('BEGIN')
        if worker:
            config = conn.execute('SELECT digest,ir,outr,input_bound,output_bound FROM config').fetchall()
            if config != [(config_sha, 300, 1200, 1048576, output_bound)]: raise ValueError('worker_config_binding')
            rows = conn.execute('SELECT id,arm,request_sha,reserved,charged,state,receipt FROM calls ORDER BY id LIMIT 25').fetchall()
            metrics = worker_metrics(rows, output_bound)
            identity = config
        else:
            config = conn.execute('SELECT ir,outr FROM config').fetchall()
            if config != [(300, 900)]: raise ValueError('supervisor_pricing_binding')
            routes = conn.execute('SELECT fingerprint,endpoint,model,role FROM approved_route_identity ORDER BY role LIMIT 3').fetchall()
            rows = conn.execute('SELECT id,route,reserve,charged,state,receipt FROM calls ORDER BY id LIMIT 13').fetchall()
            metrics = supervisor_metrics(rows, routes)
            identity = [config, routes]
        proof = {'transaction_rows_sha256': sha(canonical(rows).encode()), 'identity_sha256': sha(canonical(identity).encode()),
                 'row_receipt_sha256': [sha(canonical(row).encode()) for row in rows], 'verified_metrics': metrics}
        conn.rollback()
    # Exact transaction row digest above is authoritative; file bytes may change
    # after the RO transaction. Do not mislabel this later file hash a snapshot.
    proof['artifact_sha256_after_transaction'] = sha(read_file(path))
    return metrics, proof


def terminal_record(root, run_id, config_sha):
    path = root / 'launcher-terminal.json'
    if not path.exists(): return None
    raw = read_file(path); value = strict_json(raw)
    if (type(value) is not dict or value.get('schema') != 'pex.staged.launcher-terminal.v1'
            or value.get('run_id') != run_id or value.get('config_sha256') != config_sha
            or value.get('status') not in {'comparison_complete', 'inconclusive'}
            or type(value.get('cleanup_confirmed')) is not bool or type(value.get('comparison_complete')) is not bool):
        raise ValueError('terminal_binding')
    report_sha = value.get('report_sha256')
    proof = {'launcher_terminal_sha256': sha(raw)}
    if report_sha is not None:
        report_raw = read_file(root / 'run/report.json')
        if sha(report_raw) != digest(report_sha): raise ValueError('report_hash_mismatch')
        report = strict_json(report_raw)
        if type(report) is not dict or report.get('config_sha256') != config_sha: raise ValueError('report_config_mismatch')
        proof['report_sha256'] = report_sha
    raw_category = value.get('failure_category')
    if raw_category is not None and (type(raw_category) is not str or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}', raw_category)):
        raise ValueError('terminal_failure_category')
    category = {'TimeoutError': 'timeout', 'WallBudgetExhausted': 'timeout', 'AdmissionRefused': 'admission',
                'WorkerBudgetExhausted': 'budget', 'WorkerBudgetTerminal': 'budget',
                'ProtocolInconclusive': 'protocol'}.get(raw_category,
                'none' if raw_category is None and value['comparison_complete'] else 'unknown')
    cleanup_errors = value.get('cleanup_errors', [])
    if type(cleanup_errors) is not list: raise ValueError('invalid_cleanup_error_list')
    if raw_category is None and cleanup_errors and not value['cleanup_confirmed']:
        category = 'cleanup'
    if value['comparison_complete'] and (not value['cleanup_confirmed'] or report_sha is None or category != 'none'):
        raise ValueError('unsupported_completed_comparison')
    terminal = 'finished' if value['comparison_complete'] else {
        'budget': 'worker_budget_terminal_inconclusive', 'timeout': 'wall_budget_terminal_inconclusive',
        'admission': 'admission_refused', 'protocol': 'protocol_inconclusive', 'cleanup': 'cleanup_unconfirmed',
    }.get(category, 'outcome_inconclusive')
    fields = dict(cleanup_confirmed=value['cleanup_confirmed'], comparison_complete=value['comparison_complete'],
                  failure_category=category, phase='terminal',
                  terminal=terminal)
    return fields, proof


def emit_setup(writer, root, out, config_sha, output_bound):
    """A real local binding check, explicitly no inference/admission claim."""
    raw = read_file(root / 'pair.json')
    if sha(raw) != config_sha: raise ValueError('setup_config_changed')
    if (root / 'launcher-terminal.json').exists(): raise ValueError('setup_after_terminal')
    proof = {'schema':'pex-recording-setup-check/v1','run_id':root.name,
             'config_sha256':config_sha,'worker_output_per_call':output_bound,
             'observed_utc':utc(),'qualification':'setup_only_no_inference'}
    encoded = canonical(proof).encode()
    fd = os.open(out / 'setup-binding.json', os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f: f.write(encoded);f.flush();os.fsync(f.fileno())
    return writer.emit(event='setup',qualification='setup_only_no_inference',
                       source_sha256=sha(encoded),phase='waiting_for_admission')


def run(args):
    os.umask(0o077)
    root = Path(args.run_prefix).absolute()
    if root.is_symlink() or root.resolve() != root or root.name != args.run_id:
        raise ValueError('exact_run_prefix_required')
    display = Path(getattr(args, 'display_prefix', None) or root).absolute()
    if display.is_symlink() or display.resolve() != display or display.name != args.run_id or not display.is_dir():
        raise ValueError('exact_display_prefix_required')
    expected_start = display / 'recording-live/display/follower-start.json'
    if Path(args.follower_start).absolute() != expected_start:
        raise ValueError('exact_display_follower_required')
    config_sha = digest(args.config_sha256)
    config_raw = read_file(root / 'pair.json')
    if sha(config_raw) != config_sha: raise ValueError('root_config_hash')
    output_bound = strict_json(config_raw).get('profile', {}).get('worker_output_per_call', 4096)
    if type(output_bound) is not int or output_bound not in (4096,16384): raise ValueError('exact_output_profile_required')
    # Read only frozen profile metadata, never credential files, prompts, or source.
    out = display / 'recorder-provenance'
    out.mkdir(mode=0o700, exist_ok=False)
    with SafeFeedWriter(run_id=args.run_id, feed_path=display / 'safe-display.jsonl',
                        follower_start_path=Path(args.follower_start), terminal_path=root / 'launcher-terminal.json') as writer:
        if getattr(args, 'reviewed_excerpts', False) and not writer.reviewed_excerpts_enabled:
            raise ValueError('follower_excerpt_opt_in_required')
        emit_setup(writer, root, out, config_sha, output_bound)
        previous = None; index = 0; start = time.monotonic(); excerpt_seen = set()
        while time.monotonic() - start < args.max_seconds:
            if shutil.disk_usage(out).free < RESERVE + 8 * 1024 * 1024: raise ValueError('disk_reserve')
            if sha(read_file(root / 'pair.json')) != config_sha: raise ValueError('config_changed')
            admission_path = root / 'launcher-admission.json'
            if not admission_path.exists():
                time.sleep(1); continue
            admission_raw = read_file(admission_path); admission = strict_json(admission_raw)
            if (type(admission) is not dict or admission.get('run_id') != args.run_id
                    or admission.get('config_sha256') != config_sha): raise ValueError('admission_identity')
            identity_path = root / 'run/accounting-identity.json'
            measurements = []; proof = {'schema': 'pex-recording-measurement/v1', 'run_id': args.run_id,
                'config_sha256': config_sha, 'admission_sha256': sha(admission_raw)}
            if identity_path.exists() and all((root / ('run/' + name)).exists() for name in ('workers.sqlite', 'supervisor.sqlite')):
                identity_raw = read_file(identity_path); identity = strict_json(identity_raw)
                if type(identity) is not dict or identity.get('config') != config_sha: raise ValueError('accounting_identity')
                proof['accounting_identity_sha256'] = sha(identity_raw)
                try:
                    workers, wp = snapshot_db(root / 'run/workers.sqlite', config_sha=config_sha, worker=True, output_bound=output_bound)
                    supervisor, sp = snapshot_db(root / 'run/supervisor.sqlite', config_sha=config_sha, worker=False)
                except sqlite3.OperationalError:
                    time.sleep(1); continue  # Brief initialization/lock: no unproven measurements.
                proof.update(workers=wp, supervisor=sp)
                measurements += [dict(arm=arm, **metric) for arm, metric in workers.items()]
                if supervisor: measurements.append(dict(arm='pex', **supervisor))
            terminal = terminal_record(root, args.run_id, config_sha)
            if terminal: proof['terminal'] = terminal[1]
            fingerprint = sha(canonical(proof).encode())
            if fingerprint != previous:
                if index >= 1800: raise ValueError('snapshot_bound')
                proof['observed_utc'] = utc(); index += 1
                source = out / f'measurement-{index:04d}.json'
                raw = (canonical(proof) + '\n').encode()
                fd = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                try: os.write(fd, raw); os.fsync(fd)
                finally: os.close(fd)
                source_sha = sha(raw)
                for fields in measurements:
                    writer.emit(event='measurement', qualification='live_current_run_status', source_sha256=source_sha, **fields)
                if terminal:
                    writer.emit(event='run_terminal', qualification='terminal_recorded_not_publication_approved',
                                source_sha256=source_sha, **terminal[0])
                    return 0
                previous = fingerprint
            if getattr(args, 'reviewed_excerpts', False):
                try:
                    drain_approved(root, writer, config_sha=config_sha, seen=excerpt_seen, now=time.time(), display_root=display)
                except (ValueError, OSError, KeyError, TypeError, UnicodeError, sqlite3.Error):
                    # Excerpt review failure never stops truthful typed usage or
                    # reflects raw artifacts/errors onto the safe display.
                    error = out / 'excerpt-withheld.json'
                    if not error.exists():
                        error.write_text(canonical({'schema': 'pex-excerpt-withheld/v1',
                            'run_id': args.run_id, 'observed_utc': utc(),
                            'reason': 'private_verification_or_approval_unavailable'}) + '\n')
            time.sleep(1)
    return 3  # No manufactured terminal event on observer timeout.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-prefix', required=True); parser.add_argument('--run-id', required=True)
    parser.add_argument('--display-prefix', help='Explicit shared native display prefix; source artifacts remain under run-prefix')
    parser.add_argument('--config-sha256', required=True); parser.add_argument('--follower-start', required=True)
    parser.add_argument('--max-seconds', type=int, default=1800)
    parser.add_argument('--reviewed-excerpts', action='store_true', help='Opt-in root-reviewed current worker wire selections; replay refused')
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 3600: parser.error('max-seconds must be 1..3600')
    try: return run(args)
    except Exception:
        print('Sidecar stopped: current-run binding or validated measurement unavailable; no terminal invented.')
        return 2


if __name__ == '__main__': raise SystemExit(main())
