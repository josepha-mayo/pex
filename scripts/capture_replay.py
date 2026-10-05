"""Export a live PEX session's stored event ledger as a replayable fixture.

Reads the demo-home sqlite directly (no running bridge needed), dedups the
OpenCode SSE frame stream to its completed forms, maps the supervision-
relevant events onto the recorded-replay schema, and reconstructs the
workspace mutations from the worker's own edit/write tool calls.

    uv run python scripts/capture_replay.py \
        --home build/demo/home-<utc>/pex-home \
        --session opencode:ses_... \
        --workspace build/demo/live-<utc>/workspace \
        --seed false-test-claim \
        --out fixtures/demo/captured_live_eval.json

The output is a *recorded replay* fixture: deterministic, still labeled
`not_live_control`, and scored by `scripts/eval_replays.py` like any other
fixture. It is evidence of what the pipeline saw — not a claim that the
replay is the live run.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_events(db_path: Path, session_id: str) -> list[dict]:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = db.execute(
            "select json from events where session_id = ? order by ts",
            (session_id,),
        ).fetchall()
    finally:
        db.close()
    if not rows:
        raise SystemExit(f"no events stored for session {session_id!r} in {db_path}")
    return [json.loads(raw) for (raw,) in rows]


def _load_goal(db_path: Path, goal_id: str) -> dict:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        try:
            row = db.execute("select json from goals where id = ?", (goal_id,)).fetchone()
        except sqlite3.OperationalError:
            row = None
    finally:
        db.close()
    if not row:
        raise SystemExit(f"goal {goal_id!r} not found in {db_path}")
    return json.loads(row[0])


_PROTOCOL_DELTA = re.compile(r"^(assistant|user|system|[a-z_]+\.[a-z_.]+)$")


def _dedup_frames(events: list[dict]) -> list[dict]:
    """Collapse literal SSE re-deliveries (same key, type, tool, delta) to
    their last frame. Distinct message parts under one parent — text parts,
    role markers, transport fallbacks — all carry different deltas and stay,
    because each is a distinct observation the live pipeline ingested."""

    latest: dict[tuple, int] = {}
    for index, event in enumerate(events):
        meta = event.get("metadata") or {}
        lineage = meta.get("opencode_message_lineage") or {}
        call_id = meta.get("opencode_tool_call_id")
        if call_id:
            # Pending vs completed tool frames differ only in payload — the
            # completed frame (last) is the real observation.
            key = (call_id, event.get("event_type"))
        else:
            key = (
                lineage.get("message_id") or event.get("event_id"),
                event.get("event_type"),
                event.get("tool_name"),
                event.get("message_delta"),
            )
        latest[key] = index
    keep = set(latest.values())
    return [event for index, event in enumerate(events) if index in keep]


def _relpath(file_path: str, workspace: str) -> str | None:
    try:
        rel = PurePosixPath(Path(file_path).as_posix()).relative_to(
            PurePosixPath(Path(workspace).as_posix())
        )
    except ValueError:
        return None
    return str(rel)


def _seed_files(seed: str, tamper: bool) -> dict[str, str]:
    from scripts.opencode_recovery_once import seed_scenario

    with tempfile.TemporaryDirectory(prefix="pex-capture-seed-") as tmp:
        root = Path(tmp)
        seed_scenario(root, seed)
        if tamper and (root / "verify.py").exists():
            (root / "verify.py").unlink()
        return {
            p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted(root.rglob("*"))
            if p.is_file() and ".git" not in p.parts
        }


def export(
    db_path: Path,
    session_id: str,
    workspace: str,
    seed_files: dict[str, str],
    title: str,
    reconcile_disk: Path | None = None,
    fixture_id: str | None = None,
) -> dict:
    events = _dedup_frames(_load_events(db_path, session_id))
    goal_id = next((e.get("goal_id") for e in events if e.get("goal_id")), None)
    if goal_id is None:
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = db.execute("select json from sessions where id = ?", (session_id,)).fetchone()
        finally:
            db.close()
        goal_id = json.loads(row[0]).get("goal_id") if row else None
    goal_row = _load_goal(db_path, goal_id) if goal_id else {}

    file_state = dict(seed_files)
    fixture_events: list[dict] = []
    mutations: list[dict] = []

    def apply_edit(tool_input: dict) -> str | None:
        rel = _relpath(str(tool_input.get("filePath") or ""), workspace)
        if rel is None:
            return None
        if "content" in tool_input:
            file_state[rel] = tool_input["content"]
        else:
            old = tool_input.get("oldString")
            new = tool_input.get("newString")
            current = file_state.get(rel)
            if current is None or old is None or old not in current:
                return rel
            file_state[rel] = current.replace(old, new, 1)
        return rel

    for event in events:
        etype = event.get("event_type")
        tool = event.get("tool_name")
        tool_input = event.get("tool_input") or {}

        if etype == "user_prompt":
            text = (event.get("message_delta") or "").strip()
            if not text or _PROTOCOL_DELTA.match(text):
                continue
            fixture_events.append({"event_type": "user_prompt", "message": text})
        elif etype == "agent_response":
            text = (event.get("message_delta") or "").strip()
            # Role markers and SSE transport echoes are not prose claims.
            if text and not _PROTOCOL_DELTA.match(text):
                fixture_events.append({"event_type": "agent_response", "message": text})
        elif etype == "tool_call" and tool in {"edit", "write"}:
            rel = apply_edit(tool_input)
            if rel is None:
                continue  # outside the workspace — not part of the fixture
            fixture_events.append(
                {
                    "event_type": "file_edit",
                    "message": f"{tool} {rel}",
                    "file_paths": [rel],
                }
            )
            mutations.append(
                {
                    "after": len(fixture_events) - 1,
                    "files": {rel: file_state[rel]},
                }
            )
        elif tool == "bash":
            command = event.get("command") or tool_input.get("command")
            if not command:
                continue
            entry: dict = {"event_type": "shell", "command": command}
            process_state = event.get("process_state")
            if process_state:
                entry["process_state"] = process_state
            fixture_events.append(entry)
        elif etype == "stop":
            fixture_events.append(
                {
                    "event_type": "stop",
                    "message": event.get("message_delta") or "",
                }
            )
        # status / agent_thought / tool_result frames are transport detail,
        # not supervision signal — the replay schema has no slot for them.

    if reconcile_disk is not None and fixture_events:
        # Workers can write files through arbitrary shell commands, which no
        # tool frame instruments. Reconcile the reconstructed state against
        # the recorded bytes on disk, as an honestly labeled event placed
        # before the terminal frame — the same place the live verifier read
        # the file.
        drifted = []
        for rel, reconstructed in file_state.items():
            disk = reconcile_disk / rel
            if not disk.is_file():
                continue
            try:
                actual = disk.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if actual != reconstructed:
                file_state[rel] = actual
                drifted.append((rel, actual))
        if drifted:
            # The uninstrumented write actually landed before the last
            # validating run: place the reconciliation just before the final
            # green pytest (or the terminal stop when no green run exists),
            # so earlier claims still see the tampered surface and the final
            # claim sees the recorded bytes — matching what the live verifier
            # read from disk.
            insert_at = next(
                (
                    i
                    for i in range(len(fixture_events) - 1, -1, -1)
                    if fixture_events[i]["event_type"] == "stop"
                ),
                len(fixture_events),
            )
            for i in range(insert_at - 1, -1, -1):
                candidate = fixture_events[i]
                if candidate["event_type"] != "shell":
                    continue
                pytest_state = (candidate.get("process_state") or {}).get("pytest") or {}
                if pytest_state.get("ok") is True:
                    insert_at = i
                    break
            for mutation in mutations:
                if int(mutation["after"]) >= insert_at:
                    mutation["after"] = int(mutation["after"]) + len(drifted)
            for rel, actual in drifted:
                fixture_events.insert(
                    insert_at,
                    {
                        "event_type": "file_edit",
                        "message": (
                            f"captured: {rel} reconciled to recorded bytes "
                            "(uninstrumented write path)"
                        ),
                        "file_paths": [rel],
                    },
                )
                mutations.append({"after": insert_at, "files": {rel: actual}})
                insert_at += 1

    fixture = {
        "id": fixture_id or f"captured-{session_id.split(':')[-1][:24]}",
        "title": title,
        "replay": True,
        "not_live_control": True,
        "captured_from_live_session": session_id,
        "goal": {
            # project_id must satisfy the BoundedId pattern — a live workspace
            # path (drive letters, separators) is not one.
            "project_id": "captured-live",
            "title": goal_row.get("title") or title,
            "objective": goal_row.get("objective") or "",
            "acceptance_criteria": goal_row.get("acceptance_criteria") or [],
            "evidence_requirements": goal_row.get("evidence_requirements") or [],
        },
        "workspace": {"files": seed_files, "mutations": mutations},
        "events": fixture_events,
    }
    return fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--home",
        required=True,
        type=Path,
        help="demo home dir containing pex.sqlite (or its pex-home child)",
    )
    parser.add_argument("--session", required=True)
    parser.add_argument(
        "--workspace",
        required=True,
        help="absolute path of the live workspace (for filePath relativizing)",
    )
    parser.add_argument(
        "--seed",
        default="false-test-claim",
        help="seed scenario name used to regenerate the initial files",
    )
    parser.add_argument(
        "--tamper",
        action="store_true",
        help="drop verify.py from the seed (matches --scenario tamper)",
    )
    parser.add_argument("--title", default="Captured live run")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    home = args.home
    nested = home / "pex-home" / "pex.sqlite"
    db = nested if nested.exists() else home / "pex.sqlite"
    if not db.exists():
        raise SystemExit(f"pex.sqlite not found under {home}")

    seed_files = _seed_files(args.seed, args.tamper)
    disk = Path(args.workspace)
    fixture = export(
        db,
        session_id=args.session,
        workspace=args.workspace,
        seed_files=seed_files,
        title=args.title,
        reconcile_disk=disk if disk.is_dir() else None,
        # Keep the fixture id aligned with its filename so list_fixtures
        # reports the id the replay endpoint actually resolves.
        fixture_id=args.out.stem if args.out else None,
    )
    out = args.out or Path(f"{fixture['id']}.json")
    out.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    print(
        f"wrote {out}: {len(fixture['events'])} events, "
        f"{len(fixture['workspace']['mutations'])} mutations, "
        f"{len(seed_files)} seed files"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
