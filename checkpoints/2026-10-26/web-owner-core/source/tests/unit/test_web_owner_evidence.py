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
        self.path.write_text("".join(json.dumps({"ts": "2026-10-27T12:00:00+00:00", "worker_model": "opencode/deepseek-v4.1-flash-free", "supervisor_model": "nvidia/nemotron-3-super-120b-a12b", **e}) + "\n" for e in events))
        return read_evidence(self.path)

    def test_default_empty_missing(self):
        self.assertEqual(read_evidence(None), {"state": "not_configured"})
        self.assertEqual(read_evidence(self.path), {"state": "unavailable"})
        self.path.touch()
        self.assertEqual(read_evidence(self.path), {"state": "empty"})

    def test_narrow_projection_never_grades_or_raw_text(self):
        value = self.write([{"event": "arm_started", "arm": "baseline", "prompt": "PRIVATE", "reasoning": "PRIVATE"}, {"event": "arm_terminal", "arm": "baseline", "terminal": "natural_stop", "worker_calls": 1, "grade": "PRIVATE"}])
        self.assertEqual(value["arms"]["baseline"], {"status": "natural_stop", "worker_calls": 1})
        self.assertFalse(value["paired_terminal"])
        self.assertNotIn("PRIVATE", json.dumps(value))

    def test_pair_requires_both_terminal_and_never_exposes_grade(self):
        self.assertEqual(self.write([{"event": "paired_results_available", "arms": {"baseline": {"grade": "PRIVATE"}}}]), {"state": "unavailable"})
        value = self.write([{"event": "arm_terminal", "arm": arm, "terminal": "infrastructure_error", "worker_calls": 0} for arm in ("baseline", "pex")] + [{"event": "paired_results_available", "arms": {"baseline": {"grade": "PRIVATE"}}}])
        self.assertTrue(value["paired_terminal"])
        self.assertNotIn("PRIVATE", json.dumps(value))

    def test_untrusted_metadata_is_not_returned(self):
        for bad in ({"worker_model": "PRIVATE"}, {"terminal": "PRIVATE", "event": "arm_terminal"}, {"worker_calls": True}, {"worker_calls": -1}, {"worker_calls": 1001}, {"arm": "PRIVATE"}, {"ts": "PRIVATE"}):
            self.assertEqual(self.write([{"event": "review_finished", "arm": "pex", **bad}]), {"state": "unavailable"})

    def test_size_partial_symlink_fifo_and_invalid_paths(self):
        for raw in (b'{', b'x' * 262145, b'{}\n' * 513):
            self.path.write_bytes(raw)
            self.assertEqual(read_evidence(self.path), {"state": "unavailable"})
        self.path.unlink()
        self.path.symlink_to(Path(self.tmp.name)/"missing")
        self.assertEqual(read_evidence(self.path), {"state": "unavailable"})
        self.path.unlink(); os.mkfifo(self.path)
        self.assertEqual(read_evidence(self.path), {"state": "unavailable"})
        with self.assertRaises(ValueError): read_evidence(Path("relative"))
