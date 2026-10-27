"""Real SQLite/WAL with authored records; no real worker data or inference."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_web_owner_http as authored_http
from pex_bridge.store import Store
from pex_bridge.web_owner_http import create_web_owner_auth_app
from pex_bridge.web_owner_workspace import OwnerWorkspaceReader, _ReadView
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.goal import Goal
from pex_protocol.session import HarnessSession

NOW = datetime(2026, 10, 26, tzinfo=UTC)


class WorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "authored.sqlite"
        self.writer = Store(self.path)
        await self.writer.connect()
        await self.writer.db.execute("PRAGMA wal_autocheckpoint=0")
        self.reader = OwnerWorkspaceReader(self.path)

    async def asyncTearDown(self):
        await self.writer.close()
        self.directory.cleanup()

    async def seed(self):
        goal = Goal(
            id="g1",
            project_id="synthetic-project",
            title="Verify an authored task",
            objective="PRIVATE OBJECTIVE MUST NOT LEAK",
            created_at=NOW,
            updated_at=NOW,
        )
        await self.writer.create_goal_with_ledger(goal, [])
        session = HarnessSession(
            id="s1",
            harness_type=HarnessType.OPENCODE,
            vendor_session_id="PRIVATE VENDOR",
            status=SessionStatus.WORKING,
            last_activity=NOW,
            cwd="/private/path",
            metadata={"secret": "PRIVATE METADATA"},
        )
        await self.writer.db.execute(
            "INSERT INTO sessions(id,json) VALUES (?,?)", (session.id, session.model_dump_json())
        )
        await self.writer.db.commit()

    async def test_real_wal_committed_rows_and_allowlisted_projection(self):
        await self.seed()
        self.assertTrue(Path(str(self.path) + "-wal").exists())
        with patch.object(Store, "connect", side_effect=AssertionError("no startup")):
            result = await self.reader.read_workspace()
        self.assertEqual(result["schema"], "pex.owner-workspace.v1")
        self.assertEqual(result["sessions"][0]["status"], "working")
        self.assertEqual(result["goals"][0]["completion"]["status"], "uncertain")
        self.assertEqual(
            result["goals"][0]["completion"]["reason"], "no_current_supported_completion_evidence"
        )
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("/private", json.dumps(result))
        self.assertEqual(
            set(result["sessions"][0]), {"id", "harness_type", "status", "goal_id", "last_activity"}
        )
        self.assertEqual(set(result["goals"][0]), {"id", "title", "paused", "completion"})

    async def test_evidence_failure_does_not_blank_workspace(self):
        await self.seed()
        event_path = Path(self.directory.name) / "authored-events.jsonl"
        event_path.write_text("incomplete")
        reader = OwnerWorkspaceReader(self.path, event_path=event_path)
        result = await reader.read_workspace()
        self.assertEqual(result["run_evidence"], {"state": "unavailable"})
        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual(len(result["goals"]), 1)
        self.assertEqual(
            (await self.reader.read_workspace())["run_evidence"], {"state": "not_configured"}
        )

    async def test_uncommitted_rows_are_not_visible(self):
        await self.seed()
        await self.writer.db.execute("BEGIN IMMEDIATE")
        await self.writer.db.execute("DELETE FROM sessions")
        result = await self.reader.read_workspace()
        self.assertEqual(len(result["sessions"]), 1)
        await self.writer.db.rollback()

    async def test_read_connection_refuses_writes_even_with_query_only_disabled(self):
        await self.seed()
        async with _ReadView(self.path)._pooled_connection() as db:
            self.assertEqual((await (await db.execute("PRAGMA query_only")).fetchone())[0], 1)
            for sql in (
                "DELETE FROM sessions",
                "CREATE TABLE forbidden(x)",
                "UPDATE goals SET intent_revision=99",
            ):
                with self.assertRaises(sqlite3.OperationalError):
                    await db.execute(sql)
            await db.execute("PRAGMA query_only=OFF")
            with self.assertRaises(sqlite3.OperationalError):
                await db.execute("DELETE FROM sessions")
        self.assertEqual(len((await self.reader.read_workspace())["sessions"]), 1)

    async def test_missing_database_not_created_and_no_migrations(self):
        missing = Path(self.directory.name) / "missing.sqlite"
        with self.assertRaises(sqlite3.OperationalError):
            await OwnerWorkspaceReader(missing).read_workspace()
        self.assertFalse(missing.exists())
        with self.assertRaises(RuntimeError):
            await _ReadView(self.path).connect()

    async def test_quarantined_or_corrupt_intent_fails_closed(self):
        legacy = Path(self.directory.name) / "legacy-authored.sqlite"
        with sqlite3.connect(legacy) as db:
            db.execute(
                "CREATE TABLE goals(id TEXT,intent_revision INTEGER,intent_hash TEXT,json TEXT)"
            )
            db.execute("INSERT INTO goals VALUES ('g1',NULL,NULL,'{}')")
        with self.assertRaises(ValueError):
            await OwnerWorkspaceReader(legacy).read_workspace()
        with sqlite3.connect(legacy) as db:
            self.assertEqual(
                db.execute("SELECT intent_revision,intent_hash FROM goals").fetchone(), (None, None)
            )

    async def test_twenty_row_bound_and_truncation(self):
        await self.seed()
        row = await (await self.writer.db.execute("SELECT json FROM sessions")).fetchone()
        for n in range(21):
            value = json.loads(row[0])
            value["id"] = f"session-{n}"
            await self.writer.db.execute(
                "INSERT INTO sessions(id,json) VALUES (?,?)", (value["id"], json.dumps(value))
            )
        await self.writer.db.commit()
        result = await self.reader.read_workspace()
        self.assertEqual(len(result["sessions"]), 20)
        self.assertTrue(result["truncated"]["sessions"])
        self.assertLessEqual(len(json.dumps(result).encode()), 32768)

    async def test_relative_path_rejected(self):
        with self.assertRaises(ValueError):
            OwnerWorkspaceReader(Path("relative.sqlite"))


class WorkspaceHttpTests(unittest.IsolatedAsyncioTestCase):
    asyncTearDown = WorkspaceTests.asyncTearDown
    seed = WorkspaceTests.seed

    async def asyncSetUp(self):
        await WorkspaceTests.asyncSetUp(self)
        self.http = authored_http.OwnerHttpTests()
        self.http.setUp()
        self.http.app = create_web_owner_auth_app(self.http.sessions, workspace=self.reader)

    async def workspace_request(self, cookie=None, **kwargs):
        return await self.http.request(
            "/owner/workspace",
            "GET",
            headers=self.http.auth_headers(cookie) if cookie else [(b"host", authored_http.HOST)],
            **kwargs,
        )

    async def test_owner_only_real_sqlite_projection(self):
        await self.seed()
        self.http.response(await self.workspace_request(), 401)
        cookie, _ = await self.http.signed_in()
        _, payload = self.http.response(await self.workspace_request(cookie), 200)
        self.assertEqual(payload["sessions"][0]["id"], "s1")
        self.assertNotIn("PRIVATE", json.dumps(payload))

    async def test_unconfigured_and_reader_error_hide_details(self):
        cookie, _ = await self.http.signed_in()
        self.http.app = create_web_owner_auth_app(self.http.sessions)
        self.http.response(await self.workspace_request(cookie), 503)
        self.http.app = create_web_owner_auth_app(self.http.sessions, workspace=self.reader)
        with patch.object(
            self.reader, "read_workspace", AsyncMock(side_effect=RuntimeError("PRIVATE PATH"))
        ):
            _, payload = self.http.response(await self.workspace_request(cookie), 503)
            self.assertNotIn("PRIVATE", json.dumps(payload))

    async def test_expiry_or_logout_during_reader_never_releases_rows(self):
        for action in ("expire", "logout"):
            cookie, csrf = await self.http.signed_in()

            async def delayed(action=action, cookie=cookie, csrf=csrf):
                if action == "expire":
                    self.http.now += 4000
                else:
                    self.http.sessions.logout(self.http.auth_headers(cookie, csrf))
                return {"private": "MUST NOT LEAK"}

            with patch.object(self.reader, "read_workspace", delayed):
                _, payload = self.http.response(await self.workspace_request(cookie), 401)
                self.assertNotIn("MUST NOT LEAK", json.dumps(payload))

    async def test_revocation_during_response_start_sends_no_private_body(self):
        cookie, csrf = await self.http.signed_in()
        messages = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            messages.append(message)
            if message["type"] == "http.response.start":
                self.http.sessions.logout(self.http.auth_headers(cookie, csrf))

        scope = {
            "type": "http",
            "scheme": "https",
            "method": "GET",
            "path": "/owner/workspace",
            "raw_path": b"/owner/workspace",
            "headers": self.http.auth_headers(cookie),
            "query_string": b"",
        }
        with patch.object(
            self.reader, "read_workspace", AsyncMock(return_value={"private": "MUST NOT LEAK"})
        ):
            await self.http.app(scope, receive, send)
        self.assertEqual(messages[-1]["body"], b"")

    async def test_timeout_oversize_and_malformed_storage_hide_details(self):
        await self.seed()
        cookie, _ = await self.http.signed_in()

        async def slow():
            await asyncio.sleep(0.05)
            return {"private": "PRIVATE PATH"}

        with (
            patch.object(self.reader, "read_workspace", slow),
            patch.object(authored_http.http, "WORKSPACE_TIMEOUT_SECONDS", 0.001),
        ):
            _, data = self.http.response(await self.workspace_request(cookie), 503)
            self.assertEqual(data, {"error": "owner_workspace_unavailable"})
        with patch.object(
            self.reader, "read_workspace", AsyncMock(return_value={"private": "X" * 32769})
        ):
            _, data = self.http.response(await self.workspace_request(cookie), 503)
            self.assertEqual(data, {"error": "owner_workspace_unavailable"})
        await self.writer.db.execute(
            "INSERT INTO sessions(id,json) VALUES ('broken','PRIVATE PATH not JSON')"
        )
        await self.writer.db.commit()
        _, data = self.http.response(await self.workspace_request(cookie), 503)
        self.assertEqual(data, {"error": "owner_workspace_unavailable"})

    async def test_mutations_query_and_body_rejected_before_read(self):
        cookie, _ = await self.http.signed_in()
        with patch.object(self.reader, "read_workspace", AsyncMock()) as reader:
            self.http.response(
                await self.http.request(
                    "/owner/workspace", "POST", headers=self.http.auth_headers(cookie)
                ),
                405,
            )
            self.http.response(
                await self.workspace_request(
                    cookie, scope_changes={"query_string": b"path=private"}
                ),
                400,
            )
            self.http.response(await self.workspace_request(cookie, body=b"x"), 413)
            reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
