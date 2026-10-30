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
# Conservative next-pair admission bound, not a user spending limit.
# Retains 431182500 historical liability plus both 111000000 reservations.
NEXT_PAIR_ENVELOPE=653_182_500
# Pair19 ConnectTimeout remains fully charged; bound both next create attempts.
NEXT_RETRY_ENVELOPE=764_182_500
# Next fresh pair includes all pair20 verified charges; no historical reset.
OBSERVATION_RETRY_ENVELOPE=809_557_500
# New task retains pair21/diagnostic history; exact independent grant still required.
ASYNCPOOL_PAIR_ENVELOPE=832_245_000
# Pair05 unknown creation remains fully charged; next pair adds two reserves.
ASYNCPOOL_RETRY_ENVELOPE=943_245_000
# Pair06 actual verified full lifetimes retained before repaired fresh comparison.
ASYNCPOOL_REPAIRED_ENVELOPE=988_620_000
# Pair07 verified lifetimes retained; buffered-connect recovery adds no VM time.
ASYNCPOOL_CONNECT_RETRY_ENVELOPE=1_033_995_000
# Pair08 interrupted by tool policy; retain its verified full VM lifetime.
ASYNCPOOL_POLICY_RETRY_ENVELOPE=1_056_682_500

def allocation_bounds(vm_seconds):
    if type(vm_seconds) is not int or vm_seconds not in (330,750):
        raise ValueError('exact supported compute lifetime required')
    return (RESERVATION,VERIFIED_FULL_LIFETIME) if vm_seconds==330 else (111_000_000,22_687_500)

class ComputeBudget:
    def __init__(self,path,*,prior_upper_bound_nano_usd,evidence_sha256,cap_nano_usd=CAP,vm_seconds=330):
        path=Path(path)
        if type(cap_nano_usd)is not int or cap_nano_usd not in (CAP,120_000_000,140_000_000,250_000_000,500_000_000,NEXT_PAIR_ENVELOPE,NEXT_RETRY_ENVELOPE,OBSERVATION_RETRY_ENVELOPE,ASYNCPOOL_PAIR_ENVELOPE,ASYNCPOOL_RETRY_ENVELOPE,ASYNCPOOL_REPAIRED_ENVELOPE,ASYNCPOOL_CONNECT_RETRY_ENVELOPE,ASYNCPOOL_POLICY_RETRY_ENVELOPE):
            raise ValueError('explicit supported compute ceiling required')
        self.cap=cap_nano_usd
        self.vm_seconds=vm_seconds
        self.reservation,self.verified_full_lifetime=allocation_bounds(vm_seconds)
        self.allocation=(2,512,vm_seconds,self.reservation,self.verified_full_lifetime)
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
        self.db.execute('CREATE TABLE IF NOT EXISTS allocation(cpu INTEGER,memory INTEGER,seconds INTEGER,reservation INTEGER,verified INTEGER)')
        self.db.execute('CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,charged INTEGER,state TEXT)')
        self.expected=(prior_upper_bound_nano_usd,evidence_sha256)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            rows=self.db.execute('SELECT * FROM config').fetchall()
            limits=self.db.execute('SELECT value FROM ceiling').fetchall()
            allocations=self.db.execute('SELECT * FROM allocation').fetchall()
            if not allocations:
                if rows and self.vm_seconds!=330:raise ValueError('legacy compute allocation cannot be changed')
                self.db.execute('INSERT INTO allocation VALUES (?,?,?,?,?)',self.allocation)
            elif allocations!=[self.allocation]:raise ValueError('compute allocation identity changed')
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
        if self.db.execute('SELECT * FROM allocation').fetchall()!=[self.allocation]:raise ValueError('compute allocation changed')
        rows=self.db.execute('SELECT charged,state FROM calls').fetchall()
        for charge,state in rows:
            if type(charge)is not int or (charge,state) not in ((self.reservation,'uncertain'),(self.verified_full_lifetime,'verified_full_lifetime')):raise ValueError('compute accounting corrupt')
        total=self.expected[0]+sum(r[0] for r in rows)
        if total>self.cap:raise ValueError('compute envelope exceeded')
        return total

    def reserve(self,identity):
        if type(identity)is not str or not identity or len(identity)>256:raise ValueError('compute identity required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self._total()+self.reservation>self.cap:raise ValueError('cumulative compute reservation refused')
            self.db.execute('INSERT INTO calls VALUES (?,?,?)',(identity,self.reservation,'uncertain'))
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise

    def settle_verified_allocation(self,identity,*,cpu,memory_mb,max_seconds):
        if (type(cpu),type(memory_mb),type(max_seconds))!=(int,int,int) or (cpu,memory_mb,max_seconds)!=(2,512,self.vm_seconds):raise ValueError('exact verified allocation required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self._total()
            if self.db.execute('SELECT charged,state FROM calls WHERE id=?',(identity,)).fetchall()!=[(self.reservation,'uncertain')]:raise ValueError('single reserved compute identity required')
            self.db.execute('UPDATE calls SET charged=?,state=? WHERE id=?',(self.verified_full_lifetime,'verified_full_lifetime',identity))
            self.db.execute('COMMIT')
        except BaseException:self.db.execute('ROLLBACK');raise

    def total(self):return self._total()
    def close(self):self.db.close()
