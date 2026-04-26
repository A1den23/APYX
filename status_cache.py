from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class CachedValue:
    value: Any
    updated_at: datetime


class StatusCache:
    def __init__(self) -> None:
        self._values: dict[str, CachedValue] = {}
        self._lock = Lock()

    def set(self, key: str, value: Any, updated_at: datetime) -> None:
        with self._lock:
            self._values[key] = CachedValue(value=value, updated_at=updated_at)

    def get(self, key: str) -> CachedValue | None:
        with self._lock:
            return self._values.get(key)
