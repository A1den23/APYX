from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from errors import safe_error_message


@dataclass
class MetricHealth:
    last_success_at: datetime | None = None
    last_error: str | None = None
    success_count: int = 0
    fail_count: int = 0
    interval_seconds: float = 0


class HealthTracker:
    def __init__(self) -> None:
        self.started_at = datetime.now(timezone.utc)
        self._metrics: dict[str, MetricHealth] = {}
        self._lock = Lock()

    def register(self, name: str, interval_seconds: float) -> None:
        with self._lock:
            self._metrics[name] = MetricHealth(interval_seconds=interval_seconds)

    def record_success(self, name: str) -> None:
        with self._lock:
            m = self._metrics.setdefault(name, MetricHealth())
            m.last_success_at = datetime.now(timezone.utc)
            m.success_count += 1

    def record_failure(self, name: str, error: str) -> None:
        with self._lock:
            m = self._metrics.setdefault(name, MetricHealth())
            m.last_error = safe_error_message(error)
            m.fail_count += 1

    @property
    def uptime(self) -> timedelta:
        return datetime.now(timezone.utc) - self.started_at

    def snapshot(self) -> dict[str, MetricHealth]:
        with self._lock:
            return dict(self._metrics)

    def total_runs(self) -> tuple[int, int, int]:
        total_ok = sum(m.success_count for m in self._metrics.values())
        total_fail = sum(m.fail_count for m in self._metrics.values())
        return total_ok + total_fail, total_ok, total_fail
