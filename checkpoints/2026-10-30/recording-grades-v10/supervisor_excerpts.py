"""Offline monitor response verifier. Never reads request bodies or executes tools.

The settled receipt attests actual protocol acceptance. This observer additionally
checks raw identity/usage and a narrower text-or-single-final-tool subset. It does
not re-run the invocation history, approve the decision, or claim its efficacy.
"""
import base64
import datetime as dt
import math
import re
import sqlite3

from record_support import HEX, canonical, sha, timestamp
from reviewed_excerpts import private_bytes, strict_json

MODEL='nvidia/nemotron-3-super-120b-a12b'
ENDPOINT='https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions'
FINAL={'planner':'SupervisorDecision','verifier':'IndependentVerifierDecision'}
PROTOCOL_PINS={'pex_supervisor.loop':'2c62e5b93aba14ff4f6fb7739f574d364dab83a95a77345d8e0bc7f0d5168768',
               'pex_protocol.actions':'e8aa8fee7540287929d8c913bddc3ac731adc3b71a0d137247bee0877759e2ae'}
ACTIONS={'NOOP','ANNOTATE','NOTIFY','SEND_NUDGE','INJECT_CONTEXT','CONTINUE_SESSION','REQUEST_VERIFICATION',
         'RESPOND_PERMISSION','APPLY_OVERLAY','REVERT_OVERLAY','FRESH_HANDOFF','START_AGENT','STOP_AGENT',
         'FORK_PROBE','CLEANUP','FOCUS_UI','ASK_HUMAN'}


def final_arguments(raw, role):
    if type(raw) is not str or not 1 <= len(raw.encode()) <= 16384: raise ValueError('bounded_final_arguments')
    value=strict_json(raw)
    required={'rationale','action_type'} if role=='planner' else {'rationale','approved'}
    allowed=required|{'evidence','evidence_refs'}|({'message','payload','confidence','risk'} if role=='planner' else set())
    if type(value) is not dict or not required <= set(value) or not set(value) <= allowed:
        raise ValueError('final_argument_fields')
    if type(value['rationale']) is not str or not 1 <= len(value['rationale']) <= 2000:
        raise ValueError('final_rationale')
    for key in ('evidence','evidence_refs'):
        x=value.get(key,[])
        if type(x) is not list or len(x)>20 or any(type(s) is not str for s in x): raise ValueError('final_evidence_fields')
    if role=='verifier':
        if type(value['approved']) is not bool: raise ValueError('final_approval_boolean')
    else:
        if value['action_type'] not in ACTIONS: raise ValueError('final_action_enum')
        if type(value.get('message','')) is not str or len(value.get('message',''))>4000: raise ValueError('final_message')
        if type(value.get('payload',{})) is not dict: raise ValueError('final_payload')
        n=value.get('confidence',.6)
        if type(n) not in (int,float) or not math.isfinite(n) or not 0<=n<=1: raise ValueError('final_confidence')
        if value.get('risk','low') not in {'none','low','medium','high','irreversible'}: raise ValueError('final_risk')
    return raw  # EXACT original argument string, never json.dumps(value).


def monitor_usage(raw, role):
    required={'prompt_tokens','completion_tokens','total_tokens'}
    optional={'prompt_tokens_details','completion_tokens_details','prompt_cache_hit_tokens','prompt_cache_miss_tokens'}
    if type(raw) is not dict or not required <= set(raw) or not set(raw)<=required|optional: raise ValueError('monitor_usage_shape')
    i,o,t=(raw[k] for k in ('prompt_tokens','completion_tokens','total_tokens'))
    if (any(type(n) is not int or not 1<=n<=266240 for n in (i,o,t)) or i+o!=t or i>262144
            or o>(1200 if role=='planner' else 900)): raise ValueError('monitor_usage_bound')
    cache={'prompt_cache_hit_tokens','prompt_cache_miss_tokens'} & set(raw)
    if cache:
        if len(cache)!=2: raise ValueError('monitor_cache_partition')
        hit,miss=raw['prompt_cache_hit_tokens'],raw['prompt_cache_miss_tokens']
        if any(type(n) is not int or not 0<=n<=i for n in (hit,miss)) or hit+miss!=i: raise ValueError('monitor_cache_partition')
        details=raw.get('prompt_tokens_details')
        if isinstance(details,dict) and details.get('cached_tokens') is not None and details['cached_tokens']!=hit:
            raise ValueError('monitor_cache_disagreement')
    for key,cap,allowed in [('prompt_tokens_details',i,{'cached_tokens','cache_write_tokens','created_cache_tokens','audio_tokens','multimodal_tokens'}),
                           ('completion_tokens_details',o,{'reasoning_tokens','audio_tokens','accepted_prediction_tokens','rejected_prediction_tokens'})]:
        d=raw.get(key)
        if d is None: continue
        if type(d) is not dict or not set(d)<=allowed: raise ValueError('monitor_usage_details')
        d={k:v for k,v in d.items() if v is not None}
        if 'multimodal_tokens' in d or any(type(n) is not int or not 0<=n<=cap for n in d.values()): raise ValueError('monitor_usage_details')
        if any(d.get(k,0)!=0 for k in ('audio_tokens','cache_write_tokens','created_cache_tokens','accepted_prediction_tokens','rejected_prediction_tokens')):
            raise ValueError('monitor_unsupported_usage_details')
    return dict(input_tokens=i,output_tokens=o,total_tokens=t)


