"""Private, offline-only exact worker excerpt verification. Never auto-approve prose.

The root reviewer supplies a bounded selection manifest AND a separate approval
triple after inspecting exact bytes privately. Only immutable current-run wire
artifacts bound by settled ledger receipts are supported. Supervisor prose and
replay are deliberately unsupported. No network/provider/benchmark imports.
"""
import base64
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat

from record_support import HEX, canonical, read_approvals, sha, timestamp

MANIFEST_FIELDS = {'schema', 'run_id', 'config_sha256', 'source_relative_path',
                   'source_sha256', 'model_excerpt_sha256', 'start_byte',
                   'end_byte', 'reviewed_utc'}
WORKER_MODEL = 'deepseek-ai/DeepSeek-V4.1-Flash-1017'


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate_field')
            result[key] = value
        return result
    def invalid(_): raise ValueError('nonfinite_json')
    def finite_float(value):
        n=float(value)
        if not math.isfinite(n): raise ValueError('nonfinite_json')
        return n
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite_float)


def private_bytes(path, limit):
    path = Path(path).absolute()
    if path.resolve() != path: raise ValueError('unlinked_private_path_required')
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            info.st_uid != os.geteuid() or info.st_mode & 0o077 or info.st_size > limit):
        raise ValueError('private_artifact_refused')
    return path.read_bytes()


