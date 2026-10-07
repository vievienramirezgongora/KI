"""Independent plugins exercise extension points without patching core modules."""

import json
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path

from outlier_detection import Pipeline
from outlier_detection.contracts import Detection
from outlier_detection.extractors import EXTRACTORS, extract_records
from outlier_detection.methods import DETECTORS
from outlier_detection.validation import keys, positive


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class UpperLimit:
    limit: float

    @classmethod
    def from_config(cls, settings, zero_spread):
        keys(settings, ("limit",))
        positive(settings["limit"], "limit")
        return cls(settings["limit"])

    def detect(self, values):
        return Detection(tuple(x > self.limit for x in values), None, {"limit": self.limit})


@dataclass(frozen=True)
class LinesExtractor:
    comment_prefix: str

    @classmethod
    def from_config(cls, settings):
        keys(settings, ("comment_prefix",))
        prefix = settings["comment_prefix"]
        if not isinstance(prefix, str) or not prefix:
            raise ValueError("comment_prefix must be a nonempty string")
        return cls(prefix)

    def extract(self, documents, path):
        rows = ({"value": line} for line in documents.text(path).splitlines()
                if not line.startswith(self.comment_prefix))
        return extract_records(rows, "value", "error")


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write("pipeline.json", {
            "methods": "methods.json", "extractors": "extractors.json",
            "input": {"path": "data.txt", "extractor": "lines"},
        })
        self.write("methods.json", {
            "detectors": {"upper_limit": {"limit": 20}}, "zero_spread": "error",
        })
        self.write("extractors.json", {"lines": {"kind": "lines", "comment_prefix": "#"}})
        (self.root / "data.txt").write_text("# Measurements\n1\n2\n100\n", encoding="utf-8")

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding="utf-8")

    def pipeline(self, detectors=None, extractors=None):
        return Pipeline(
            self.root / "pipeline.json",
            detector_factories={"upper_limit": UpperLimit.from_config} if detectors is None else detectors,
            extractor_factories={"lines": LinesExtractor.from_config} if extractors is None else extractors,
        )

    def test_external_detector_and_format_work_without_core_changes(self):
        result = self.pipeline().run()
        self.assertEqual(result["count"], 3)
        self.assertEqual(set(result["methods"]), {"upper_limit"})
        self.assertEqual(result["methods"]["upper_limit"]["outliers"], [{"record": 3, "value": 100}])

    def test_external_plugins_coexist_with_builtins_without_global_mutation(self):
        methods = json.loads((ROOT / "config/methods.json").read_text())
        methods["detectors"]["upper_limit"] = {"limit": 20}
        self.write("methods.json", methods)
        result = self.pipeline(
            detectors={**DETECTORS, "upper_limit": UpperLimit.from_config},
            extractors={**EXTRACTORS, "lines": LinesExtractor.from_config},
        ).run()
        self.assertEqual(set(result["methods"]), set(DETECTORS) | {"upper_limit"})
        self.assertNotIn("upper_limit", DETECTORS)
        self.assertNotIn("lines", EXTRACTORS)

    def test_plugin_configuration_is_validated_by_plugin(self):
        self.write("methods.json", {"detectors": {"upper_limit": {"limit": -1}}, "zero_spread": "error"})
        with self.assertRaisesRegex(ValueError, "limit"):
            self.pipeline()
        self.write("methods.json", {"detectors": {"upper_limit": {"limit": 20}}, "zero_spread": "error"})
        self.write("extractors.json", {"lines": {"kind": "lines", "comment_prefix": ""}})
        with self.assertRaisesRegex(ValueError, "comment_prefix"):
            self.pipeline()

    def test_unknown_plugins_are_rejected_and_empty_registry_has_no_fallback(self):
        with self.assertRaisesRegex(ValueError, "Unknown detector"):
            self.pipeline(detectors={})
        with self.assertRaisesRegex(ValueError, "Unknown extractor kind"):
            self.pipeline(extractors={})

    def test_incorrect_plugin_result_length_is_not_silently_truncated(self):
        class BrokenDetector:
            def detect(self, values):
                return Detection((True,), None, {})

        pipeline = self.pipeline(detectors={"upper_limit": lambda settings, policy: BrokenDetector()})
        with self.assertRaisesRegex(ValueError, "result length"):
            pipeline.run()


if __name__ == "__main__":
    unittest.main()