def monitor_content(body, role, selection_kind, config):
    if (type(body) is not dict or body.get('model')!=MODEL or body.get('object')!='chat.completion'
            or body.get('error') is not None): raise ValueError('monitor_response_identity')
    usage=monitor_usage(body.get('usage'),role)
    choices=body.get('choices')
    if type(choices) is not list or len(choices)!=1 or type(choices[0]) is not dict: raise ValueError('monitor_choice')
    choice=choices[0];message=choice.get('message')
    if (type(choice.get('index')) is not int or choice['index']!=0 or type(message) is not dict
            or message.get('role')!='assistant' or message.get('refusal') is not None
            or message.get('function_call') is not None): raise ValueError('monitor_assistant_message')
    content=message.get('content')
    if content is not None and (type(content) is not str or len(content.encode())>2*1024*1024 or '\x00' in content):
        raise ValueError('monitor_content')
    if choice.get('finish_reason')=='stop' and selection_kind=='assistant_content':
        if message.get('tool_calls') is not None or type(content) is not str or not content.strip(): raise ValueError('monitor_stop_shape')
        return content,usage,'supervisor_json_assistant_content'
    if choice.get('finish_reason')!='tool_calls' or selection_kind!='final_tool_arguments': raise ValueError('monitor_selection_kind')
    calls=message.get('tool_calls')
    if type(calls) is not list or len(calls)!=1 or type(calls[0]) is not dict or set(calls[0])!={'id','type','function'}:
        raise ValueError('single_final_tool_only')
    call=calls[0];function=call['function']
    if (call['type']!='function' or type(call['id']) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',call['id'])
            or type(function) is not dict or set(function)!={'name','arguments'} or function['name']!=FINAL[role]):
        raise ValueError('final_tool_identity')
    for name,digest in PROTOCOL_PINS.items():
        if config.get('sources',{}).get(name,{}).get('sha256')!=digest: raise ValueError('final_protocol_source_changed')
    return final_arguments(function['arguments'],role),usage,'supervisor_json_final_tool_arguments'


