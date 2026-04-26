from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors.security_events import LogScanState, RecentSecurityEventCache


@dataclass
class RuntimeState:
    alert_engine: AlertEngine
    history: RollingMetricHistory
    security_state: LogScanState
    recent_security_events: RecentSecurityEventCache


class RuntimeStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> RuntimeState:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return RuntimeState(
            alert_engine=AlertEngine.from_dict(data["alert_engine"]),
            history=RollingMetricHistory.from_dict(data["history"]),
            security_state=LogScanState.from_dict(data["security_state"]),
            recent_security_events=RecentSecurityEventCache.from_dict(
                data["recent_security_events"]
            ),
        )

    def save(self, state: RuntimeState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(
                {
                    "alert_engine": state.alert_engine.to_dict(),
                    "history": state.history.to_dict(),
                    "security_state": state.security_state.to_dict(),
                    "recent_security_events": state.recent_security_events.to_dict(),
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        tmp_path.replace(self.path)
