#!/usr/bin/env python3
"""Private, offline-only PEX safe-display follower and exact-window recorder.

No provider imports/calls; no benchmark launcher; no UI control; no raw runtime
artifact reader. Root must approve the feed producer and reserve/inspect a safe
unobstructed window before explicitly invoking capture. Test fixtures are not
inference evidence. This utility never fabricates model responses.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import textwrap
import unicodedata

SCHEMA = 'pex-safe-display/v1'
TITLE = 'PEX Live Evidence'
SIMULATED_TITLE = 'PEX Evidence - SIMULATED'
MAX_LINE = 32768
MAX_TRACE = 2 * 1024 * 1024
MAX_VIDEO = 30 * 1024 * 1024
RESERVE = 256 * 1024 * 1024
HEX = re.compile(r'[0-9a-f]{64}\Z')
COUNTS = {'worker_requests', 'worker_input_tokens', 'worker_output_tokens',
          'supervisor_requests', 'supervisor_input_tokens', 'supervisor_output_tokens'}
BOOLS = {'counts_validated', 'cleanup_confirmed', 'comparison_complete'}
HASHES = {'source_sha256', 'task_public_manifest_sha256', 'model_excerpt_sha256'}
ENUMS = {
    'excerpt_origin': {'worker_json_assistant_content', 'worker_sse_assistant_delta_content',
                       'worker_sse_role_unspecified_delta_content','supervisor_json_assistant_content',
                       'supervisor_json_final_tool_arguments'},
    'supervisor_role': {'planner','verifier'},
    'event': {'setup', 'waiting', 'admitted', 'arm_started', 'phase_started',
              'worker_response', 'supervisor_response', 'arm_terminal',
              'run_terminal', 'resource_failure', 'cleanup', 'measurement', 'grade_summary'},
    'phase': {'waiting_for_admission', 'setup', 'baseline_phase1', 'baseline_phase2',
              'pex_phase1', 'review', 'pex_phase2', 'cleanup', 'terminal'},
    'arm': {'baseline', 'pex'},
    'terminal': {'finished', 'staged_natural_stop', 'no_intervention',
                 'planner_rejected', 'verifier_rejected', 'protocol_inconclusive',
                 'infrastructure_inconclusive', 'grading_inconclusive',
                 'worker_budget_terminal_inconclusive', 'wall_budget_terminal_inconclusive',
                 'cleanup_unconfirmed', 'platform_denied', 'admission_refused', 'cancelled', 'outcome_inconclusive'},
    'failure_category': {'none', 'platform_denied', 'quota', 'resource', 'transport',
                         'admission', 'budget', 'timeout', 'protocol', 'cleanup', 'unknown',
                         'setup_infrastructure','observation_infrastructure','supervisor_infrastructure'},
    'task_id': {'asyncpool_v1_cancel_safe_dual_limit', 'stockroom_v3_atomic_reservations'},
    'grade_outcome': {'complete_all_pass', 'complete_some_failed', 'candidate_import_failure', 'grader_import_infrastructure'},
    'public_test_status': {'passed', 'failed'},
    'grade_limits': {'same_vm_not_adversarially_hardened'},
    'qualification': {'live_current_run_grade_with_limits', 'authored_fixture_grade', 'setup_only_no_inference', 'live_current_run_status',
                      'live_current_run_reviewed_excerpt', 'terminal_inconclusive',
                      'terminal_recorded_not_publication_approved','authored_fixture_reviewed_excerpt'},
}
GRADE_COUNTS = {'expected_checks', 'executed_checks', 'passed_checks', 'expected_public_checks'}
GRADE_FIELDS = GRADE_COUNTS | {'task_id', 'grade_outcome', 'public_test_status', 'grade_limits'}
ALLOWED = {'schema', 'run_id', 'seq', 'at_utc', 'model_excerpt', 'reviewed_utc', 'source_captured_utc', 'supervisor_seconds'} | COUNTS | BOOLS | HASHES | set(ENUMS) | GRADE_COUNTS
REQUIRED = {'schema', 'run_id', 'seq', 'at_utc', 'event', 'qualification', 'source_sha256'}


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def timestamp(value):
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z', value):
        raise ValueError('invalid_timestamp')
    return dt.datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def read_approvals(path):
    if path is None or not path.exists():
        return set()
    if path.is_symlink() or path.stat().st_size > MAX_LINE:
        raise ValueError('invalid_excerpt_approvals')
    value = json.loads(path.read_text())
    if type(value) is not dict or set(value) != {'schema', 'approvals'} or value['schema'] != 'pex-excerpt-approvals/v1':
        raise ValueError('invalid_excerpt_approvals')
    if type(value['approvals']) is not list or len(value['approvals']) > 100:
        raise ValueError('invalid_excerpt_approvals')
    found = set()
    for row in value['approvals']:
        if type(row) is not dict or set(row) != {'run_id', 'source_sha256', 'model_excerpt_sha256'}:
            raise ValueError('invalid_excerpt_approvals')
        if not all(type(row[k]) is str and HEX.fullmatch(row[k]) for k in ('source_sha256', 'model_excerpt_sha256')):
            raise ValueError('invalid_excerpt_approvals')
        if type(row['run_id']) is not str:
            raise ValueError('invalid_excerpt_approvals')
        found.add((row['run_id'], row['source_sha256'], row['model_excerpt_sha256']))
    return found


def validate_fixture_mode(run_id, authored_fixture):
    """Reserved authored IDs must never enter a live-labeled display or feed."""
    if type(authored_fixture) is not bool:
        raise ValueError('invalid_authored_fixture_flag')
    if authored_fixture:
        if not run_id.startswith('authored-recorder-'):
            raise ValueError('authored_fixture_namespace')
    elif run_id.startswith('authored-'):
        raise ValueError('authored_fixture_flag_required')


def validate(record, *, run_id, expected_seq, not_before, now, approvals=frozenset(), authored_fixture=False):
    """Fail closed. No input text/errors are reflected onto the safe display."""
    validate_fixture_mode(run_id, authored_fixture)
    if type(record) is not dict or not REQUIRED <= set(record) or not set(record) <= ALLOWED:
        raise ValueError('invalid_fields')
    if record['schema'] != SCHEMA or record['run_id'] != run_id:
        raise ValueError('wrong_run_or_schema')
    if type(record['seq']) is not int or record['seq'] != expected_seq:
        raise ValueError('nonsequential_feed')
    at = timestamp(record['at_utc'])
    if not not_before <= at <= now + 5:
        raise ValueError('stale_or_future_event')
    for key, values in ENUMS.items():
        if key in record and (type(record[key]) is not str or record[key] not in values):
            raise ValueError('invalid_enum')
    for key in COUNTS & record.keys():
        if type(record[key]) is not int or not 0 <= record[key] <= 10**9:
            raise ValueError('invalid_count')
    if COUNTS & record.keys() and record.get('counts_validated') is not True:
        raise ValueError('unvalidated_counts')
    for key in BOOLS & record.keys():
        if type(record[key]) is not bool:
            raise ValueError('invalid_boolean')
    for key in HASHES & record.keys():
        if type(record[key]) is not str or not HEX.fullmatch(record[key]):
            raise ValueError('invalid_hash')
    if 'supervisor_seconds' in record and (type(record['supervisor_seconds']) not in (int, float)
            or not math.isfinite(record['supervisor_seconds']) or not 0 <= record['supervisor_seconds'] <= 86400):
        raise ValueError('invalid_duration')
    if record['event'] == 'grade_summary':
        required_grade = GRADE_FIELDS - {'passed_checks'}
        if (not required_grade <= set(record) or record.get('arm') not in {'baseline', 'pex'}
                or record['qualification'] != ('authored_fixture_grade' if authored_fixture else 'live_current_run_grade_with_limits')
                or 'model_excerpt' in record):
            raise ValueError('grade_summary_fields')
        expected, public_expected = {'asyncpool_v1_cancel_safe_dual_limit': (8, 4),
            'stockroom_v3_atomic_reservations': (40, 6)}[record['task_id']]
        if (any(type(record[k]) is not int or not 0 <= record[k] <= 40 for k in GRADE_COUNTS & record.keys())
                or record['expected_checks'] != expected or record['expected_public_checks'] != public_expected):
            raise ValueError('grade_summary_counts')
        if record['grade_outcome'].startswith('complete_'):
            if ('passed_checks' not in record or record['executed_checks'] != expected
                    or record['passed_checks'] > expected
                    or (record['passed_checks'] == expected) != (record['grade_outcome'] == 'complete_all_pass')):
                raise ValueError('complete_grade_summary_counts')
        elif expected != 8 or record['executed_checks'] != 0 or 'passed_checks' in record:
            raise ValueError('import_grade_not_measured')
    elif GRADE_FIELDS & set(record) or record['qualification'] in {'authored_fixture_grade', 'live_current_run_grade_with_limits'}:
        raise ValueError('grade_fields_wrong_event')
    if 'model_excerpt' in record:
        excerpt = record['model_excerpt']
        if (type(excerpt) is not str or not 1 <= len(excerpt) <= 4000
                or any(unicodedata.category(c).startswith('C') and c != '\n' for c in excerpt)):
            raise ValueError('invalid_excerpt')
        digest = sha(excerpt.encode())
        if (record.get('model_excerpt_sha256') != digest
                or (run_id, record['source_sha256'], digest) not in approvals
                or record['qualification'] != ('authored_fixture_reviewed_excerpt' if authored_fixture else 'live_current_run_reviewed_excerpt')
                or record['event'] not in {'worker_response', 'supervisor_response'}):
            raise ValueError('unapproved_excerpt')
        if 'excerpt_origin' not in record: raise ValueError('excerpt_origin_required')
        if timestamp(record.get('reviewed_utc')) > at:
            raise ValueError('review_after_display')
        if record['event']=='supervisor_response':
            if ('supervisor_role' not in record or 'source_captured_utc' not in record or
                    not record['excerpt_origin'].startswith('supervisor_') or
                    timestamp(record['source_captured_utc'])>timestamp(record['reviewed_utc'])):
                raise ValueError('monitor_excerpt_provenance')
        elif 'supervisor_role' in record or 'source_captured_utc' in record or not record['excerpt_origin'].startswith('worker_'):
            raise ValueError('worker_excerpt_provenance')
    elif {'model_excerpt_sha256','reviewed_utc','excerpt_origin','supervisor_role','source_captured_utc'} & set(record) or record['qualification'] in {'live_current_run_reviewed_excerpt','authored_fixture_reviewed_excerpt'}:
        raise ValueError('missing_excerpt')
    return dict(record)


def private_write(path, value):
    with path.open('x', encoding='utf-8') as f:
        f.write(canonical(value) + '\n')


class EvidenceDisplay:
    """Presentation only, consuming already validated records; never feed authority."""
    def __init__(self, run_id, fixture=False):
        validate_fixture_mode(run_id, fixture)
        self.run_id=run_id;self.fixture=fixture;self.arms={};self.latest=None;self.excerpt=None

    def update(self, record):
        self.latest=dict(record)
        if record.get('arm') in ('baseline','pex'):
            self.arms.setdefault(record['arm'],{}).update({k:v for k,v in record.items()
                if k in COUNTS | GRADE_FIELDS | {'event','at_utc','terminal'}})
        if 'model_excerpt' in record:self.excerpt=dict(record)
        return self.render()

    def render(self):
        row=self.latest or {};lines=[SIMULATED_TITLE if self.fixture else TITLE,
            'SIMULATED / AUTHORED FIXTURE - NOT REAL INFERENCE' if self.fixture else 'LIVE CURRENT RUN - verified feed, not full model output',
            'Run: '+self.run_id,
            'Latest feed UTC: '+row.get('at_utc','not observed')+' | event: '+row.get('event','waiting')]
        for arm in ('baseline','pex'):
            a=self.arms.get(arm,{})
            lines.append(arm.upper()+' | requests '+str(a.get('worker_requests','not observed'))+
                ' | input tokens '+str(a.get('worker_input_tokens','not observed'))+
                ' | output tokens '+str(a.get('worker_output_tokens','not observed')))
            lines.append('  Last evidence: '+a.get('terminal',a.get('event','not observed'))+' | UTC '+a.get('at_utc','not observed'))
        a=self.arms.get('pex',{})
        lines.append('FINAL GRADES — observed after worker stop; no baseline-to-PEX lift inferred')
        for arm in ('baseline', 'pex'):
            grade = self.arms.get(arm, {})
            if 'grade_outcome' not in grade:
                lines.append(arm.upper() + ' | final protected grade: not observed (not zero)')
            else:
                lines.append(arm.upper() + ' | task ' + grade['task_id'] + ' | ' + grade['grade_outcome'])
                lines.append('  Protected expected ' + str(grade['expected_checks']) + ' | executed ' +
                    str(grade['executed_checks']) + ' | passed ' + str(grade.get('passed_checks', 'NOT MEASURED')))
                lines.append('  Public expected ' + str(grade['expected_public_checks']) + ' | command ' +
                    grade['public_test_status'] + ' | executed count not independently reported')
                lines.append('  SAME-VM LIMITS: not adversarially hardened; not publication approved')
        lines.append('SUPERVISOR (separate) | requests '+str(a.get('supervisor_requests','not observed'))+
            ' | input '+str(a.get('supervisor_input_tokens','not observed'))+' | output '+str(a.get('supervisor_output_tokens','not observed')))
        if row.get('event')=='run_terminal':
            lines.append('TERMINAL: '+row.get('terminal','unknown')+' | cause: '+row.get('failure_category','unknown'))
            lines.append('Cleanup confirmed: '+str(row.get('cleanup_confirmed','unknown'))+
                ' | comparison complete: '+str(row.get('comparison_complete','unknown')))
        lines.append('-'*96)
        excerpt=self.excerpt
        if excerpt is None:
            lines+=['No root-reviewed model excerpt observed yet.','Counts/status alone do not demonstrate PEX benefit.']
        else:
            lines.append(('SIMULATED / ' if self.fixture else 'LIVE CURRENT RUN / ')+'REVIEW-DELAYED EXACT EXCERPT | LATEST ROOT-REVIEWED | '+excerpt.get('arm','unknown').upper()+
                (' / '+excerpt['supervisor_role'] if 'supervisor_role' in excerpt else '')+' | REVIEW-DELAYED')
            lines.append('Reviewed UTC: '+excerpt['reviewed_utc']+' | feed UTC: '+excerpt['at_utc'])
            lines.append('Origin: '+excerpt['excerpt_origin']+' | Source received UTC: unavailable')
            if 'source_captured_utc' in excerpt:lines.append('Source archive observation UTC: '+excerpt['source_captured_utc']+' (not server time)')
            wrapped=[]
            for line in excerpt['model_excerpt'].split('\n'):
                wrapped.extend(textwrap.wrap(line,width=96,replace_whitespace=False,drop_whitespace=False) or [''])
            lines.extend(wrapped[:8])
            if len(wrapped)>8:lines.append('[DISPLAY PREFIX ONLY - full exact approved excerpt retained in private safe trace]')
            lines.append('Full approved excerpt SHA256: '+excerpt['model_excerpt_sha256'])
        lines+=['Not raw streaming or full response. No task success or PEX lift inferred.',
                'Private evidence only. Raw safe feed and provenance remain unchanged.']
        return '\n'.join(lines)


def follow(args):
    os.umask(0o077)
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,127}', args.run_id):
        raise ValueError('invalid_run_id')
    fixture=getattr(args,'authored_fixture',False)
    validate_fixture_mode(args.run_id, fixture)
    feed = Path(args.feed)
    if feed.is_symlink() or (feed.exists() and feed.stat().st_size):
        raise ValueError('preexisting_feed_refused_no_replay')
    out = Path(args.output_dir)
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    not_before = time.time()
    private_write(out / 'follower-start.json', {'schema': 'pex-recorder-follower/v1', 'started_utc': utc(),
                  'run_id': args.run_id, 'qualification': 'setup_only_no_inference',
                  'feed_path_sha256': sha(str(feed.resolve()).encode()),
                  'excerpt_mode': 'root_reviewed_worker_wire' if args.approvals else 'disabled',
                  'authored_fixture': fixture,
                  'approvals_path_sha256': sha(str(args.approvals.resolve()).encode()) if args.approvals else None,
                  'source_code_sha256': sha(Path(__file__).read_bytes())})
    print('\033]0;' + TITLE + '\007\033[2J\033[H' + (SIMULATED_TITLE if fixture else TITLE), flush=True)
    print('SIMULATED / AUTHORED FIXTURE — NOT REAL INFERENCE | LOCAL RECORDER QUALIFICATION' if fixture else
          'LIVE CURRENT RUN STATUS | SETUP / WAITING — no inference result yet.', flush=True)
    print('UTC ' + utc() + ' | run ' + args.run_id, flush=True)
    print('Raw prompts, source, provider errors, credentials and private IDs are withheld.', flush=True)
    print('Exact excerpts require private review; review-delayed, not raw streaming. REPLAY UNSUPPORTED.', flush=True)
    panel = EvidenceDisplay(args.run_id,fixture)
    trace = out / 'safe-trace.jsonl'
    expected, inode, offset, last_event_at = 1, None, 0, not_before
    started = time.monotonic()
    result = 'stopped_without_terminal_evidence'
    stop = False
    def stopping(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGTERM, stopping)
    signal.signal(signal.SIGINT, stopping)
    try:
        with trace.open('x', encoding='utf-8') as log:
            while not stop and time.monotonic() - started < args.max_seconds:
                if shutil.disk_usage(out).free < RESERVE:
                    result = 'disk_reserve_stop'; break
                if feed.exists():
                    stat = feed.stat()
                    if feed.is_symlink() or (inode is not None and inode != (stat.st_dev, stat.st_ino)) or stat.st_size < offset:
                        raise ValueError('feed_replaced_or_truncated')
                    inode = (stat.st_dev, stat.st_ino)
                    with feed.open('rb') as source:
                        source.seek(offset)
                        for _ in range(50):
                            raw = source.readline(MAX_LINE + 1)
                            if len(raw) > MAX_LINE:
                                raise ValueError('oversized_feed_record')
                            if not raw or not raw.endswith(b'\n'):
                                break
                            record = validate(json.loads(raw), run_id=args.run_id, expected_seq=expected,
                                not_before=last_event_at, now=time.time(), approvals=read_approvals(args.approvals), authored_fixture=fixture)
                            clean = canonical(record)
                            if log.tell() + len(clean) + 1 > MAX_TRACE:
                                result = 'trace_size_limit'; stop = True; break
                            log.write(clean + '\n'); log.flush()
                            os.fsync(log.fileno())
                            print('\033[2J\033[H'+panel.update(record),flush=True)
                            offset += len(raw); expected += 1; last_event_at = timestamp(record['at_utc'])
                            if record['event'] == 'run_terminal':
                                result = 'terminal_record_received'; stop = True; break
                if not stop:
                    time.sleep(.2)
            if not stop and result == 'stopped_without_terminal_evidence':
                result = 'time_limit_without_terminal_evidence'
    except Exception:
        result = 'invalid_feed_withheld'
        print('RECORDER ERROR — unsafe, stale, malformed, or unapproved feed withheld.', flush=True)
    finally:
        terminal = {'schema': 'pex-recorder-follower-terminal/v1', 'ended_utc': utc(), 'run_id': args.run_id,
                    'result': result, 'accepted_records': expected - 1, 'trace_sha256': sha(trace.read_bytes()),
                    'qualification': 'status_trace_not_screen_video'}
        private_write(out / 'follower-terminal.json', terminal)
        print('DISPLAY ENDED | ' + result + ' | UTC ' + utc(), flush=True)
        print('Terminal receipt does not itself prove task success, cleanup, PEX lift, or public readiness.', flush=True)


def capture_command(window_id, display, output, seconds, width, height):
    if type(window_id) is not int or not 0 < window_id <= 0xffffffff:
        raise ValueError('nonzero_exact_window_required')
    if not 1 <= seconds <= 3600 or not 200 <= width <= 1920 or not 100 <= height <= 1080:
        raise ValueError('capture_bounds')
    return ['/usr/bin/ffmpeg', '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-f', 'x11grab', '-window_id', str(window_id), '-framerate', '3',
            '-video_size', f'{width}x{height}', '-draw_mouse', '0', '-i', display,
            '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'zerolatency', '-crf', '28',
            '-maxrate', '192k', '-bufsize', '384k', '-pix_fmt', 'yuv420p',
            '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-t', str(seconds),
            '-fs', str(MAX_VIDEO), '-progress', str(output.parent / 'capture-progress.txt'),
            '-cluster_time_limit', '1000', '-flush_packets', '1', '-nostats', '-n', str(output)]


def capture(args):
    """Root-only explicit action. No full-desktop fallback under any condition."""
    os.umask(0o077)
    display = os.environ.get('DISPLAY')
    if not display:
        raise ValueError('display_unavailable')
    out = Path(args.output_dir)
    if out.exists() or shutil.disk_usage(out.parent).free < RESERVE + MAX_VIDEO + MAX_TRACE + 8 * 1024 * 1024:
        raise ValueError('fresh_output_and_disk_reserve_required')
    def inspect(*command):
        return subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, timeout=5).stdout
    root_info = inspect('/usr/bin/xwininfo', '-root')
    root = re.search(r'Window id:\s*(0x[0-9a-fA-F]+)', root_info)
    if not root or args.window_id == int(root.group(1), 16):
        raise ValueError('root_desktop_capture_forbidden')
    info = inspect('/usr/bin/xwininfo', '-id', str(args.window_id))
    title = inspect('/usr/bin/xprop', '-id', str(args.window_id), '_NET_WM_NAME', 'WM_NAME')
    if not any(line.endswith('= "' + value + '"') for value in (TITLE, 'Terminal - ' + TITLE)
               for line in title.splitlines()):
        raise ValueError('exact_safe_window_title_required')
    if 'Map State: IsViewable' not in info:
        raise ValueError('window_not_viewable')
    width = int(re.search(r'Width:\s*(\d+)', info).group(1))
    height = int(re.search(r'Height:\s*(\d+)', info).group(1))
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    command = capture_command(args.window_id, display, out / 'screen-window.mkv', args.max_seconds, width, height)
    metadata = {'schema': 'pex-window-capture/v1', 'started_utc': utc(), 'method': 'ffmpeg-x11grab-nonzero-window-id',
                'qualification': 'actual_live_status_window_capture_not_full_model_output_video', 'frame_rate': 3,
                'max_seconds': args.max_seconds, 'max_video_bytes': MAX_VIDEO, 'width': width, 'height': height,
                'source_code_sha256': sha(Path(__file__).read_bytes()), 'window_title': TITLE,
                'privacy': 'private_only_not_publication_approved', 'occlusion_note': 'Window must remain unobstructed; review before sharing.'}
    if getattr(args,'authored_fixture',False):
        if args.max_seconds>30: raise ValueError('authored_capture_duration_bound')
        metadata['qualification']='authored_fixture_window_capture_NOT_REAL_INFERENCE'
    private_write(out / 'capture-start.json', metadata)
    interrupted = False
    with (out / 'capture-private.log').open('x') as log:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        private_write(out / 'capture-control.json', {'pid': os.getpid(), 'ffmpeg_pid': proc.pid})
        def stopping(*_):
            nonlocal interrupted
            interrupted = True
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
        signal.signal(signal.SIGTERM, stopping); signal.signal(signal.SIGINT, stopping)
        disk_stop = False
        ready = False
        while proc.poll() is None:
            progress = out / 'capture-progress.txt'
            if not ready and progress.exists() and progress.stat().st_size < 1024 * 1024:
                values = re.findall(r'^frame=(\d+)$', progress.read_text(), re.MULTILINE)
                if values and int(values[-1]) >= 2:
                    private_write(out / 'capture-ready.json', {'schema': 'pex-window-capture-ready/v1',
                        'observed_utc': utc(), 'frames_encoded_observed': int(values[-1]),
                        'qualification': 'ffmpeg_progress_only_requires_root_visual_review'})
                    ready = True
            if shutil.disk_usage(out).free < RESERVE + 4 * 1024 * 1024:
                disk_stop = True; stopping()
            time.sleep(.25)
        metadata.update({'ended_utc': utc(), 'ffmpeg_exit_code': proc.returncode,
                         'stop_requested': interrupted, 'disk_reserve_stop': disk_stop,
                         'capture_ready_observed': ready})
    media = out / 'screen-window.mkv'
    metadata['media_present'] = media.exists()
    if media.exists():
        metadata.update({'media_bytes': media.stat().st_size, 'media_sha256': sha(media.read_bytes())})
    metadata['trace_video_relation'] = 'must be checked against follower UTC and source hashes; no success inferred'
    private_write(out / 'capture-terminal.json', metadata)
    print('Window capture ended; private receipt written. Review required before any publication.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    f = sub.add_parser('follow'); f.set_defaults(function=follow)
    f.add_argument('--run-id', required=True); f.add_argument('--feed', required=True)
    f.add_argument('--output-dir', required=True); f.add_argument('--approvals', type=Path)
    f.add_argument('--max-seconds', type=int, default=1800)
    f.add_argument('--authored-fixture',action='store_true')
    c = sub.add_parser('capture'); c.set_defaults(function=capture)
    c.add_argument('--window-id', type=lambda v: int(v, 0), required=True)
    c.add_argument('--output-dir', required=True); c.add_argument('--max-seconds', type=int, default=1800)
    c.add_argument('--authored-fixture',action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_seconds <= 3600:
        parser.error('max-seconds must be 1..3600')
    try:
        args.function(args)
    except Exception:
        print('Recorder refused: private configuration, freshness, safe-window or resource guard failed.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
