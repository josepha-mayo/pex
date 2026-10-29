"""Durable cumulative compute envelope; accounting only, never VM authority.

Prior full-lifetime upper bounds must be independently evidenced by the caller.
Ambiguous create attempts retain the full generic reservation permanently.
"""
import re
import sqlite3
from pathlib import Path

CAP=100_000_000
RESERVATION=48_840_000
VERIFIED_FULL_LIFETIME=9_982_500

class ComputeBudget:
    def __init__(self,path,*,prior_upper_bound_nano_usd,evidence_sha256,cap_nano_usd=CAP):
        path=Path(path)
        if type(cap_nano_usd)is not int or cap_nano_usd not in (CAP,120_000_000,140_000_000):
            raise ValueError('explicit supported compute ceiling required')
        self.cap=cap_nano_usd
        if type(prior_upper_bound_nano_usd)is not int or not 0<=prior_upper_bound_nano_usd<=self.cap:
            raise ValueError('invalid predecessor compute bound')
        if type(evidence_sha256)is not str or not re.fullmatch('[0-9a-f]{64}',evidence_sha256):
            raise ValueError('independent predecessor evidence required')
        if not path.is_absolute() or path.resolve()!=path or path.parent.stat().st_mode&0o077:
            raise ValueError('private compute ledger required')
        if path.exists() and (path.is_symlink() or path.stat().st_mode&0o077):raise ValueError('private compute ledger required')
        self.db=sqlite3.connect(path,isolation_level=None);path.chmod(0o600)
        self.db.execute('CREATE TABLE IF NOT EXISTS config(prior INTEGER,evidence TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS ceiling(value INTEGER)')
        self.db.execute('CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,charged INTEGER,state TEXT)')
        self.expected=(prior_upper_bound_nano_usd,evidence_sha256)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            rows=self.db.execute('SELECT * FROM config').fetchall()
            limits=self.db.execute('SELECT value FROM ceiling').fetchall()
            if not limits:
                if rows and self.cap!=CAP:raise ValueError('legacy compute ceiling cannot be increased')
                self.db.execute('INSERT INTO ceiling VALUES (?)',(self.cap,))
            elif limits!=[(self.cap,)]:raise ValueError('compute ceiling identity changed')
            if not rows:self.db.execute('INSERT INTO config VALUES (?,?)',self.expected)
            elif rows!=[self.expected]:raise ValueError('predecessor compute identity changed')
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');self.db.close();raise

    def _total(self):
        if self.db.execute('SELECT * FROM config').fetchall()!=[self.expected]:raise ValueError('compute configuration changed')
        if self.db.execute('SELECT value FROM ceiling').fetchall()!=[(self.cap,)]:raise ValueError('compute ceiling changed')
        rows=self.db.execute('SELECT charged,state FROM calls').fetchall()
        for charge,state in rows:
            if type(charge)is not int or (charge,state) not in ((RESERVATION,'uncertain'),(VERIFIED_FULL_LIFETIME,'verified_full_lifetime')):raise ValueError('compute accounting corrupt')
        total=self.expected[0]+sum(r[0] for r in rows)
        if total>self.cap:raise ValueError('compute envelope exceeded')
        return total

    def reserve(self,identity):
        if type(identity)is not str or not identity or len(identity)>256:raise ValueError('compute identity required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self._total()+RESERVATION>self.cap:raise ValueError('cumulative compute reservation refused')
            self.db.execute('INSERT INTO calls VALUES (?,?,?)',(identity,RESERVATION,'uncertain'))
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise

    def settle_verified_allocation(self,identity,*,cpu,memory_mb,max_seconds):
        if (type(cpu),type(memory_mb),type(max_seconds))!=(int,int,int) or (cpu,memory_mb,max_seconds)!=(2,512,330):raise ValueError('exact verified allocation required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._total()
            if self.db.execute('SELECT charged,state FROM calls WHERE id=?',(identity,)).fetchall()!=[(RESERVATION,'uncertain')]:raise ValueError('single reserved compute identity required')
            self.db.execute('UPDATE calls SET charged=?,state=? WHERE id=?',(VERIFIED_FULL_LIFETIME,'verified_full_lifetime',identity))
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise

    def total(self):return self._total()
    def close(self):self.db.close()