def wire_usage(value, output_bound=4096):
    if type(output_bound) is not int or output_bound not in (4096,16384): raise ValueError('exact_output_profile_required')
    if type(value) is not dict: raise ValueError('complete_wire_usage_required')
    i, o, total = (value.get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens'))
    if (any(type(n) is not int or not 0 <= n <= 10**15 for n in (i, o, total))
            or i > 1048576 or o > output_bound or i + o != total):
        raise ValueError('wire_usage_bounds')
    for field, count in (('prompt_tokens_details', i), ('completion_tokens_details', o)):
        details = value.get(field)
        if details is not None:
            if type(details) is not dict or any(type(n) is not int or not 0 <= n <= count for n in details.values()):
                raise ValueError('wire_usage_details')
    return dict(input_tokens=i, output_tokens=o, total_tokens=total)


def assistant_content(response, content_type, *, output_bound=4096):
    """Exact decoded JSON content or ordered SSE delta.content concatenation.

    Framing/identity/finish/usage constraints mirror the reviewed worker ledger
    parser; reconstruction never uses tool args, reasoning, errors, or prose
    authored by this recorder. Returned bytes are newly UTF-8 encoded decoded
    assistant content, not literal SSE framing bytes.
    """
    if type(output_bound) is not int or output_bound not in (4096,16384): raise ValueError('exact_output_profile_required')
    if type(response) is not bytes or not 1 <= len(response) <= (8 if output_bound==16384 else 2) * 1024 * 1024:
        raise ValueError('bounded_wire_response_required')
    if type(content_type) is not str: raise ValueError('wire_content_type_required')
    kind = content_type.split(';', 1)[0].strip().lower()
    if kind == 'application/json':
        body = strict_json(response)
        if type(body) is not dict or body.get('model') != WORKER_MODEL or body.get('error') is not None:
            raise ValueError('worker_model_or_error')
        choices = body.get('choices')
        if type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict:
            raise ValueError('one_assistant_choice_required')
        choice = choices[0]
        if (type(choice.get('index')) is not int or choice['index'] != 0 or
                choice.get('finish_reason') not in {'stop', 'length', 'tool_calls'}):
            raise ValueError('complete_worker_choice_required')
        message = choice.get('message')
        if type(message) is not dict or message.get('role') != 'assistant' or type(message.get('content')) is not str:
            raise ValueError('assistant_content_required')
        return message['content'], wire_usage(body.get('usage'), output_bound), 'worker_json_assistant_content'
    if kind != 'text/event-stream': raise ValueError('unsupported_wire_content_type')
    text = response.decode('utf-8').replace('\r\n', '\n')
    if not text.endswith('\n\n'): raise ValueError('truncated_sse_framing')
    done = finished = role_seen = False
    stream_id = None; usage = None; pieces = []; progress = None; finish_usage = None
    for frame in text.split('\n\n'):
        if not frame.strip(): continue
        data = []
        for line in frame.splitlines():
            if line.startswith(':'): continue
            if not line.startswith('data:'): raise ValueError('unsupported_sse_field')
            data.append(line[5:].lstrip(' '))
        if not data: continue
        payload = '\n'.join(data)
        if done: raise ValueError('sse_data_after_done')
        if payload == '[DONE]': done = True; continue
        if usage is not None: raise ValueError('sse_data_after_terminal_usage')
        value = strict_json(payload)
        if (type(value) is not dict or value.get('model') != WORKER_MODEL or value.get('error') is not None
                or type(value.get('id')) is not str or not value['id']):
            raise ValueError('sse_model_identity')
        if stream_id is None: stream_id = value['id']
        if stream_id != value['id']: raise ValueError('mixed_sse_responses')
        choices = value.get('choices')
        if type(choices) is not list or len(choices) > 1: raise ValueError('sse_choices')
        if choices:
            if finished: raise ValueError('sse_output_after_finish')
            choice = choices[0]
            if type(choice) is not dict or type(choice.get('index')) is not int or choice['index'] != 0:
                raise ValueError('sse_choice_index')
            finish = choice.get('finish_reason')
            if finish is not None:
                if finished or finish not in {'stop', 'length', 'tool_calls'}: raise ValueError('sse_finish')
                finished = True
            elif finished: raise ValueError('sse_output_after_finish')
            delta = choice.get('delta', {})
            if type(delta) is not dict: raise ValueError('sse_delta_required')
            if 'role' in delta:
                if delta['role'] != 'assistant': raise ValueError('sse_assistant_role_required')
                role_seen = True
            content = delta.get('content')
            if content is not None:
                if type(content) is not str: raise ValueError('sse_content_string_required')
                pieces.append(content)
        raw_usage = value.get('usage')
        if raw_usage is not None:
            current = wire_usage(raw_usage, output_bound)
            if progress is not None:
                previous, previous_raw = progress
                if current['input_tokens'] != previous['input_tokens'] or current['output_tokens'] < previous['output_tokens']:
                    raise ValueError('nonmonotonic_sse_usage')
                for field in ('prompt_tokens_details', 'completion_tokens_details'):
                    for key, old in (previous_raw.get(field) or {}).items():
                        new = (raw_usage.get(field) or {}).get(key)
                        if new is None or (new != old if field == 'prompt_tokens_details' else new < old):
                            raise ValueError('conflicting_sse_usage_details')
            if choices:
                progress = (current, raw_usage)
                if finished: finish_usage = (current, raw_usage)
            else:
                if not finished: raise ValueError('premature_terminal_sse_usage')
                if finish_usage is not None:
                    final_at_finish, detail_at_finish = finish_usage
                    if current != final_at_finish: raise ValueError('finish_terminal_usage_conflict')
                    for field in ('prompt_tokens_details', 'completion_tokens_details'):
                        for key, old in (detail_at_finish.get(field) or {}).items():
                            if (raw_usage.get(field) or {}).get(key) != old:
                                raise ValueError('finish_terminal_details_conflict')
                usage = current
        elif not choices:
            raise ValueError('terminal_usage_missing')
    # Some valid chat-completion streams omit the initial role delta. The
    # endpoint/choice.delta.content contract supplies assistant output; any
    # explicit non-assistant role above is rejected, never relabeled.
    if not done or not finished or usage is None:
        raise ValueError('complete_assistant_sse_required')
    origin = 'worker_sse_assistant_delta_content' if role_seen else 'worker_sse_role_unspecified_delta_content'
    return ''.join(pieces), usage, origin


def verify_selection(root, manifest_path, *, run_id, config_sha, approvals, started, now):
    """Return approved exact UTF-8 substring, not rewritten/redacted replacement."""
    root = Path(root).absolute()
    if root.resolve() != root or root.name != run_id: raise ValueError('run_prefix_binding')
    if (root / 'launcher-terminal.json').exists(): raise ValueError('after_terminal_excerpt_refused')
    m = strict_json(private_bytes(manifest_path, 32768))
    monitor=type(m) is dict and m.get('schema')=='pex-reviewed-supervisor-selection/v1'
    fields=MANIFEST_FIELDS|({'selection_kind'} if monitor else set())
    if (type(m) is not dict or set(m) != fields or
            m['schema'] not in {'pex-reviewed-worker-selection/v1','pex-reviewed-supervisor-selection/v1'} or
            m['run_id'] != run_id or m['config_sha256'] != config_sha):
        raise ValueError('selection_binding')
    for key in ('config_sha256', 'source_sha256', 'model_excerpt_sha256'):
        if type(m[key]) is not str or not HEX.fullmatch(m[key]): raise ValueError('invalid_digest')
    config_raw = private_bytes(root / 'pair.json', 4 * 1024 * 1024)
    if sha(config_raw) != config_sha: raise ValueError('config_binding')
    config_value = strict_json(config_raw)
    output_bound = config_value.get('profile', {}).get('worker_output_per_call', 4096)
    if type(output_bound) is not int or output_bound not in (4096,16384): raise ValueError('exact_output_profile_required')
    pattern=r'run/supervisor-wire/[0-9a-f]{64}\.json' if monitor else r'run/worker-wire/[0-9a-f]{64}\.json'
    if type(m['source_relative_path']) is not str or not re.fullmatch(pattern, m['source_relative_path']):
        raise ValueError('worker_wire_only')
    triple = (run_id, m['source_sha256'], m['model_excerpt_sha256'])
    if triple not in approvals: raise ValueError('exact_root_approval_required')
    reviewed = timestamp(m['reviewed_utc'])
    if not started <= reviewed <= now + 5: raise ValueError('review_timestamp_binding')
    if monitor:
        from supervisor_excerpts import verify_monitor
        return verify_monitor(root,m,config_sha=config_sha,started=started,now=now)
    artifact = root / m['source_relative_path']
    raw = private_bytes(artifact, (12 if output_bound==16384 else 3) * 1024 * 1024)
    if sha(raw) != m['source_sha256']: raise ValueError('source_changed')
    source = strict_json(raw)
    if (type(source) is not dict or source.get('schema') != 'pex.staged.private-worker-wire.v1'
            or source.get('run_id') != run_id or source.get('config_sha256') != config_sha
            or source.get('arm') not in {'baseline', 'pex'}
            or source.get('HTTP_status') != 200
            or source.get('request_body_or_headers_captured') is not False
            or source.get('usage_validation_code') != 'validated_complete_wire'):
        raise ValueError('wire_identity_or_state')
    call_id = source.get('call_id')
    if type(call_id) is not str or not re.fullmatch(r'[A-Za-z0-9._:-]{1,128}', call_id):
        raise ValueError('call_identity')
    if artifact.name != sha(canonical([source['arm'], call_id]).encode()) + '.json':
        raise ValueError('wire_filename_binding')
    for key in ('request_sha256', 'response_sha256'):
        if type(source.get(key)) is not str or not HEX.fullmatch(source[key]): raise ValueError('wire_digest')
    encoded = source.get('raw_response_base64')
    if type(encoded) is not str: raise ValueError('wire_body_encoding')
    response = base64.b64decode(encoded, validate=True)
    if sha(response) != source['response_sha256']: raise ValueError('response_changed')
    content, parsed_usage, origin = assistant_content(response, source.get('content_type'), output_bound=output_bound)
    text = content.encode('utf-8')
    a, b = m['start_byte'], m['end_byte']
    if type(a) is not int or type(b) is not int or not 0 <= a < b <= len(text) or b - a > 16000:
        raise ValueError('bounded_contiguous_selection_required')
    selected = text[a:b]
    if sha(selected) != m['model_excerpt_sha256']: raise ValueError('selection_changed')
    excerpt = selected.decode('utf-8')
    db = root / 'run/workers.sqlite'
    private_bytes(db, 4 * 1024 * 1024)
    with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=.05) as conn:
        conn.execute('PRAGMA query_only=ON'); conn.execute('BEGIN')
        config = conn.execute('SELECT digest,ir,outr,input_bound,output_bound FROM config').fetchall()
        if config != [(config_sha, 300, 1200, 1048576, output_bound)]: raise ValueError('ledger_config_binding')
        rows = conn.execute('SELECT arm,request_sha,charged,state,receipt FROM calls WHERE id=?', (call_id,)).fetchall()
        conn.rollback()
    if len(rows) != 1: raise ValueError('settled_receipt_required')
    arm, request, charge, state, receipt_raw = rows[0]
    receipt = strict_json(receipt_raw) if type(receipt_raw) is str else None
    if (state != 'settled_raw_wire' or arm != source['arm'] or request != source['request_sha256']
            or type(receipt) is not dict or receipt.get('call_id') != call_id
            or receipt.get('arm') != arm or receipt.get('status') != 200
            or receipt.get('request_sha256') != request
            or receipt.get('response_sha256') != source['response_sha256']
            or receipt.get('usage_validation_code') != 'validated_complete_wire'
            or receipt.get('wire_evidence') != {'path': str(artifact), 'sha256': m['source_sha256']}):
        raise ValueError('settled_wire_receipt_binding')
    usage = receipt.get('usage')
    if type(usage) is not dict or usage != parsed_usage: raise ValueError('validated_usage_required')
    i, o, total = (usage.get(k) for k in ('input_tokens', 'output_tokens', 'total_tokens'))
    if (any(type(n) is not int or n < 0 for n in (i, o, total)) or i > 1048576 or o > output_bound
            or i + o != total or charge != i * 300 + o * 1200):
        raise ValueError('validated_usage_required')
    if (root / 'launcher-terminal.json').exists(): raise ValueError('after_terminal_excerpt_refused')
    return dict(arm=arm, source_sha256=m['source_sha256'], model_excerpt=excerpt,
                model_excerpt_sha256=m['model_excerpt_sha256'], reviewed_utc=m['reviewed_utc'], excerpt_origin=origin)


def drain_approved(root, writer, *, config_sha, seen, now, display_root=None):
    """One writer owns sequence. Invalid/unapproved inbox entries emit no prose."""
    root = Path(root)
    if (root / 'launcher-terminal.json').exists(): return
    display_root = Path(display_root) if display_root is not None else root
    inbox = display_root / 'reviewed-excerpts-inbox'
    if not inbox.exists(): return
    if inbox.resolve() != inbox.absolute() or not inbox.is_dir(): raise ValueError('inbox_path')
    manifests = sorted(inbox.glob('*.json'))
    if len(manifests) > 100: raise ValueError('excerpt_inbox_bound')
    approvals = read_approvals(display_root / 'reviewed-excerpts.json')
    for path in manifests:
        fields = verify_selection(root, path, run_id=writer.run_id, config_sha=config_sha,
                                  approvals=approvals, started=writer.started, now=now)
        identity = (fields['source_sha256'], fields['model_excerpt_sha256'])
        if identity in seen: continue
        writer.emit_reviewed_excerpt(fields, approvals=approvals)
        seen.add(identity)
