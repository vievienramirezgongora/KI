"""Composition root: load once, extract once, share values with all methods."""

from dataclasses import asdict

from .configuration import Configuration
from .documents import DocumentStore
from .extractors import EXTRACTORS
from .methods import DETECTORS


class Pipeline:
    def __init__(self, config_path, *, input_path=None, extractor=None, documents=None,
                 detector_factories=None, extractor_factories=None):
        self.documents = documents if documents is not None else DocumentStore()
        self.config = Configuration.load(
            config_path, self.documents, input_path=input_path, extractor=extractor,
            detector_factories=DETECTORS if detector_factories is None else detector_factories,
            extractor_factories=EXTRACTORS if extractor_factories is None else extractor_factories,
        )

    def run(self):
        data = self.config.extractor.extract(self.documents, self.config.input_path)
        values = tuple(item.value for item in data.observations)
        results = {}
        for name, method in self.config.methods.items():
            detection = method.detect(values)
            if len(detection.flags) != len(values) or (
                detection.scores is not None and len(detection.scores) != len(values)
            ):
                raise ValueError(f"Detector {name}: result length does not match observations")
            results[name] = dict(
                details=detection.details,
                flags=detection.flags,
                scores=detection.scores,
                outliers=[asdict(item) for item, flagged in zip(data.observations, detection.flags) if flagged],
            )
        return dict(input=str(self.config.input_path), count=len(values),
                    observations=[asdict(item) for item in data.observations],
                    skipped_records=data.skipped_records, metadata=self.config.metadata, methods=results)
