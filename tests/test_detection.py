import json
import math
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from outlier_detection import Pipeline
from outlier_detection.configuration import configure_detectors
from outlier_detection.documents import DocumentStore
from outlier_detection.extractors import CsvExtractor, JsonExtractor
from outlier_detection.methods import DETECTORS


ROOT = Path(__file__).resolve().parents[1]


class DetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detectors = configure_detectors(DocumentStore().json(ROOT / "config/methods.json"), DETECTORS)

    def test_tukey_known_quartiles_and_strict_boundary(self):
        result = self.detectors["tukey"].detect((0, 1, 2, 3, 6))
        self.assertEqual(result.details["q1"], 1)
        self.assertEqual(result.details["q3"], 3)
        self.assertEqual(result.details["upper"], 6)
        self.assertFalse(any(result.flags))
        self.assertTrue(self.detectors["tukey"].detect((0, 1, 2, 3, 6.01)).flags[-1])

    def test_zscore_known_population_and_sample_scores(self):
        result = self.detectors["zscore"].detect((1, 2, 3))
        self.assertEqual(result.details["mean"], 2)
        self.assertAlmostEqual(result.scores[-1], math.sqrt(1.5))
        sample = replace(self.detectors["zscore"], ddof=1, threshold=1).detect((1, 2, 3))
        self.assertEqual(sample.scores, (-1, 0, 1))
        self.assertFalse(any(sample.flags))

    def test_modified_zscore_uses_median_and_raw_mad(self):
        result = self.detectors["modified_zscore"].detect((1, 2, 3, 4, 100))
        self.assertEqual(result.details["median"], 3)
        self.assertEqual(result.details["mad"], 1)
        self.assertAlmostEqual(result.scores[-1], self.detectors["modified_zscore"].scale * 97)
        self.assertEqual(result.flags, (False, False, False, False, True))

    def test_both_tails_are_detected(self):
        values = (-100,) + (9, 10, 11) * 10 + (100,)
        for method in self.detectors.values():
            with self.subTest(method=type(method).__name__):
                flags = method.detect(values).flags
                self.assertEqual([i for i, flag in enumerate(flags) if flag], [0, 31])

    def test_zero_mad_explicit_policy_and_constant_series(self):
        result = self.detectors["modified_zscore"].detect((1, 1, 1, 1, 100))
        self.assertEqual(result.flags, (False, False, False, False, True))
        self.assertEqual(result.scores, (None,) * 5)
        for method in (self.detectors["zscore"], self.detectors["modified_zscore"]):
            self.assertFalse(any(method.detect((7, 7, 7)).flags))
            with self.assertRaisesRegex(ValueError, "Zero spread"):
                replace(method, zero_spread="error").detect((7, 7, 7))

    def test_single_value_and_sample_requirement(self):
        for method in self.detectors.values():
            self.assertEqual(method.detect((4,)).flags, (False,))
        with self.assertRaisesRegex(ValueError, "ddof"):
            replace(self.detectors["zscore"], ddof=1).detect((4,))

    def test_detectors_do_not_open_files(self):
        with patch("builtins.open", side_effect=AssertionError("Detector performed I/O")), \
             patch("pathlib.Path.open", side_effect=AssertionError("Detector performed I/O")):
            for method in self.detectors.values():
                method.detect((1, 2, 3, 100))