def verify_monitor(root, m, *, config_sha, started, now):
    if not re.fullmatch(r'run/supervisor-wire/[0-9a-f]{64}\.json',m['source_relative_path']): raise ValueError('monitor_response_path')
    artifact=root/m['source_relative_path'];raw=private_bytes(artifact,5*1024*1024)
    if sha(raw)!=m['source_sha256']: raise ValueError('monitor_artifact_changed')
    s=strict_json(raw)
    if (type(s) is not dict or s.get('schema')!='pex.staged.private-supervisor-wire.v1' or s.get('kind')!='response'
            or s.get('run_id')!=root.name or s.get('config_sha256')!=config_sha or s.get('role') not in FINAL
            or s.get('model_id')!=MODEL or s.get('endpoint')!=ENDPOINT or s.get('HTTP_status')!=200
            or s.get('content_type')!='application/json' or s.get('complete_bounded_body') is not True
            or s.get('request_headers_captured') is not False): raise ValueError('monitor_archive_identity')
    invocation=s.get('invocation_id');role=s['role'];route=s.get('route_fingerprint')
    if type(invocation) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',invocation): raise ValueError('monitor_invocation')
    for val in (route,s.get('body_sha256')):
        if type(val) is not str or not HEX.fullmatch(val): raise ValueError('monitor_digest')
    if artifact.name!=sha(canonical([invocation,'response']).encode())+'.json': raise ValueError('monitor_filename')
    captured=s.get('captured_at_utc')
    if type(captured) is not str: raise ValueError('monitor_archive_time')
    observed=dt.datetime.fromisoformat(captured)
    if observed.tzinfo is None or observed.utcoffset()!=dt.timedelta(0): raise ValueError('monitor_archive_utc')
    if not started<=observed.timestamp()<=timestamp(m['reviewed_utc'])<=now+5: raise ValueError('monitor_archive_review_order')
    captured=observed.isoformat(timespec='microseconds').replace('+00:00','Z')
    body_raw=base64.b64decode(s['raw_body_base64'],validate=True)
    if not 1<=len(body_raw)<=2*1024*1024 or sha(body_raw)!=s['body_sha256']: raise ValueError('monitor_body_changed')
    config=strict_json(private_bytes(root/'pair.json',4*1024*1024))
    content,usage,origin=monitor_content(strict_json(body_raw),role,m['selection_kind'],config)
    text=content.encode();a,b=m['start_byte'],m['end_byte']
    if type(a) is not int or type(b) is not int or not 0<=a<b<=len(text) or b-a>16000: raise ValueError('monitor_selection_bound')
    selected=text[a:b]
    if sha(selected)!=m['model_excerpt_sha256']: raise ValueError('monitor_selection_changed')
    excerpt=selected.decode('utf-8');db=root/'run/supervisor.sqlite';private_bytes(db,4*1024*1024)
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=.05) as c:
        c.execute('PRAGMA query_only=ON');c.execute('BEGIN')
        if c.execute('SELECT ir,outr FROM config').fetchall()!=[(300,900)]: raise ValueError('monitor_pricing_binding')
        if c.execute('SELECT endpoint,model,role FROM approved_route_identity WHERE fingerprint=?',(route,)).fetchall()!=[(ENDPOINT,MODEL,role)]: raise ValueError('monitor_route_binding')
        rows=c.execute('SELECT route,reserve,charged,state,receipt FROM calls WHERE id=?',(invocation,)).fetchall()
        captures=c.execute('SELECT kind,role,route,body_sha256,artifact_path,artifact_sha256 FROM staged_supervisor_wire WHERE invocation_id=?',(invocation,)).fetchall();c.rollback()
    expected=('response',role,route,s['body_sha256'],str(artifact),m['source_sha256'])
    if expected not in captures or len(captures)!=2 or not any(x[0]=='request' and x[1:3]==(role,route) for x in captures): raise ValueError('monitor_aux_capture_binding')
    if len(rows)!=1: raise ValueError('monitor_settled_receipt')
    actual_route,reserve,charged,state,receipt_raw=rows[0];receipt=strict_json(receipt_raw)
    required={'invocation_id':invocation,'route_fingerprint':route,'model_id':MODEL,'role':role,
        'attempts':1,'dispatch_state':'response_complete','outcome':'succeeded','reason':'validated_response','http_status':200}
    if (actual_route!=route or reserve!=262144*300+4096*900 or state!='settled_raw_wire' or
            type(receipt) is not dict or any(receipt.get(k)!=v for k,v in required.items())
            or type(receipt.get('attempts')) is not int or type(receipt.get('http_status')) is not int): raise ValueError('monitor_receipt_binding')
    ru=receipt.get('usage')
    if type(ru) is not dict or any(ru.get(k)!=v or type(ru.get(k)) is not int for k,v in usage.items()) or charged!=usage['input_tokens']*300+usage['output_tokens']*900:
        raise ValueError('monitor_usage_receipt_binding')
    if (root/'launcher-terminal.json').exists(): raise ValueError('after_terminal_excerpt_refused')
    return dict(arm='pex',source_sha256=m['source_sha256'],model_excerpt=excerpt,
        model_excerpt_sha256=m['model_excerpt_sha256'],reviewed_utc=m['reviewed_utc'],excerpt_origin=origin,
        supervisor_role=role,source_captured_utc=captured)
