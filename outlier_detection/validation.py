"""Shared primitive validation; no knowledge of methods or formats."""

import math


def keys(value, required, optional=()):
    if not isinstance(value, dict):
        raise ValueError("Expected a configuration object")
    missing = set(required) - value.keys()
    unknown = value.keys() - set(required) - set(optional)
    if missing or unknown:
        raise ValueError(f"Invalid configuration keys: missing={sorted(missing)}, unknown={sorted(unknown)}")


def positive(value, name):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
