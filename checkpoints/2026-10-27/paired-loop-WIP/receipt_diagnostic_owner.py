"""WIP failure-safe receipt-diagnostic owner; no network or live entry point.

Injected operations require separate trusted admission. A budget check is NOT a
spending grant. No credential/environment reads, providers, VM or tools on import.
Every fallible pre-wire boundary gets a private fsynced phase first. OS kill or
broken storage cannot be made durable by Python finally; absence stays unknown.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets

RESERVATION=319_488_000
MAX_BODY=2*1024*1024
PHASES=frozenset(('ledger_constructor','reserve','key_metadata','key_read','key_validate',
    'signal_setup','client_constructor','wire_dispatch','response_read','settle_raw',
    'terminal_pre_cleanup','signal_cleanup','client_cleanup','ledger_cleanup'))


def digest(raw):return hashlib.sha256(raw).hexdigest()


def atomic_private(path,raw):
    path=Path(path)
    if (not path.is_absolute() or path.resolve()!=path or not path.parent.is_dir()
            or path.parent.stat().st_uid!=os.geteuid() or path.parent.stat().st_mode&0o077):
        raise ValueError('private_owned_directory_required')
    if type(raw)is not bytes or len(raw)>3*1024*1024:raise ValueError('bounded_private_bytes_required')
    temporary=path.with_name('.'+path.name+'.pending-'+secrets.token_hex(8))
    fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb')as handle:handle.write(raw);handle.flush();os.fsync(handle.fileno())
        os.link(temporary,path,follow_symlinks=False)
    finally:temporary.unlink(missing_ok=True)
    fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'path':str(path),'sha256':digest(raw)}


def publish(path,value):
    return atomic_private(path,json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode())


@dataclass(frozen=True)
class BudgetProof:
    """Arithmetic only. The caller must independently verify actual authority."""
    prior_provider_nanoUSD:int
    approved_cap_nanoUSD:int
    full_reservation_nanoUSD:int=RESERVATION
    def check(self):
        if (any(type(x)is not int or x<0 for x in (self.prior_provider_nanoUSD,self.approved_cap_nanoUSD,self.full_reservation_nanoUSD))
                or self.full_reservation_nanoUSD!=RESERVATION
                or self.prior_provider_nanoUSD+self.full_reservation_nanoUSD>self.approved_cap_nanoUSD):
            raise ValueError('existing_cumulative_cap_cannot_fit_one_full_reservation')


def execute_once(root,identity,budget,request_body,operations):
    """One admitted owner call; all operations are explicit controller callbacks.

    Operations: ledger_factory(root), key_metadata(), key_read(), signal_start(),
    signal_stop(), client_factory(secret), open_response(client). Client/ledger
    expose close(); response context exposes status_code/headers/iter_bytes().
    There are no default transports, retries, alternate routes or live fixtures.
    """
    if type(budget)is not BudgetProof:raise ValueError('exact_budget_proof_required')
    budget.check()  # BEFORE callbacks, credentials, ledger, claim or network.
    if (type(identity)is not dict or set(identity)!={'run_id','config_sha256','call_id'}
            or not re.fullmatch('[a-z0-9-]{1,128}',identity['run_id'])
            or not re.fullmatch('[a-f0-9]{64}',identity['config_sha256'])
            or not re.fullmatch('[A-Za-z0-9._:-]{1,128}',identity['call_id'])):
        raise ValueError('exact_diagnostic_identity_required')
    if type(request_body)is not bytes or not 0<len(request_body)<=MAX_BODY:raise ValueError('bounded_exact_request_required')
    root=Path(root)
    if not root.is_absolute() or root.resolve()!=root or root.parent.stat().st_mode&0o077:
        raise ValueError('new_private_owner_directory_required')
    root.mkdir(mode=0o700)  # Exclusive owner claim; never reopen an old attempt.
    request_pin=atomic_private(root/'request.body.json',request_body)
    ledger=client=secret=None;signal_attempted=False;reserve_attempted=False;reserve_ack=False
    wire_entered=False;body_read_complete=False;transport_complete=False;body=b'';body_pin=None
    status=content_type=None;primary_error=None;fatal=None;seq=0;current_phase='before_ledger'
    cleanup={};journal_errors=[];terminal_persisted=False;terminal=None
    def phase(name):
        nonlocal seq,current_phase
        if name not in PHASES:raise ValueError('allowlisted_phase_required')
        current_phase=name;seq+=1
        return publish(root/('phase-%03d-%s.json'%(seq,name)),{
            'schema':'pex.receipt-diagnostic-owner-phase.v1',**identity,
            'at_utc':datetime.now(timezone.utc).isoformat(),'seq':seq,'phase':name,
            'reserve_acknowledged':reserve_ack,'wire_API_entered':wire_entered})
    def safe_phase(name):
        try:phase(name)
        except BaseException as error:journal_errors.append({'phase':name,'error_class':type(error).__name__})
    def safe_publish(name,value):
        try:return publish(root/name,value)
        except BaseException as error:
            journal_errors.append({'phase':name,'error_class':type(error).__name__});return None
    try:
        phase('ledger_constructor');ledger=operations.ledger_factory(root)
        phase('reserve');reserve_attempted=True
        ledger.reserve(identity['call_id'],request_pin['sha256'],request_body);reserve_ack=True
        phase('key_metadata');operations.key_metadata()
        phase('key_read');secret=operations.key_read()
        phase('key_validate')
        if type(secret)is not str or not 1<=len(secret)<=16384 or any(not 32<ord(c)<127 for c in secret):
            raise ValueError('credential_format_unproven')
        phase('signal_setup');signal_attempted=True;operations.signal_start()
        phase('client_constructor');client=operations.client_factory(secret);secret=None
        phase('wire_dispatch');wire_entered=True
        with operations.open_response(client)as response:
            status=response.status_code;content_type=response.headers.get('content-type','')
            phase('response_read');captured=bytearray()
            try:
                for chunk in response.iter_bytes():
                    if type(chunk)is not bytes:raise TypeError('byte_chunks_required')
                    if len(captured)+len(chunk)>MAX_BODY:
                        captured.extend(chunk[:MAX_BODY-len(captured)]);raise ValueError('response_body_bound')
                    captured.extend(chunk)
                body_read_complete=True
            finally:
                body=bytes(captured)
                body_pin=atomic_private(root/('response.body'if body_read_complete else'response.partial'),body)
        transport_complete=body_read_complete
        if transport_complete:
            phase('settle_raw')
            # Original bytes were published BEFORE entering the strict parser.
            ledger.wire_evidence_sink=lambda *args:body_pin
            ledger.settle_raw(identity['call_id'],request_pin['sha256'],status,content_type,body)
    except BaseException as error:
        primary_error={'phase':current_phase,'error_class':type(error).__name__}
        if not isinstance(error,Exception):fatal=error
    finally:
        secret=None
        charge=budget.full_reservation_nanoUSD if reserve_attempted else None
        state='reservation_outcome_unknown'if reserve_attempted else'not_reserved'
        receipt=None;snapshot_error=None;row_present=None
        if ledger is not None:
            try:
                row=ledger.db.execute('SELECT charged,state,receipt FROM calls WHERE id=?',(identity['call_id'],)).fetchone()
                row_present=row is not None
                if row is not None:
                    charge,state,raw_receipt=row
                    if type(charge)is not int or not 0<=charge<=budget.full_reservation_nanoUSD or state not in ('reserved_uncertain','uncertain','settled_raw_wire'):
                        raise ValueError('stored_diagnostic_row_invalid')
                    receipt=json.loads(raw_receipt)if raw_receipt else None
                    if receipt is not None and type(receipt)is not dict:raise ValueError('stored_diagnostic_receipt_invalid')
            except BaseException as error:
                snapshot_error=type(error).__name__;receipt=None
                charge=budget.full_reservation_nanoUSD if reserve_attempted else None;state='reservation_outcome_unknown'
        terminal={'schema':'pex.receipt-diagnostic-owner-terminal.v1',**identity,
            'at_utc':datetime.now(timezone.utc).isoformat(),'diagnostic_only_not_benchmark':True,
            'request':request_pin,'raw_response':body_pin,'HTTP_status':status,'content_type':content_type,
            'reserve_attempted':reserve_attempted,'reserve_acknowledged':reserve_ack,'ledger_row_present':row_present,
            'wire_API_entered':wire_entered,'body_read_complete':body_read_complete,'transport_complete':transport_complete,
            'state':state,'charged_bound_nanoUSD':charge,
            'provider_cumulative_bound_nanoUSD':None if charge is None else budget.prior_provider_nanoUSD+charge,
            'primary_error':primary_error,'ledger_snapshot_error_class':snapshot_error,
            'usage_validation_code':None if receipt is None else receipt.get('usage_validation_code'),
            'usage':None if receipt is None else receipt.get('usage'),
            'cleanup_results':cleanup,'journal_errors':journal_errors,'cleanup_finished':False,
            'automatic_retry':False,'task_success_or_PEX_lift':None,
            'qualification':'Actual local phase/receipt evidence only. No automatic refund for pre-wire failure, no OS-exit claim. OS kill or unavailable storage may still prevent a final record; absence stays unknown.'}
        safe_phase('terminal_pre_cleanup');safe_publish('terminal-before-cleanup.json',terminal)
        for name,operation,attempt in (
                ('signal_cleanup',lambda:operations.signal_stop(),signal_attempted),
                ('client_cleanup',lambda:client.close(),client is not None),
                ('ledger_cleanup',lambda:ledger.close(),ledger is not None)):
            cleanup[name]={'attempted':attempt}
            if not attempt:continue
            safe_phase(name)
            try:operation();cleanup[name]['completed']=True
            except BaseException as error:cleanup[name].update(completed=False,error_class=type(error).__name__)
        terminal['cleanup_finished']=True
        terminal['at_utc']=datetime.now(timezone.utc).isoformat()
        terminal_persisted=safe_publish('terminal.json',terminal)is not None
    if fatal is not None:raise fatal
    return terminal,terminal_persisted
