"""Resolve configuration references and delegate plugin-specific validation."""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from .contracts import Detector, DetectorFactory, Extractor, ExtractorFactory
from .documents import DocumentStore
from .validation import keys


def configure_detectors(data, factories: Mapping[str, DetectorFactory]):
    keys(data, ("detectors", "zero_spread"))
    if data["zero_spread"] not in ("flag_deviations", "error"):
        raise ValueError("zero_spread must be flag_deviations or error")
    definitions = data["detectors"]
    if not isinstance(definitions, dict) or not definitions:
        raise ValueError("Expected at least one detector configuration")
    configured = {}
    for name, settings in definitions.items():
        if name not in factories:
            raise ValueError(f"Unknown detector: {name}")
        if not isinstance(settings, dict):
            raise ValueError(f"Detector {name}: expected configuration object")
        configured[name] = factories[name](settings, data["zero_spread"])
    return MappingProxyType(configured)


def configure_extractors(definitions, factories: Mapping[str, ExtractorFactory]):
    if not isinstance(definitions, dict) or not definitions:
        raise ValueError("Expected named extractor definitions")
    configured = {}
    for name, settings in definitions.items():
        if not isinstance(settings, dict) or not isinstance(settings.get("kind"), str):
            raise ValueError(f"Extractor {name}: expected a kind string")
        kind = settings["kind"]
        if kind not in factories:
            raise ValueError(f"Unknown extractor kind: {kind}")
        # 'kind' belongs to dispatch; remaining settings belong to the plugin.
        configured[name] = factories[kind]({k: v for k, v in settings.items() if k != "kind"})
    return MappingProxyType(configured)


@dataclass(frozen=True)
class Configuration:
    methods: Mapping[str, Detector]
    extractor: Extractor
    input_path: Path
    metadata: object

    @classmethod
    def load(cls, path, documents: DocumentStore, *, detector_factories, extractor_factories,
             input_path=None, extractor=None):
        path = documents.resolve(path)
        data = documents.json(path)
        keys(data, ("methods", "extractors", "input"), ("metadata",))
        keys(data["input"], ("path", "extractor"))
        methods_path = documents.resolve(data["methods"], path.parent)
        extractors_path = documents.resolve(data["extractors"], path.parent)
        methods = configure_detectors(documents.json(methods_path), detector_factories)
        parsed = configure_extractors(documents.json(extractors_path), extractor_factories)
        name = extractor if extractor is not None else data["input"]["extractor"]
        if not isinstance(name, str) or name not in parsed:
            raise ValueError(f"Unknown extractor: {name}")
        source = (documents.resolve(input_path) if input_path is not None
                  else documents.resolve(data["input"]["path"], path.parent))
        metadata = (documents.json(documents.resolve(data["metadata"], path.parent))
                    if "metadata" in data else None)
        return cls(methods, parsed[name], source, metadata)
