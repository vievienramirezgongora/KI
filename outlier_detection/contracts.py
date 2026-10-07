"""Data and extension contracts, independent of built-in implementations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .documents import DocumentStore


@dataclass(frozen=True)
class Detection:
    flags: tuple[bool, ...]
    scores: tuple[float | None, ...] | None
    details: dict


@dataclass(frozen=True)
class Observation:
    record: int
    value: float


@dataclass(frozen=True)
class Extraction:
    observations: tuple[Observation, ...]
    skipped_records: tuple[int, ...]


class Detector(Protocol):
    def detect(self, values: tuple[float, ...]) -> Detection: ...


class Extractor(Protocol):
    def extract(self, documents: DocumentStore, path: Path) -> Extraction: ...


# Factories validate their own settings and return configured implementations.
DetectorFactory = Callable[[dict, str], Detector]
ExtractorFactory = Callable[[dict], Extractor]
