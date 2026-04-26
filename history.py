from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class MetricSample:
    value: float
    timestamp: datetime


@dataclass(frozen=True)
class MetricChange:
    baseline: float
    current: float
    percent: float


def percent_change(*, current: float, baseline: float) -> float:
    if baseline == 0:
        raise ValueError("baseline cannot be zero")
    return (current - baseline) / baseline


class RollingMetricHistory:
    def __init__(self, retention_minutes: int = 180) -> None:
        self._retention = timedelta(minutes=retention_minutes)
        self._samples: dict[str, deque[MetricSample]] = defaultdict(deque)

    def record(self, key: str, value: float, timestamp: datetime) -> None:
        samples = self._samples[key]
        samples.append(MetricSample(value=value, timestamp=timestamp))
        latest_timestamp = max(sample.timestamp for sample in samples)
        cutoff = latest_timestamp - self._retention
        self._samples[key] = deque(
            sample for sample in samples if sample.timestamp >= cutoff
        )

    def latest_sample(self, key: str) -> MetricSample | None:
        samples = self._samples.get(key)
        if not samples:
            return None
        return samples[-1]

    def latest_change(self, key: str, *, current: float) -> MetricChange | None:
        samples = self._samples.get(key)
        if not samples:
            return None
        baseline = samples[-1].value
        if baseline == 0:
            return None
        return MetricChange(
            baseline=baseline,
            current=current,
            percent=percent_change(current=current, baseline=baseline),
        )

    def window_change(
        self, key: str, *, current: float, now: datetime, window_minutes: int
    ) -> MetricChange | None:
        samples = self._samples.get(key)
        if not samples:
            return None
        cutoff = now - timedelta(minutes=window_minutes)
        baseline_sample = max(
            (sample for sample in samples if sample.timestamp <= cutoff),
            key=lambda sample: sample.timestamp,
            default=None,
        )
        if baseline_sample is None:
            return None
        if baseline_sample.value == 0:
            return None
        return MetricChange(
            baseline=baseline_sample.value,
            current=current,
            percent=percent_change(current=current, baseline=baseline_sample.value),
        )

    def to_dict(self) -> dict:
        return {
            "retention_minutes": self._retention.total_seconds() / 60,
            "samples": {
                key: [
                    {
                        "value": sample.value,
                        "timestamp": sample.timestamp.isoformat(),
                    }
                    for sample in samples
                ]
                for key, samples in self._samples.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RollingMetricHistory":
        history = cls(retention_minutes=int(data.get("retention_minutes", 180)))
        for key, samples in data.get("samples", {}).items():
            history._samples[key] = deque(
                MetricSample(
                    value=float(sample["value"]),
                    timestamp=datetime.fromisoformat(sample["timestamp"]),
                )
                for sample in samples
            )
        return history
