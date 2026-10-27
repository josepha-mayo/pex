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
            "CREATE TABLE IF NOT EXISTS config (budget INTEGER CHECK(typeof(budget)='integer' AND budget>0), ir INTEGER CHECK(typeof(ir)='integer' AND ir>0), outr INTEGER CHECK(typeof(outr)='integer' AND outr>0))"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS calls (id TEXT PRIMARY KEY, route TEXT CHECK(typeof(route)='text' AND length(route)=64), reserve INTEGER CHECK(typeof(reserve)='integer' AND reserve>0), charged INTEGER CHECK(typeof(charged)='integer' AND charged>=0 AND charged<=reserve), state TEXT CHECK(state IN ('reserved_uncertain','uncertain','settled_raw_wire')), receipt TEXT)"
        )
        expected = (budget, input_rate, output_rate)
        rows = self.db.execute("SELECT * FROM config").fetchall()
        if fresh and not rows:
            self.db.execute("INSERT INTO config VALUES (?,?,?)", expected)
        elif rows != [expected]:
            self.db.close()
            raise ValueError("pricing/budget identity changed")
        self.budget, self.ir, self.outr = expected
        try:
            self._validate_stored()
        except BaseException:
            self.db.close()
            raise

    def _validate_stored(self):
        config = self.db.execute("SELECT budget,ir,outr FROM config").fetchall()
        if config != [(self.budget, self.ir, self.outr)] or any(
            type(x) is not int for x in config[0]
        ):
            raise ValueError("stored pricing/budget corrupt")
        total = 0
        for call_id, route, reserved, charged, state, raw in self.db.execute(
            "SELECT id,route,reserve,charged,state,receipt FROM calls"
        ):
            if (
                type(call_id) is not str
                or not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", call_id)
                or type(route) is not str
                or not re.fullmatch(r"[a-f0-9]{64}", route)
                or integer(reserved) == 0
                or integer(charged) > reserved
                or state not in ("reserved_uncertain", "uncertain", "settled_raw_wire")
            ):
                raise ValueError("stored accounting corrupt")
            if state != "settled_raw_wire" and charged != reserved:
                raise ValueError("uncertain charge reduced")
            if state == "reserved_uncertain":
                if raw is not None:
                    raise ValueError("unexpected pending receipt")
            else:
                if type(raw) is not str or len(raw) > 16384:
                    raise ValueError("stored receipt corrupt")
                receipt = json.loads(raw)
                if (
                    type(receipt) is not dict
                    or receipt.get("invocation_id") != call_id
                    or receipt.get("route_fingerprint") != route
                ):
                    raise ValueError("stored receipt identity corrupt")
                if state == "settled_raw_wire":
                    usage = receipt.get("usage")
                    if (
                        receipt.get("outcome") != "succeeded"
                        or receipt.get("dispatch_state") != "response_complete"
                        or receipt.get("attempts") != 1
                        or receipt.get("http_status") != 200
                        or type(usage) is not dict
                    ):
                        raise ValueError("stored settlement corrupt")
                    i, o, t = (
                        integer(usage.get(k))
                        for k in ("input_tokens", "output_tokens", "total_tokens")
                    )
                    if i + o != t or i * self.ir + o * self.outr != charged:
                        raise ValueError("stored usage charge corrupt")
            total += charged
        if total > self.budget:
            raise ValueError("stored budget exceeded")
        return total

    def reserve(self, call_id, route):
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", call_id):
            raise ValueError("invalid invocation identity")
        # Conservative configured upper envelope, NOT a tokenizer estimate.
        amount = integer(route.limits.max_usage_tokens * max(self.ir, self.outr))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            spent = self._validate_stored()
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
        from managed_chat import Receipt

        if receipt is not None and type(receipt) is not Receipt:
            raise ValueError("raw-wire receipt required")
        if receipt is None:
            return  # crash/missing response retains FULL reservation, no retry
        if receipt.invocation_id != call_id or receipt.route_fingerprint != row[0]:
            raise ValueError("receipt identity mismatch")
        charge = row[1]
        state = "uncertain"
        if (
            receipt.outcome == "succeeded"
            and receipt.attempts == 1
            and receipt.http_status == 200
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
