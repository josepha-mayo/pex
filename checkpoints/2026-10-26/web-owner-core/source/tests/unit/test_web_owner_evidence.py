"""Authored JSONL fixtures only; no live inference, provider calls or browser."""

import json
import os
import tempfile
import unittest
from pathlib import Path

from pex_bridge.web_owner_evidence import read_evidence


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "authored.jsonl"

    def write(self, events):
        self.path.write_text(
            "".join(
                json.dumps(
                    {
                        "ts": "2026-10-27T12:00:00+00:00",
                        "worker_model": "opencode/deepseek-v4.1-flash-free",
                        "supervisor_model": "nvidia/nemotron-3-super-120b-a12b",
                        **e,
                    }
                )
                + "\n"
                for e in events
            )
        )
        return read_evidence(self.path)

    def test_default_empty_missing(self):
        self.assertEqual(read_evidence(None), {"state": "not_configured"})
        self.assertEqual(read_evidence(self.path), {"state": "unavailable"})
        self.path.touch()
        self.assertEqual(read_evidence(self.path), {"state": "empty"})

    def test_narrow_projection_never_grades_or_raw_text(self):
        value = self.write(
            [
                {
                    "event": "arm_started",
                    "arm": "baseline",
                    "prompt": "PRIVATE",
                    "reasoning": "PRIVATE",
                },
                {
                    "event": "arm_terminal",
                    "arm": "baseline",
                    "terminal": "natural_stop",
                    "worker_calls": 1,
                    "grade": "PRIVATE",
                },
            ]
        )
        self.assertEqual(value["arms"]["baseline"], {"status": "natural_stop", "worker_calls": 1})
        self.assertFalse(value["paired_terminal"])
        self.assertNotIn("PRIVATE", json.dumps(value))

    def test_pair_requires_both_terminal_and_never_exposes_grade(self):
        self.assertEqual(
            self.write(
                [{"event": "paired_results_available", "arms": {"baseline": {"grade": "PRIVATE"}}}]
            ),
            {"state": "unavailable"},
        )
        value = self.write(
            [
                {
                    "event": "arm_terminal",
                    "arm": arm,
                    "terminal": "infrastructure_error",
                    "worker_calls": 0,
                }
                for arm in ("baseline", "pex")
            ]
            + [{"event": "paired_results_available", "arms": {"baseline": {"grade": "PRIVATE"}}}]
        )
        self.assertTrue(value["paired_terminal"])
        self.assertNotIn("PRIVATE", json.dumps(value))

    def test_untrusted_metadata_is_not_returned(self):
        for bad in (
            {"worker_model": "PRIVATE"},
            {"terminal": "PRIVATE", "event": "arm_terminal"},
            {"worker_calls": True},
            {"worker_calls": -1},
            {"worker_calls": 1001},
            {"arm": "PRIVATE"},
            {"ts": "PRIVATE"},
        ):
            self.assertEqual(
                self.write([{"event": "review_finished", "arm": "pex", **bad}]),
                {"state": "unavailable"},
            )

    def test_size_partial_symlink_fifo_and_invalid_paths(self):
        for raw in (b"{", b"x" * 262145, b"{}\n" * 513):
            self.path.write_bytes(raw)
            self.assertEqual(read_evidence(self.path), {"state": "unavailable"})
        self.path.unlink()
        self.path.symlink_to(Path(self.tmp.name) / "missing")
        self.assertEqual(read_evidence(self.path), {"state": "unavailable"})
        self.path.unlink()
        os.mkfifo(self.path)
        self.assertEqual(read_evidence(self.path), {"state": "unavailable"})
        with self.assertRaises(ValueError):
            read_evidence(Path("relative"))

    def test_timestamp_canonicalized_for_browser_parser(self):
        value = self.write(
            [{"event": "arm_started", "arm": "baseline", "ts": "20261027T120000+0000"}]
        )
        self.assertEqual(value["observed_at"], "2026-10-27T12:00:00+00:00")

    def test_utc_conversion_overflow_fails_closed(self):
        for stamp in ("0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"):
            with self.subTest(stamp=stamp):
                self.assertEqual(
                    self.write([{"event": "arm_started", "arm": "baseline", "ts": stamp}]),
                    {"state": "unavailable"},
                )

    def test_denied_execution_and_unknown_create_remain_independent_metadata(self):
        value = self.write(
            [
                {"event": "platform_denied", "arm": "baseline", "error": "PRIVATE"},
                {"event": "create_outcome_uncertain", "sandbox_id": "PRIVATE"},
                {"event": "cleanup_unconfirmed", "receipt": "PRIVATE"},
            ]
        )
        self.assertEqual(value["state"], "recorded")
        self.assertEqual(
            value["lifecycle"],
            {"execution": "platform_denied", "allocation": "uncertain", "cleanup": "unconfirmed"},
        )
        self.assertFalse(value["paired_terminal"])
        for arm in value["arms"].values():
            self.assertEqual(arm, {"status": "not_started", "worker_calls": None})
        self.assertNotIn("PRIVATE", json.dumps(value))

    def test_lifecycle_does_not_invent_a_denial_or_allocation_from_cleanup(self):
        value = self.write([{"event": "create_outcome_uncertain"}])
        self.assertEqual(
            value["lifecycle"],
            {"execution": "not_reported", "allocation": "uncertain", "cleanup": "not_reported"},
        )
        value = self.write([{"event": "platform_denied"}])
        self.assertEqual(
            value["lifecycle"],
            {
                "execution": "platform_denied",
                "allocation": "not_reported",
                "cleanup": "not_reported",
            },
        )
        self.assertNotIn("lifecycle", self.write([{"event": "cleanup_unconfirmed"}]))

    def test_denial_cannot_be_followed_by_resumed_work_or_success(self):
        for before in ("platform_denied", "create_outcome_uncertain"):
            for after in (
                {"event": "arm_started", "arm": "baseline"},
                {"event": "worker_natural_stop", "arm": "baseline"},
                {"event": "arm_terminal", "arm": "baseline", "terminal": "natural_stop"},
                {"event": "paired_terminal"},
            ):
                with self.subTest(before=before, after=after):
                    self.assertEqual(
                        self.write([{"event": before}, after]), {"state": "unavailable"}
                    )

    def test_authored_browser_fixture_matches_the_real_projection_contract(self):
        fixtures = Path(__file__).resolve().parents[2] / "apps/desktop/tests/fixtures"
        expected = json.loads((fixtures / "ownerDeniedCreate.authored.json").read_text())
        self.assertEqual(
            read_evidence(fixtures / "ownerDeniedCreate.authored.events.jsonl"),
            expected["run_evidence"],
        )
