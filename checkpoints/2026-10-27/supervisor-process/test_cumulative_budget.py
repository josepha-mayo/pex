import hashlib
import json
import sqlite3
import pytest
from cumulative_budget import audit_closed, continuation_fits

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

@pytest.fixture
def ledgers(tmp_path):
    w=tmp_path/"worker.sqlite";s=tmp_path/"supervisor.sqlite"
    c=sqlite3.connect(w)
    c.execute("CREATE TABLE calls(arm,reserved,charged,state,receipt)")
    for arm in ("baseline","pex"):
        for _ in range(10):
            r=dict(arm=arm,status=200,usage=dict(input_tokens=10,output_tokens=2,total_tokens=12))
            c.execute("INSERT INTO calls VALUES (?,?,?,?,?)",(arm,319488000,5400,"settled_raw_wire",json.dumps(r)))
    c.commit();c.close()
    c=sqlite3.connect(s);c.execute("CREATE TABLE pilot_admission(state)");c.execute("INSERT INTO pilot_admission VALUES ('closed')")
    c.execute("CREATE TABLE calls(reserve,charged,state)")
    c.execute("INSERT INTO calls VALUES (82329600,82329600,'uncertain')")
    c.commit();c.close()
    return w,s

def audit(pair):
    w,s=pair;return audit_closed(w,digest(w),s,digest(s))

def test_preserves_pool_and_global_attempts(ledgers):
    before=[digest(p) for p in ledgers]
    r=audit(ledgers)
    assert r["remaining_attempts"]==dict(baseline=2,pex=2,supervisor=11)
    assert r["remaining_nano_usd"]["supervisor"]==167670400
    assert r["remaining_total_nano_usd"]==917562400
    assert [digest(p) for p in ledgers]==before

def test_changed_snapshot_denied(ledgers):
    w,s=ledgers
    with pytest.raises(ValueError):audit_closed(w,"0"*64,s,digest(s))

def test_open_predecessor_denied(ledgers):
    w,s=ledgers;c=sqlite3.connect(s);c.execute("UPDATE pilot_admission SET state='active'");c.commit();c.close()
    with pytest.raises(ValueError):audit(ledgers)

def test_uncertain_worker_not_refunded(ledgers):
    w,s=ledgers;c=sqlite3.connect(w);c.execute("UPDATE calls SET state='uncertain'");c.commit();c.close()
    with pytest.raises(ValueError):audit(ledgers)

def test_compute_continuation_not_reset(ledgers):
    r=audit(ledgers)
    assert not continuation_fits(r,1,1,2,97680000)
    assert not continuation_fits(r,1,1,2,19965000)
    assert continuation_fits(r,1,1,1,19965000)
    assert not continuation_fits(r,10,1,0,19965000)

def test_prior_supervisor_refund_not_trusted(ledgers):
    w,s=ledgers;c=sqlite3.connect(s);c.execute("UPDATE calls SET charged=0");c.commit();c.close()
    assert audit(ledgers)["charged_nano_usd"]["supervisor"]==82329600


@pytest.mark.parametrize("suffix", ["-wal", "-journal"])
def test_unpinned_sidecar_rejected(ledgers, suffix):
    w,s=ledgers
    from pathlib import Path
    Path(str(w)+suffix).write_bytes(b"unhashed accounting updates")
    with pytest.raises(ValueError, match="uncheckpointed"):
        audit(ledgers)


def test_queries_exact_hashed_snapshot_not_reopened_path(ledgers, monkeypatch):
    from pathlib import Path
    w,s=ledgers
    expected=digest(w)
    original=Path.read_bytes
    def replace_after_read(path):
        data=original(path)
        if path==w:
            db=sqlite3.connect(w)
            db.execute("DELETE FROM calls")
            db.commit();db.close()
        return data
    monkeypatch.setattr(Path,"read_bytes",replace_after_read)
    result=audit_closed(w,expected,s,digest(s))
    assert result["attempts"]["baseline"]==10
    assert result["attempts"]["pex"]==10


def test_wal_format_main_file_not_silently_accepted(ledgers):
    w,s=ledgers
    data=bytearray(w.read_bytes());data[18:20]=b"\x02\x02"
    w.write_bytes(data)
    with pytest.raises(ValueError,match="rollback-mode"):
        audit(ledgers)


def test_interrupted_diagnostic_reserved_uncertain_is_retained(ledgers,tmp_path):
    from cumulative_budget import include_supervisor_diagnostics
    p=tmp_path/'diagnostic.sqlite'
    db=sqlite3.connect(p);db.execute('CREATE TABLE calls(reserve,charged,state)')
    db.execute("INSERT INTO calls VALUES(82329600,82329600,'reserved_uncertain')");db.commit();db.close()
    result=include_supervisor_diagnostics(audit(ledgers),[{'path':str(p),'sha256':digest(p)}])
    assert result['charged_nano_usd']['supervisor']==164659200
    assert result['remaining_nano_usd']['supervisor']==85340800
    assert result['remaining_attempts']['supervisor']==10
    with pytest.raises(ValueError,match='unique'):
        include_supervisor_diagnostics(audit(ledgers),[{'path':str(p),'sha256':digest(p)}]*2)
