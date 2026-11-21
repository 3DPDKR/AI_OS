"""Regression tests: GitHub file layout must support documented CLI imports."""
from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_FILE = PROJECT_ROOT / "nexion" / "evidence_triage.py"


class PackageLayoutTests(unittest.TestCase):
    def test_01_review_module_resolves_inside_python_package(self):
        spec = importlib.util.find_spec("nexion.evidence_triage")
        self.assertIsNotNone(spec)
        self.assertEqual(Path(spec.origin).resolve(), PACKAGE_FILE.resolve())

    def test_02_read_only_triage_api_remains_importable(self):
        module = importlib.import_module("nexion.evidence_triage")
        self.assertTrue(callable(module.triage_anchor_mismatch))
        self.assertEqual(module.FORMAT, "nexion-external-review-witness-v1")

    def test_03_no_misplaced_shadow_copy_at_project_root(self):
        self.assertTrue(PACKAGE_FILE.is_file())
        self.assertFalse((PROJECT_ROOT / "evidence_triage.py").exists())

    def test_04_documented_targeted_cli_discovers_eighteen_tests(self):
        process = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests",
             "-p", "test_evidence_triage.py", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertIn("Ran 18 tests", process.stderr)


if __name__ == "__main__":
    unittest.main()
