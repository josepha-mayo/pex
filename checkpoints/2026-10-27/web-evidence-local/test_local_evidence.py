import json
import tempfile
import unittest
from pathlib import Path

import httpx

from serve_owner_evidence import LocalEvidenceApp, read_secret

SECRET = "a" * 43


class EvidenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "events.jsonl"
        self.write_event(1)
        self.app = LocalEvidenceApp(
            origin="https://127.0.0.1:7443", secret=SECRET, events=self.path
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="https://127.0.0.1:7443",
        )

    def write_event(self, calls):
        self.path.write_text(
            json.dumps(
                {
                    "event": "arm_terminal",
                    "arm": "baseline",
                    "terminal": "natural_stop",
                    "worker_calls": calls,
                    "worker_model": "nebius/deepseek-ai/DeepSeek-V4.1-Flash-1017",
                    "supervisor_model": "nvidia/nemotron-3-super-120b-a12b",
                    "ts": "2026-10-27T12:00:00+00:00",
                    "hidden_tests": "NEVER_EXPOSE",
                    "prompt": "NEVER_EXPOSE",
                    "api_key": "NEVER_EXPOSE",
                }
            )
            + "\n"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.tmp.cleanup()

    async def login(self):
        result = await self.client.post(
            "/owner/auth/login",
            headers={"Origin": "https://127.0.0.1:7443"},
            json={"owner_secret": SECRET},
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn("Secure", result.headers["set-cookie"])
        return result.json()["csrf_token"]

    async def test_actual_file_refresh_and_no_private_fields(self):
        self.assertEqual((await self.client.get("/owner/workspace")).status_code, 401)
        await self.login()
        first = await self.client.get("/owner/workspace")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["sessions"], [])
        self.assertEqual(first.json()["run_evidence"]["arms"]["baseline"]["worker_calls"], 1)
        self.assertNotIn("NEVER_EXPOSE", first.text)
        self.write_event(2)
        second = await self.client.get("/owner/workspace")
        self.assertEqual(second.json()["run_evidence"]["arms"]["baseline"]["worker_calls"], 2)
        self.path.write_text("{")
        self.assertEqual(
            (await self.client.get("/owner/workspace")).json()["run_evidence"],
            {"state": "unavailable"},
        )

    async def test_timestamp_overflow_keeps_authenticated_workspace_available(self):
        await self.login()
        for stamp in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            with self.subTest(stamp=stamp):
                self.write_event(1)
                event = json.loads(self.path.read_text())
                event["ts"] = stamp
                self.path.write_text(json.dumps(event) + "\n")
                response = await self.client.get("/owner/workspace")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["run_evidence"], {"state": "unavailable"})
                self.assertNotIn("NEVER_EXPOSE", response.text)
        self.write_event(2)
        recovered = await self.client.get("/owner/workspace")
        self.assertEqual(recovered.json()["run_evidence"]["arms"]["baseline"]["worker_calls"], 2)

    async def test_boundaries_logout_and_static(self):
        page = await self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("No bridge workspace attached", page.text)
        for path in [
            "/report.json",
            "/events.jsonl",
            "/v1/sessions",
            "/owner.html?x=1",
            "/../AGENTS.md",
        ]:
            self.assertEqual((await self.client.get(path)).status_code, 404)
        self.assertEqual(
            (await self.client.get("/", headers={"Host": "evil.test"})).status_code, 403
        )
        self.assertEqual(
            (
                await self.client.get(
                    "http://127.0.0.1:7443/", headers={"X-Forwarded-Proto": "https"}
                )
            ).status_code,
            403,
        )
        self.assertEqual(
            (
                await self.client.post(
                    "/owner/auth/login",
                    headers={"Origin": "https://evil.test"},
                    json={"owner_secret": SECRET},
                )
            ).status_code,
            403,
        )
        csrf = await self.login()
        self.assertEqual(
            (
                await self.client.post(
                    "/owner/auth/logout",
                    headers={
                        "Origin": "https://127.0.0.1:7443",
                        "X-PEX-Owner-CSRF": csrf,
                    },
                )
            ).status_code,
            200,
        )
        self.assertEqual((await self.client.get("/owner/workspace")).status_code, 401)

    async def test_event_symlink_and_private_secret(self):
        await self.login()
        target = self.path.with_name("other.jsonl")
        self.path.rename(target)
        self.path.symlink_to(target)
        self.assertEqual(
            (await self.client.get("/owner/workspace")).json()["run_evidence"],
            {"state": "unavailable"},
        )
        secret_file = self.path.with_name("owner.secret")
        secret_file.write_text(SECRET)
        secret_file.chmod(0o600)
        self.assertEqual(read_secret(secret_file), SECRET)
        secret_file.chmod(0o644)
        with self.assertRaises(ValueError):
            read_secret(secret_file)


if __name__ == "__main__":
    unittest.main()
