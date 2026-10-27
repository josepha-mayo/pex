"""Trusted authored data fixtures only; no candidate module import/execution."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import task_adapter as a


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.package = self.root / "package"
        files = {}
        for name in a.FILES:
            relative = f"public/{a.TASK}/{name}"
            data = f"AUTHORED INERT FIXTURE {name}\n".encode()
            a.exclusive(self.package / relative, data)
            files[relative] = a.digest(data)
        for relative in (*a.PROTECTED, "INITIAL_PROMPT.txt"):
            data = (
                b"PRIVATE INERT FIXTURE"
                if relative.startswith("evaluator/")
                else b"Read TASK.md."
            )
            a.exclusive(self.package / relative, data)
            files[relative] = a.digest(data)
        raw = a.encoded({"files": files})
        a.exclusive(self.package / "MANIFEST.json", raw)
        pin = patch.object(a, "MANIFEST_SHA256", a.digest(raw))
        pin.start()
        self.addCleanup(pin.stop)
        self.out = self.root / "staged"

    def test_public_only_matched_staging(self):
        receipt, prompt = a.stage(self.package, self.out)
        from dataclasses import make_dataclass

        Arm = make_dataclass(
            "Arm", ["condition", "workspace", "public_sha256", "prompt", "worker"]
        )
        worker = object()
        arms = a.make_arms(self.out, receipt, prompt, worker, Arm)
        self.assertIs(arms[0].worker, arms[1].worker)
        self.assertEqual(arms[0].prompt, arms[1].prompt)
        self.assertEqual(arms[0].public_sha256, arms[1].public_sha256)
        for arm in arms:
            actual = sorted(
                str(p.relative_to(arm.workspace))
                for p in arm.workspace.rglob("*")
                if p.is_file()
            )
            self.assertEqual(actual, sorted(a.FILES))
            self.assertNotIn(
                b"PRIVATE",
                b"".join(
                    p.read_bytes() for p in arm.workspace.rglob("*") if p.is_file()
                ),
            )
        private = json.loads(
            (self.out / "controller/evaluator-inputs.json").read_text()
        )
        self.assertFalse(private["candidate_execution_permitted"])
        self.assertFalse(receipt["execution_boundary_verified"])

    def test_changed_public_refused_before_creation(self):
        (self.package / f"public/{a.TASK}/reliable.py").write_text("changed")
        with self.assertRaises(ValueError):
            a.stage(self.package, self.out)
        self.assertFalse(self.out.exists())

    def test_changed_protected_refused(self):
        (self.package / a.PROTECTED[0]).write_text("changed")
        with self.assertRaises(ValueError):
            a.stage(self.package, self.out)

    def test_symlink_refused(self):
        p = self.package / f"public/{a.TASK}/reliable.py"
        saved = p.read_bytes()
        p.unlink()
        (self.root / "outside").write_bytes(saved)
        p.symlink_to(self.root / "outside")
        with self.assertRaises(ValueError):
            a.stage(self.package, self.out)

    def test_existing_destination_refused(self):
        self.out.mkdir()
        with self.assertRaises(FileExistsError):
            a.stage(self.package, self.out)

    def test_manifest_changed_refused(self):
        (self.package / "MANIFEST.json").write_text("{}")
        with self.assertRaises(ValueError):
            a.stage(self.package, self.out)

    def test_changed_staging_refused(self):
        receipt, prompt = a.stage(self.package, self.out)
        (self.out / "workers/baseline/reliable.py").write_text("changed")
        with self.assertRaises(ValueError):
            a.make_arms(self.out, receipt, prompt, object(), lambda *x: x)

    def test_hardlink_refused(self):
        import os

        os.link(self.package / f"public/{a.TASK}/reliable.py", self.root / "linked")
        with self.assertRaises(ValueError):
            a.stage(self.package, self.out)


if __name__ == "__main__":
    unittest.main()
