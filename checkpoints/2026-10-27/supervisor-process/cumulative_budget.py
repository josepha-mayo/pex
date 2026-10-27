"""Read-only continuation audit; this never grants authority or opens a new ledger."""
import hashlib
import json
import sqlite3
from pathlib import Path

CAPS = {"baseline":375000000, "pex":375000000, "supervisor":250000000}
WORKER_RESERVATION = 319488000
SUPERVISOR_RESERVATION = 82329600
COMPUTE_CAP = 100000000
COMPUTE_RESERVATION = 48840000

def _db(path, expected):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("closed ledger file required")
    # A main-file digest cannot authenticate WAL or rollback-journal changes.
    # Require a checkpointed, quiescent predecessor instead of reading sidecars.
    for suffix in ("-wal", "-journal"):
        sidecar=Path(str(path)+suffix)
        if sidecar.is_symlink() or (sidecar.exists() and sidecar.stat().st_size):
            raise ValueError("uncheckpointed predecessor ledger")
    data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected:
        raise ValueError("predecessor ledger identity changed")
    if data[18:20] != b"\x01\x01":
        raise ValueError("rollback-mode closed ledger snapshot required")
    # Query exactly the hashed bytes, not a pathname that can change after hashing.
    db=sqlite3.connect(":memory:")
    try:
        db.deserialize(data)
    except Exception:
        db.close()
        raise
    db.execute("PRAGMA query_only=ON")
    return db

def _integer(x):
    if type(x) is not int or x<0: raise ValueError("invalid charge/count")
    return x

