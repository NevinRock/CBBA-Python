"""Portable evidence and generated-report regression checks; no auctions run."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from test.homogeneous_artifacts import evidence_directory, pack_evidence, unpack_evidence
from test import analyze_homogeneous_results as analysis

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "doc/homogeneous"


class HomogeneousDeliveryTest(unittest.TestCase):
    def test_evidence_packing_is_deterministic(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "raw"
            source.mkdir()
            (source / "trials.csv").write_bytes(b"seed\n0\n")
            h = hashlib.sha256((source / "trials.csv").read_bytes()).hexdigest()
            (source / "raw_files_sha256.json").write_text(json.dumps({"trials.csv": h}))
            (source / "preflight.json").write_text(json.dumps({"source_sha256": {}}))
            pack_evidence(source, root / "one.gz")
            pack_evidence(source, root / "two.gz")
            self.assertEqual((root / "one.gz").read_bytes(), (root / "two.gz").read_bytes())
            with self.assertRaises(FileExistsError):
                pack_evidence(source, root / "one.gz")

    def test_unsafe_evidence_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / "unsafe.gz"
            record = {"path": "../outside", "sha256": hashlib.sha256(b"x").hexdigest(),
                      "bytes_base64": base64.b64encode(b"x").decode()}
            with gzip.open(bundle, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")
            with self.assertRaises(ValueError):
                unpack_evidence(bundle, Path(folder) / "expanded")

    def test_corrupt_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / "bad.gz"
            record = {"path": "file", "sha256": "0" * 64,
                      "bytes_base64": base64.b64encode(b"x").decode()}
            with gzip.open(bundle, "wt", encoding="utf-8") as stream:
                stream.write(json.dumps(record) + "\n")
            with self.assertRaises(ValueError):
                unpack_evidence(bundle, Path(folder) / "expanded")

    def test_published_evidence_is_complete_and_csv_matches(self):
        with evidence_directory(RESULTS) as raw:
            self.assertEqual(len(list((raw / "paired_inputs").glob("*.json"))), 90)
            self.assertEqual(len(list((raw / "diagnostics").glob("*.json"))), 270)
            self.assertEqual((raw / "trials.csv").read_text(encoding="utf-8"),
                             (RESULTS / "trials.csv").read_text(encoding="utf-8"))
            hashes = json.loads((raw / "raw_files_sha256.json").read_text())
            for name, expected in hashes.items():
                self.assertEqual(hashlib.sha256((raw / name).read_bytes()).hexdigest(), expected)

    def test_report_regeneration_fixes_wording_and_preserves_provenance(self):
        with evidence_directory(RESULTS) as raw, tempfile.TemporaryDirectory() as folder:
            details = [analysis.read_json(path) for path in sorted((raw / "diagnostics").glob("*.json"))]
            rows, summary, comparisons, _ = analysis.build_statistics(details)
            fallbacks, failures = analysis.fallback_statistics(rows, details)
            audit = analysis.read_json(RESULTS / "independent_audit.json")
            metadata = {"run_base_commit": analysis.read_json(raw / "preflight.json")["git_commit"]}
            analysis.write_report(Path(folder), rows, summary, comparisons, fallbacks, failures, audit, metadata)
            report = (Path(folder) / "final_report.md").read_text(encoding="utf-8")
            self.assertIn("Savings from successful local recoveries total 44, 345, and 1,753 broadcasts for 6, 12, and 24 robots, respectively.", report)
            self.assertNotIn("44,345,1753", report)
            self.assertNotIn("Per the user's latest instruction", report)
            self.assertNotIn("stage-two report are the parameter authority", report)
            self.assertIn("Experiment files were uncommitted at execution time", report)
            self.assertIn(metadata["run_base_commit"], report)
            self.assertIn("SHA-256", report)


if __name__ == "__main__":
    unittest.main()
