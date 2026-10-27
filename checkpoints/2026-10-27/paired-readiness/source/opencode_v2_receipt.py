"""Pinned OpenCode2.1.4 terminal-record validation, not task scoring.

CLI2 JSON omits legacy step events. A natural stop therefore needs both the
fresh captured CLI message identity AND committed post-exit local session rows.
This reader is for an explicitly supplied disposable worker profile only.
"""

from contextlib import contextmanager
import hashlib
import json
import sqlite3
from pathlib import Path
from opencode_cli import (
    CliTurn,
    _constant,
    _float,
    _object,
    MAX_OUTPUT_BYTES,
    MAX_LINE_BYTES,
    MAX_EVENTS,
)


@contextmanager
def _open(path: Path):
    if (
        not path.is_absolute()
        or path.is_symlink()
        or path.resolve() != path
        or not path.is_file()
    ):
        raise ValueError("explicit regular terminal database required")
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)
    db.execute("PRAGMA query_only=ON")
    try:
        yield db
    finally:
        db.close()


def prior_sequence(path: Path, session_id: str | None = None) -> int:
    if not path.exists():
        return 0
    with _open(path) as db:
        if session_id is None:
            raise ValueError("new CLI2 turn requires a fresh disposable profile")
        value = db.execute(
            "SELECT COALESCE(MAX(seq),0) FROM session_message WHERE session_id=?",
            (session_id,),
        ).fetchone()[0]
    if type(value) is not int or value < 0:
        raise ValueError("invalid prior sequence")
    return value


def _json(raw):
    if not isinstance(raw, str) or len(raw.encode()) > 1024 * 1024:
        raise ValueError("terminal row too large")
    return json.loads(
        raw, object_pairs_hook=_object, parse_constant=_constant, parse_float=_float
    )


def completed_turn_v2(
    raw: bytes,
    *,
    exit_code: int,
    database: Path,
    prompt: str,
    after_sequence: int,
    expected_session: str | None = None,
) -> CliTurn:
    if exit_code != 0 or not raw or len(raw) > MAX_OUTPUT_BYTES:
        raise ValueError("unsuccessful bounded CLI2 turn")
    events = []
    messages = []
    session = None
    message_ids = set()
    for line in raw.splitlines():
        if not line or len(line) > MAX_LINE_BYTES or len(events) >= MAX_EVENTS:
            raise ValueError("CLI2 event bound")
        event = _json(line.decode())
        if not isinstance(event, dict) or event.get("type") not in {
            "text",
            "reasoning",
            "tool_use",
        }:
            raise ValueError("unqualified CLI2 event")
        vendor = event.get("sessionID")
        part = event.get("part")
        if (
            not isinstance(vendor, str)
            or not 1 <= len(vendor) <= 256
            or not isinstance(part, dict)
            or part.get("sessionID") != vendor
        ):
            raise ValueError("CLI2 session binding")
        if (
            session is not None
            and session != vendor
            or expected_session is not None
            and vendor != expected_session
        ):
            raise ValueError("CLI2 crossed sessions")
        session = vendor
        message = part.get("messageID")
        if not isinstance(message, str) or not 1 <= len(message) <= 256:
            raise ValueError("CLI2 message identity")
        message_ids.add(message)
        if event["type"] == "text":
            if not isinstance(part.get("text"), str):
                raise ValueError("CLI2 text invalid")
            messages.append(part["text"])
        events.append(event)
    with _open(database) as db:
        session_row = db.execute(
            "SELECT version,idle_outcome FROM session_v2 WHERE id=?", (session,)
        ).fetchone()
        if session_row != ("2.1.4", "succeeded"):
            raise ValueError("CLI2 terminal session not succeeded")
        rows = db.execute(
            "SELECT id,type,seq,data FROM session_message WHERE session_id=? AND seq>? ORDER BY seq LIMIT 1001",
            (session, after_sequence),
        ).fetchall()
        if not rows or len(rows) > 1000:
            raise ValueError("CLI2 terminal row bound")
        if db.execute(
            "SELECT COUNT(*) FROM session_pending WHERE session_id=?", (session,)
        ).fetchone()[0]:
            raise ValueError("CLI2 pending work remains")
        assistants = [r for r in rows if r[1] == "assistant"]
        users = [r for r in rows if r[1] == "user"]
        idle = [r for r in rows if r[1] == "idle"]
        if len(users) != 1 or not assistants or not idle:
            raise ValueError("CLI2 invocation lineage missing")
        user = _json(users[0][3])
        if user.get("text") != prompt:
            raise ValueError("CLI2 prompt changed or duplicated")
        if not message_ids.issubset({r[0] for r in assistants}):
            raise ValueError("CLI2 output not in fresh committed lineage")
        final = assistants[-1]
        payload = _json(final[3])
        outcome = _json(idle[-1][3])
        if (
            final[0] not in message_ids
            or not users[0][2] < final[2] < idle[-1][2]
            or outcome.get("outcome") != "succeeded"
        ):
            raise ValueError("CLI2 final lineage invalid")
        if (
            payload.get("finish") != "stop"
            or payload.get("rawFinish") != "stop"
            or payload.get("error")
            or type(payload.get("time", {}).get("completed")) is not int
        ):
            raise ValueError("CLI2 natural terminal stop unproven")
        content = payload.get("content")
        if not isinstance(content, list):
            raise ValueError("CLI2 committed content invalid")
        committed = [
            p.get("text")
            for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        captured = [
            e["part"].get("text")
            for e in events
            if e["type"] == "text" and e["part"]["messageID"] == final[0]
        ]
        if committed != captured:
            raise ValueError("CLI2 text differs from committed message")
    return CliTurn(
        session, tuple(messages), len(events), hashlib.sha256(raw).hexdigest(), len(raw)
    )
