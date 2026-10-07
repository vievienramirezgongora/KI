"""One filesystem reader, shared by configuration, metadata and extractors."""

import json
from copy import deepcopy
from pathlib import Path


class DocumentStore:
    """A lazy snapshot: each canonical path is read at most once per instance.

    Create a new store (or Pipeline) to observe changes on disk. JSON consumers
    receive copies so they cannot modify another consumer's configuration.
    """

    def __init__(self):
        self._texts: dict[Path, str] = {}
        self._json: dict[Path, object] = {}

    @staticmethod
    def resolve(path, relative_to=None) -> Path:
        path = Path(path)
        if relative_to is not None and not path.is_absolute():
            path = Path(relative_to) / path
        return path.resolve(strict=True)

    def text(self, path) -> str:
        path = self.resolve(path)
        if path not in self._texts:
            self._texts[path] = path.read_text(encoding="utf-8-sig")
        return self._texts[path]

    def json(self, path):
        path = self.resolve(path)
        if path not in self._json:
            def reject_constant(value):
                raise ValueError(f"Invalid JSON number: {value}")

            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError(f"Duplicate JSON key: {key}")
                    result[key] = value
                return result

            self._json[path] = json.loads(
                self.text(path), parse_constant=reject_constant,
                object_pairs_hook=unique_object,
            )
        return deepcopy(self._json[path])