class PipelineTests(unittest.TestCase):
    def test_csv_and_json_produce_identical_detections(self):
        csv = Pipeline(ROOT / "config/pipeline.json").run()
        json_result = Pipeline(ROOT / "config/pipeline.json", input_path=ROOT / "examples/measurements.json",
                               extractor="json_measurements").run()
        self.assertEqual(csv["count"], 13)
        self.assertEqual(csv["methods"], json_result["methods"])
        self.assertEqual(csv["observations"], json_result["observations"])
        for result in csv["methods"].values():
            self.assertEqual(result["outliers"], [{"record": 13, "value": 100.0}])

    def test_all_documents_read_once_across_repeated_runs(self):
        reads = []
        original = Path.read_text

        def counted(path, *args, **kwargs):
            reads.append(path.resolve())
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", counted):
            pipeline = Pipeline(ROOT / "config/pipeline.json")
            pipeline.run()
            pipeline.run()
            pipeline.documents.json(ROOT / "examples/../examples/info.json")
        expected = [ROOT / "config" / name for name in ("pipeline.json", "methods.json", "extractors.json")]
        expected += [ROOT / "examples" / name for name in ("info.json", "measurements.csv")]
        self.assertCountEqual(reads, expected)

    def test_metadata_alias_reuses_already_loaded_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline.json"
            data = json.loads((ROOT / "config/pipeline.json").read_text())
            data.update(methods=str(ROOT / "config/methods.json"),
                        extractors=str(ROOT / "config/extractors.json"),
                        metadata=str(ROOT / "config/methods.json"))
            data["input"]["path"] = str(ROOT / "examples/measurements.csv")
            path.write_text(json.dumps(data))
            original = Path.read_text
            reads = []

            def counted(path, *args, **kwargs):
                reads.append(path.resolve())
                return original(path, *args, **kwargs)

            with patch.object(Path, "read_text", counted):
                Pipeline(path).run()
            self.assertEqual(reads.count(ROOT / "config/methods.json"), 1)

    def test_cached_json_is_not_mutated_by_consumers(self):
        store = DocumentStore()
        first = store.json(ROOT / "config/methods.json")
        first["detectors"]["tukey"]["factor"] = 99
        second = store.json(ROOT / "config/methods.json")
        self.assertNotEqual(first, second)

    def test_cli_works_from_another_directory(self):
        result = subprocess.run([sys.executable, "-m", "outlier_detection", "--config", "config/pipeline.json"],
                                cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["count"], 13)
        # Library paths inside configuration are independent of the caller's cwd.
        result = subprocess.run([sys.executable, "-c",
                                 "import sys; sys.path.insert(0, sys.argv[1]); "
                                 "from outlier_detection import Pipeline; "
                                 "assert Pipeline(sys.argv[2]).run()['count'] == 13",
                                 str(ROOT), str(ROOT / "config/pipeline.json")],
                                cwd="/tmp", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


class ValidationTests(unittest.TestCase):
    def extract_csv(self, text, missing="error"):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            path.write_text(text, encoding="utf-8")
            config = CsvExtractor.from_config(dict(field="value", missing=missing, delimiter=","))
            return config.extract(DocumentStore(), path)

    def test_missing_policy_preserves_source_records(self):
        result = self.extract_csv("value,label\n1,a\n,b\n100,c\n", missing="skip")
        self.assertEqual(result.skipped_records, (2,))
        self.assertEqual([x.record for x in result.observations], [1, 3])
        with self.assertRaisesRegex(ValueError, "missing"):
            self.extract_csv("value,label\n,a\n")

    def test_empty_nonfinite_and_malformed_csv_fail(self):
        for text in ("value\n", "value\nNaN\n", "value\ninf\n", "value\nabc\n",
                     "wrong\n1\n", "value,value\n1,2\n", "value\n1,2\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.extract_csv(text)

    def test_json_booleans_and_invalid_structure_fail(self):
        config = JsonExtractor.from_config(dict(field="value", missing="error", items_path=[]))
        for data in ([{"value": True}], [1], {"value": 1}, [{"value": {}}]):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "data.json"
                path.write_text(json.dumps(data))
                with self.subTest(data=data), self.assertRaises(ValueError):
                    config.extract(DocumentStore(), path)

    def test_config_has_no_silent_defaults(self):
        raw = DocumentStore().json(ROOT / "config/methods.json")
        for data in ({}, dict(raw, unknown=True), dict(raw, detectors={"zscore": {"threshold": 3, "ddof": True}}),
                     dict(raw, detectors={"tukey": {"factor": -1}})):
            with self.subTest(data=data), self.assertRaises(ValueError):
                configure_detectors(data, DETECTORS)

    def test_duplicate_json_keys_and_nan_fail(self):
        for text in ('{"value": 1, "value": 2}', '{"value": NaN}'):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "info.json"
                path.write_text(text)
                with self.assertRaises(ValueError):
                    DocumentStore().json(path)


if __name__ == "__main__":
    unittest.main()
