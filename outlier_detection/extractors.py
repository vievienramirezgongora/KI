"""Built-in formats and shared conversion of records to numeric observations."""

import csv
import io
import math
from dataclasses import dataclass
from types import MappingProxyType

from .contracts import Extraction, Observation
from .validation import keys


def validate_record_settings(settings):
    if not isinstance(settings["field"], str) or not settings["field"]:
        raise ValueError("Extractor field must be a nonempty string")
    if settings["missing"] not in ("error", "skip"):
        raise ValueError("missing must be error or skip")


def extract_records(rows, field, missing) -> Extraction:
    observations, skipped = [], []
    for record, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Record {record} must be an object")
        raw = row.get(field)
        if raw is None or isinstance(raw, str) and not raw.strip():
            if missing == "skip":
                skipped.append(record)
                continue
            raise ValueError(f"Record {record}: missing field {field}")
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ValueError(f"Record {record}: expected a numeric value")
        try:
            value = float(raw)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"Record {record}: invalid numeric value") from exc
        if not math.isfinite(value):
            raise ValueError(f"Record {record}: value must be finite")
        observations.append(Observation(record, value))
    if not observations:
        raise ValueError("No numeric observations available")
    return Extraction(tuple(observations), tuple(skipped))


@dataclass(frozen=True)
class CsvExtractor:
    field: str
    missing: str
    delimiter: str

    @classmethod
    def from_config(cls, settings):
        keys(settings, ("field", "missing", "delimiter"))
        validate_record_settings(settings)
        delimiter = settings["delimiter"]
        if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n"':
            raise ValueError("CSV delimiter must be one character other than newline or quote")
        return cls(settings["field"], settings["missing"], delimiter)

    def rows(self, text):
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=self.delimiter)
        names = reader.fieldnames
        if not names or self.field not in names or len(names) != len(set(names)):
            raise ValueError("CSV needs unique headers including the configured field")
        for record, row in enumerate(reader, start=1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"CSV record {record} has the wrong number of columns")
            yield row

    def extract(self, documents, path):
        return extract_records(self.rows(documents.text(path)), self.field, self.missing)


@dataclass(frozen=True)
class JsonExtractor:
    field: str
    missing: str
    items_path: tuple[str, ...]

    @classmethod
    def from_config(cls, settings):
        keys(settings, ("field", "missing", "items_path"))
        validate_record_settings(settings)
        path = settings["items_path"]
        if not isinstance(path, list) or any(not isinstance(p, str) or not p for p in path):
            raise ValueError("JSON items_path must be an array of nonempty object keys")
        return cls(settings["field"], settings["missing"], tuple(path))

    def extract(self, documents, path):
        rows = documents.json(path)
        for key in self.items_path:
            if not isinstance(rows, dict) or key not in rows:
                raise ValueError(f"Missing JSON items_path key: {key}")
            rows = rows[key]
        if not isinstance(rows, list):
            raise ValueError("JSON items_path must select an array of records")
        return extract_records(rows, self.field, self.missing)


EXTRACTORS = MappingProxyType({"csv": CsvExtractor.from_config, "json": JsonExtractor.from_config})
