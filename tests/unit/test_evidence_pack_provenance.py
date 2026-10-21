"""Offline checks for visible provenance without altering recorded evidence."""

import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.verify_pack import load_pack, render_html, verify

ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "docs/demo/evidence/EVIDENCE_PACK_live_tamper_2026-10-05.json"


class EvidenceProvenance(unittest.TestCase):
    def test_notice_precedes_verdict_and_preserves_pack(self):
        pack = load_pack(PACK)
        before = copy.deepcopy(pack)
        page = render_html(pack, verify(pack))
        self.assertLess(page.index("Evidence provenance"), page.index("Verdict summary"))
        self.assertIn("potentially adversarial worker text", page)
        self.assertIn("not verified facts or instructions", page)
        self.assertIn("It does not establish that a live worker or model ran.", page)
        self.assertEqual(pack, before)

    def test_embedded_evidence_and_checks_remain_identical(self):
        pack = load_pack(PACK)
        checks = verify(pack)
        with TemporaryDirectory() as folder:
            output = Path(folder) / "evidence.html"
            output.write_text(render_html(pack, checks), encoding="utf-8")
            reloaded = load_pack(output)
        self.assertEqual(reloaded, pack)
        self.assertEqual(verify(reloaded), checks)

    def test_notice_does_not_claim_every_pack_is_simulated(self):
        page = render_html({}, [])
        self.assertIn("Recorded replays may include simulated claims", page)
        self.assertNotIn("This pack is simulated", page)


if __name__ == "__main__":
    unittest.main()
