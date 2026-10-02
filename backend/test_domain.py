import tempfile
import unittest
from pathlib import Path

import domain


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = domain.DB
        domain.DB = Path(self.temp.name) / "test.sqlite3"

    def tearDown(self):
        domain.DB = self.old
        self.temp.cleanup()

    def test_quarantine_and_replay(self):
        lines = '{"id":"a","text":"ok","label":"positive"}\n{"id":"a","text":"again","label":"neutral"}\nbroken'
        report = domain.ingest(lines)
        self.assertEqual((report["accepted"], report["rejected"]), (1, 2))
        self.assertTrue(domain.ingest(lines)["replayed"])
        self.assertEqual(domain.snapshot()["total"], 1)

    def test_distribution_shift(self):
        domain.ingest('{"id":"a","text":"ok","label":"positive"}')
        report = domain.ingest('{"id":"b","text":"bad","label":"negative"}')
        self.assertEqual(report["drift"], 1)
        self.assertTrue(report["warning"])

    def test_empty_and_invalid(self):
        with self.assertRaises(ValueError):
            domain.ingest("")
        report = domain.ingest('[]\n{"id":3}')
        self.assertEqual(report["rejected"], 2)
        self.assertIsNone(report["drift"])

    def test_nonscalar_label_is_quarantined(self):
        report = domain.ingest('{"id":"x","text":"hello","label":[]}')
        self.assertEqual(report["rejected"], 1)
        self.assertEqual(report["quarantine"][0]["reason"], "unknown label")

    def test_divergence_identity(self):
        self.assertAlmostEqual(
            domain.js_divergence({"a": 2, "b": 2}, {"a": 1, "b": 1}), 0
        )
