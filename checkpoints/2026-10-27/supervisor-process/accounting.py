"""Controller-owned durable reservations. Local caps are NOT provider cash caps."""

import json
import os
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path


def integer(value, limit=10**15):
    if type(value) is not int or not 0 <= value <= limit:
        raise ValueError("invalid accounting integer")
    return value


class Ledger:
    def __init__(self, path: Path, *, budget: int, input_rate: int, output_rate: int):
        # Rates in integer nano-currency units PER token, no floating/zero fallback.
        for value in (budget, input_rate, output_rate):
            if integer(value) == 0:
                raise ValueError("explicit positive budget and pricing required")
        if (
            not path.is_absolute()
            or path.parent.resolve(strict=True) != path.parent
            or path.is_symlink()
        ):
            raise ValueError("controller ledger path invalid")
        fresh = not path.exists()
        if not fresh and (not path.is_file() or path.stat().st_nlink != 1):
            raise ValueError("controller ledger must be regular unlinked file")
        if fresh:
            fd = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
            )
            os.close(fd)
        self.db = sqlite3.connect(path, timeout=1, isolation_level=None)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS config (budget INTEGER, ir INTEGER, outr INTEGER)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, route TEXT, reserve INTEGER, charged INTEGER, state TEXT, receipt TEXT)"
        )
        expected = (budget, input_rate, output_rate)
        rows = self.db.execute("SELECT * FROM config").fetchall()
        if fresh and not rows:
            self.db.execute("INSERT INTO config VALUES (?,?,?)", expected)
        elif rows != [expected]:
            raise ValueError("pricing/budget identity changed")
        self.budget, self.ir, self.outr = expected

    def reserve(self, call_id, route):
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", call_id):
            raise ValueError("invalid invocation identity")
        # Conservative configured upper envelope, NOT a tokenizer estimate.
        amount = integer(route.limits.max_usage_tokens * max(self.ir, self.outr))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            spent = self.db.execute(
                "SELECT COALESCE(SUM(charged),0) FROM calls"
            ).fetchone()[0]
            if amount + spent > self.budget:
                raise ValueError("budget reservation refused")
            self.db.execute(
                "INSERT INTO calls VALUES (?,?,?,?,?,?)",
                (
                    call_id,
                    route.fingerprint,
                    amount,
                    amount,
                    "reserved_uncertain",
                    None,
                ),
            )
            self.db.execute("COMMIT")  # durable BEFORE any transport constructor
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def settle(self, call_id, receipt):
        row = self.db.execute(
            "SELECT route,reserve,state FROM calls WHERE id=?", (call_id,)
        ).fetchone()
        if row is None or row[2] != "reserved_uncertain":
            raise ValueError("missing or previously settled reservation")
        if receipt is None:
            return  # crash/missing response retains FULL reservation, no retry
        if receipt.invocation_id != call_id or receipt.route_fingerprint != row[0]:
            raise ValueError("receipt identity mismatch")
        charge = row[1]
        state = "uncertain"
        if (
            receipt.outcome == "succeeded"
            and receipt.dispatch_state == "response_complete"
            and receipt.usage is not None
        ):
            usage = receipt.usage
            i, o, t = (
                integer(x)
                for x in (usage.input_tokens, usage.output_tokens, usage.total_tokens)
            )
            if i + o != t:
                raise ValueError("invalid raw-wire usage")
            charge = integer(i * self.ir + o * self.outr)
            if charge > row[1]:
                raise ValueError("actual usage exceeds reserved envelope")
            state = "settled_raw_wire"
        # Even preflight refusal retains reservation: conservative, no automatic rebate.
        changed = self.db.execute(
            "UPDATE calls SET charged=?,state=?,receipt=? WHERE id=? AND state=?",
            (
                charge,
                state,
                json.dumps(asdict(receipt), sort_keys=True),
                call_id,
                "reserved_uncertain",
            ),
        ).rowcount
        if changed != 1:
            raise ValueError("reservation already settled concurrently")

    def summary(self):
        return [
            {"id": r[0], "reserved": r[1], "charged": r[2], "state": r[3]}
            for r in self.db.execute(
                "SELECT id,reserve,charged,state FROM calls ORDER BY id"
            )
        ]

    def close(self):
        self.db.close()