def audit_closed(worker_path, worker_sha256, supervisor_path, supervisor_sha256):
    """Pinned quiescent predecessor files only; uncertain charges are never refunded."""
    charges={k:0 for k in CAPS}; attempts={k:0 for k in CAPS}
    worker=_db(worker_path,worker_sha256)
    supervisor=_db(supervisor_path,supervisor_sha256)
    try:
        if any(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='predecessor'").fetchone() for db in (worker,supervisor)):
            raise ValueError("successor ledger requires full predecessor-chain audit")
        if supervisor.execute("SELECT state FROM pilot_admission").fetchall()!=[("closed",)]:
            raise ValueError("predecessor pilot not closed")
        for arm,reserve,charge,state,receipt in worker.execute(
                "SELECT arm,reserved,charged,state,receipt FROM calls"):
            if arm not in ("baseline","pex") or reserve!=WORKER_RESERVATION:
                raise ValueError("worker predecessor reservation mismatch")
            _integer(charge)
            if state=="settled_raw_wire":
                r=json.loads(receipt); u=r["usage"]
                i,o,t=(_integer(u[k]) for k in ("input_tokens","output_tokens","total_tokens"))
                if (r["status"]!=200 or r["arm"]!=arm or i+o!=t or i>1048576
                        or o>4096 or charge!=i*300+o*1200):
                    raise ValueError("worker predecessor settlement invalid")
            elif state not in ("uncertain","reserved_uncertain") or charge!=reserve:
                raise ValueError("uncertain worker debit reduced")
            charges[arm]+=charge; attempts[arm]+=1
        for reserve,charge,state in supervisor.execute("SELECT reserve,charged,state FROM calls"):
            if reserve!=SUPERVISOR_RESERVATION or _integer(charge)>reserve:
                raise ValueError("supervisor predecessor reservation mismatch")
            # Conservative audit: retain FULL bound for every prior supervisor call.
            # Never interpret a no-dispatch receipt as permission to refund it.
            charges["supervisor"]+=reserve; attempts["supervisor"]+=1
    finally:
        worker.close();supervisor.close()
    if any(charges[k]>CAPS[k] or attempts[k]>12 for k in CAPS):
        raise ValueError("predecessor exceeds existing limits")
    return {"authority":"none_read_only_audit",
            "predecessor_sha256":{"worker":worker_sha256,"supervisor":supervisor_sha256},
            "charged_nano_usd":charges,"attempts":attempts,
            "remaining_nano_usd":{k:CAPS[k]-charges[k] for k in CAPS},
            "remaining_attempts":{k:12-attempts[k] for k in CAPS},
            "remaining_total_nano_usd":sum(CAPS.values())-sum(charges.values())}

def continuation_fits(audit, worker_calls_each, supervisor_calls, compute_create_attempts,
                      prior_compute_reserved_nano_usd):
    """Conservative pre-admission check; true still is NOT approval or activation."""
    w,s,n,p=map(_integer,(worker_calls_each,supervisor_calls,compute_create_attempts,
                         prior_compute_reserved_nano_usd))
    counts={"baseline":w,"pex":w,"supervisor":s}
    reserve={"baseline":WORKER_RESERVATION,"pex":WORKER_RESERVATION,
             "supervisor":SUPERVISOR_RESERVATION}
    return (p+n*COMPUTE_RESERVATION<=COMPUTE_CAP and
            all(counts[k]<=audit["remaining_attempts"][k] and
                counts[k]*reserve[k]<=audit["remaining_nano_usd"][k] for k in CAPS))


def include_supervisor_diagnostics(audit, snapshots, *, allocation_profile="legacy"):

    """Retain interrupted reservations; rebate only validated raw-wire settlements.

    Caller supplies the complete independently pinned predecessor list. This
    function is read-only and cannot determine authorization or discover runs.
    """
    if allocation_profile not in ("legacy","350m-350m-300m-v1","250m-250m-500m-v2","200m-200m-600m-v3"):
        raise ValueError("unknown preregistered allocation")
    caps={
        "legacy":CAPS,
        "350m-350m-300m-v1":{"baseline":350000000,"pex":350000000,"supervisor":300000000},
        "250m-250m-500m-v2":{"baseline":250000000,"pex":250000000,"supervisor":500000000},
        "200m-200m-600m-v3":{"baseline":200000000,"pex":200000000,"supervisor":600000000},
    }[allocation_profile]
    result=json.loads(json.dumps(audit))
    seen=set()
    for item in snapshots:
        if set(item)!={'path','sha256'} or item['path'] in seen:
            raise ValueError('unique pinned diagnostic predecessors required')
        seen.add(item['path'])
        db=_db(item['path'],item['sha256'])
        try:
            for reserve,charged,state,raw,call_id,route in db.execute('SELECT reserve,charged,state,receipt,id,route FROM calls'):
                if reserve!=SUPERVISOR_RESERVATION or _integer(charged)>reserve:
                    raise ValueError('diagnostic reservation mismatch')
                if state=='settled_raw_wire':
                    r=json.loads(raw);u=r['usage']
                    i,o,t=(_integer(u[k]) for k in ('input_tokens','output_tokens','total_tokens'))
                    cap={'planner':1200,'verifier':900}.get(r.get('role'),0)
                    if (r.get('invocation_id')!=call_id or r.get('route_fingerprint')!=route
                            or r.get('model_id')!='nvidia/nemotron-3-super-120b-a12b'
                            or r.get('outcome')!='succeeded' or r.get('dispatch_state')!='response_complete'
                            or r.get('http_status')!=200 or r.get('attempts')!=1
                            or i>262144 or not cap or o>cap or i+o!=t or charged!=i*300+o*900):
                        raise ValueError('diagnostic raw-wire settlement invalid')
                    debit=charged
                elif state in ('reserved_uncertain','uncertain') and charged==reserve:
                    debit=reserve
                else:raise ValueError('diagnostic uncertainty cannot be refunded')
                result['charged_nano_usd']['supervisor']+=debit
                result['attempts']['supervisor']+=1
        finally:db.close()
    result['remaining_nano_usd']={k:caps[k]-result['charged_nano_usd'][k] for k in caps}
    result['remaining_attempts']={k:12-result['attempts'][k] for k in CAPS}
    result['remaining_total_nano_usd']=sum(result['remaining_nano_usd'].values())
    if min(result['remaining_nano_usd'].values())<0 or min(result['remaining_attempts'].values())<0:
        raise ValueError('cumulative diagnostic envelope exceeded')
    return result
