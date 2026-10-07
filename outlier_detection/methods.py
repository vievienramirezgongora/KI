"""Built-in detectors: local parameter validation and pure computation, no I/O."""

import math
import statistics
from dataclasses import dataclass
from types import MappingProxyType

from .contracts import Detection
from .validation import keys, positive


def finite(*values):
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Numeric range exceeded during statistical calculation")


def quantile(sorted_values, probability):
    """Linear interpolation, position (n-1)*p (Hyndman–Fan type 7)."""
    position = (len(sorted_values) - 1) * probability
    left, right = math.floor(position), math.ceil(position)
    fraction = position - left
    return sorted_values[left] * (1 - fraction) + sorted_values[right] * fraction


def standardized(values, center, spread, scale, threshold, zero_policy, details):
    finite(center, spread)
    if spread == 0:
        if zero_policy == "error":
            raise ValueError("Zero spread: standardized score is undefined")
        flags = tuple(x != center for x in values)
        scores = tuple(None for _ in values)
    else:
        scores = tuple(scale * ((x - center) / spread) for x in values)
        finite(*scores)
        flags = tuple(abs(score) > threshold for score in scores)
    return Detection(flags, scores, dict(details, threshold=threshold,
                     zero_spread=spread == 0, zero_spread_policy=zero_policy))


@dataclass(frozen=True)
class Tukey:
    factor: float

    @classmethod
    def from_config(cls, settings, zero_spread):
        keys(settings, ("factor",))
        positive(settings["factor"], "factor")
        return cls(settings["factor"])

    def detect(self, values):
        ordered = sorted(values)
        q1, q3 = quantile(ordered, 0.25), quantile(ordered, 0.75)
        iqr = q3 - q1
        lower, upper = q1 - self.factor * iqr, q3 + self.factor * iqr
        finite(q1, q3, iqr, lower, upper)
        return Detection(tuple(x < lower or x > upper for x in values), None,
                         dict(q1=q1, q3=q3, iqr=iqr, factor=self.factor,
                              lower=lower, upper=upper, quantile_method="linear_type_7"))


@dataclass(frozen=True)
class ZScore:
    threshold: float
    ddof: int
    zero_spread: str

    @classmethod
    def from_config(cls, settings, zero_spread):
        keys(settings, ("threshold", "ddof"))
        positive(settings["threshold"], "threshold")
        if type(settings["ddof"]) is not int or settings["ddof"] not in (0, 1):
            raise ValueError("zscore.ddof must be 0 or 1")
        return cls(settings["threshold"], settings["ddof"], zero_spread)

    def detect(self, values):
        if len(values) <= self.ddof:
            raise ValueError("Z-score requires more observations than ddof")
        center = statistics.fmean(values)
        spread = statistics.pstdev(values) if self.ddof == 0 else statistics.stdev(values)
        return standardized(values, center, spread, 1, self.threshold,
                            self.zero_spread, dict(mean=center, std=spread, ddof=self.ddof))


@dataclass(frozen=True)
class ModifiedZScore:
    threshold: float
    scale: float
    zero_spread: str

    @classmethod
    def from_config(cls, settings, zero_spread):
        keys(settings, ("threshold", "scale"))
        positive(settings["threshold"], "threshold")
        positive(settings["scale"], "scale")
        return cls(settings["threshold"], settings["scale"], zero_spread)

    def detect(self, values):
        center = statistics.median(values)
        mad = statistics.median(abs(x - center) for x in values)
        return standardized(values, center, mad, self.scale, self.threshold,
                            self.zero_spread, dict(median=center, mad=mad, scale=self.scale))


DETECTORS = MappingProxyType({
    "tukey": Tukey.from_config,
    "zscore": ZScore.from_config,
    "modified_zscore": ModifiedZScore.from_config,
})
