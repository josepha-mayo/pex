"""Controller-owned durable reservations. Local caps are NOT provider cash caps."""

import json
import os
import re
import sqlite3
from dataclasses import asdict, replace
from pathlib import Path


class PilotBudgetExhausted(ValueError):
    """Typed terminal admission result; never a worker/task-quality failure."""
    def __init__(self, code):
        messages = {
            "budget_reservation_refused": "budget reservation refused",
            "global_attempt_cap_refused": "global attempt cap refused",
        }
        if code not in messages:
            raise ValueError("invalid budget terminal code")
        self.code = code
        super().__init__(messages[code])


def integer(value, limit=10**15):
    if type(value) is not int or not 0 <= value <= limit:
        raise ValueError("invalid accounting integer")
    return value


class Ledger:
    def __init__(
        self,
        path: Path,
        *,
        budget: int,
        input_rate: int,
        output_rate: int,
        route,
        currency: str,
        pricing_provenance_sha256: str,
        input_token_bound: int | None = None,
        output_token_bound: int | None = None,
        approved_routes: tuple | None = None,
        max_attempts: int | None = None,
    ):
        # Caller-supplied binding is not authorization. Public live entry still denies.
        from managed_chat import Route

        if type(route) is not Route:
            raise ValueError("exact typed route required")
        if type(currency) is not str or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("explicit currency required")
        if type(pricing_provenance_sha256) is not str or not re.fullmatch(
            r"[a-f0-9]{64}", pricing_provenance_sha256
        ):
            raise ValueError("pricing provenance digest required")
        # This profile is a documented provider envelope, not caller-estimated tokens.
        # It grants no live authority; actual transport admission remains separate.
        split = input_token_bound is not None or output_token_bound is not None
        if split:
            if (
                type(input_token_bound) is not int
                or type(output_token_bound) is not int
                or (input_token_bound, output_token_bound) != (262144, 4096)
                or route.endpoint != "https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions"
                or route.model_id != "nvidia/nemotron-3-super-120b-a12b"
                or route.output_field != "max_completion_tokens"
                or not 1 <= route.limits.max_output_tokens <= 4096
                or (input_rate, output_rate, currency) != (300, 900, "USD")
            ):
                raise ValueError("split envelope requires pinned Nebius route/pricing/limits")
            self.envelope = ("nebius-nemotron-super-20261027", input_token_bound, output_token_bound)
            self.reservation = integer(input_token_bound * input_rate + output_token_bound * output_rate)
        else:
            self.envelope = ("authored-legacy", None, None)
            self.reservation = integer(route.limits.max_usage_tokens * max(input_rate, output_rate))
        self.input_bound, self.output_bound = input_token_bound, output_token_bound
        if approved_routes is not None or max_attempts is not None:
            if (
                not split or type(approved_routes) is not tuple
                or len(approved_routes) != 2
                or any(type(r) is not Route for r in approved_routes)
                or route.role != "planner"
                or sorted(r.role for r in approved_routes) != ["planner", "verifier"]
                or route not in approved_routes
                or any(replace(r, role=route.role, limits=replace(r.limits, max_output_tokens=route.limits.max_output_tokens)) != route for r in approved_routes)
                or any(not 1 <= r.limits.max_output_tokens <= 4096 for r in approved_routes)
                or type(max_attempts) is not int or max_attempts != 12
                or type(budget) is not int or budget != 250000000
            ):
                raise ValueError("shared pilot requires exact two roles, quarter-dollar cap and 12 attempts")
            routes = tuple(sorted(approved_routes, key=lambda r: r.role))
        else:
            routes = (route,)
        self.routes = {r.fingerprint: r for r in routes}
        self.route_identities = tuple((r.fingerprint, r.endpoint, r.model_id, r.role) for r in routes)
        self.max_attempts = max_attempts
        self.route = route
        self.currency = currency
        self.provenance = pricing_provenance_sha256
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
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS pricing_identity (fingerprint TEXT, endpoint TEXT, model TEXT, role TEXT, currency TEXT, provenance TEXT)"
        )
        identity = (
            route.fingerprint,
            route.endpoint,
            route.model_id,
            route.role,
            currency,
            pricing_provenance_sha256,
        )
        stored_identity = self.db.execute("SELECT * FROM pricing_identity").fetchall()
        if fresh and not stored_identity:
            self.db.execute(
                "INSERT INTO pricing_identity VALUES (?,?,?,?,?,?)", identity
            )
        elif stored_identity != [identity]:
            self.db.close()
            raise ValueError("route/currency/pricing provenance identity changed")
        self.identity = identity
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS reservation_identity (profile TEXT, input_bound INTEGER, output_bound INTEGER)"
        )
        stored_envelope = self.db.execute("SELECT * FROM reservation_identity").fetchall()
        if fresh and not stored_envelope:
            self.db.execute("INSERT INTO reservation_identity VALUES (?,?,?)", self.envelope)
        elif stored_envelope != [self.envelope]:
            self.db.close()
            raise ValueError("reservation envelope identity changed; new ledger required")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS approved_route_identity (fingerprint TEXT, endpoint TEXT, model TEXT, role TEXT)"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS pilot_limits (max_attempts INTEGER)")
        stored_routes = tuple(self.db.execute("SELECT * FROM approved_route_identity ORDER BY role").fetchall())
        stored_limits = self.db.execute("SELECT * FROM pilot_limits").fetchall()
        if fresh and not stored_routes and not stored_limits:
            self.db.executemany("INSERT INTO approved_route_identity VALUES (?,?,?,?)", self.route_identities)
            self.db.execute("INSERT INTO pilot_limits VALUES (?)", (max_attempts,))
        elif stored_routes != self.route_identities or stored_limits != [(max_attempts,)]:
            self.db.close()
            raise ValueError("approved routes/attempt identity changed; new ledger required")
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
        if (
            tuple(self.db.execute("SELECT * FROM approved_route_identity ORDER BY role").fetchall()) != self.route_identities
            or self.db.execute("SELECT * FROM pilot_limits").fetchall() != [(self.max_attempts,)]
        ):
            raise ValueError("stored approved routes/attempt limit corrupt")
        count = self.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]
        if self.max_attempts is not None and count > self.max_attempts:
            raise ValueError("stored global attempt cap exceeded")
        if self.db.execute("SELECT * FROM reservation_identity").fetchall() != [self.envelope]:
            raise ValueError("stored reservation envelope corrupt")
        if self.db.execute("SELECT * FROM pricing_identity").fetchall() != [
            self.identity
        ]:
            raise ValueError("stored route/currency/pricing provenance corrupt")
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
                or route not in self.routes
                or integer(reserved) != self.reservation
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
                    or receipt.get("model_id") != self.routes[route].model_id
                    or receipt.get("role") != self.routes[route].role
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
                    self._validate_usage_bounds(i, o, route)
                    if i + o != t or i * self.ir + o * self.outr != charged:
                        raise ValueError("stored usage charge corrupt")
            total += charged
        if total > self.budget:
            raise ValueError("stored budget exceeded")
        return total

    def _validate_usage_bounds(self, input_tokens, output_tokens, route_fingerprint):
        if self.input_bound is not None and (
            input_tokens > self.input_bound or output_tokens > min(self.output_bound, self.routes[route_fingerprint].limits.max_output_tokens)
        ):
            raise ValueError("raw-wire usage exceeds split token envelope")

    def reserve(self, call_id, route):
        from managed_chat import Route

        if (
            type(route) is not Route
            or self.routes.get(route.fingerprint) != route
        ):
            raise ValueError("route does not match pinned pricing")
        if not re.fullmatch(r"[a-zA-Z0-9._-]{1,128}", call_id):
            raise ValueError("invalid invocation identity")
        # Conservative configured upper envelope, NOT a tokenizer estimate.
        amount = self.reservation
        self.db.execute("BEGIN IMMEDIATE")
        try:
            spent = self._validate_stored()
            if self.max_attempts is not None and self.db.execute("SELECT COUNT(*) FROM calls").fetchone()[0] >= self.max_attempts:
                raise PilotBudgetExhausted("global_attempt_cap_refused")
            if amount + spent > self.budget:
                raise PilotBudgetExhausted("budget_reservation_refused")
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
        if (
            receipt.invocation_id != call_id
            or receipt.route_fingerprint != row[0]
            or row[0] not in self.routes
            or receipt.model_id != self.routes[row[0]].model_id
            or receipt.role != self.routes[row[0]].role
        ):
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
            self._validate_usage_bounds(i, o, row[0])
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
