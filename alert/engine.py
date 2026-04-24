from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class AlertEvent:
    kind: str
    title: str
    body: str
    timestamp: datetime

    def telegram_text(self) -> str:
        stamp = self.timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"[APYX {self.kind}] {self.title}\n{self.body}\nTime: {stamp}"


@dataclass
class AlertState:
    active: bool = False
    last_sent_at: datetime | None = None


class AlertEngine:
    def __init__(self, cooldown: timedelta) -> None:
        self.cooldown = cooldown
        self._states: dict[str, AlertState] = {}

    def evaluate(
        self,
        *,
        metric_key: str,
        breached: bool,
        alert_title: str,
        alert_body: str,
        recovery_title: str,
        recovery_body: str,
        now: datetime,
    ) -> AlertEvent | None:
        state = self._states.setdefault(metric_key, AlertState())
        if breached:
            if (
                not state.active
                or state.last_sent_at is None
                or now - state.last_sent_at >= self.cooldown
            ):
                state.active = True
                state.last_sent_at = now
                return AlertEvent("ALERT", alert_title, alert_body, now)
            return None

        if state.active:
            state.active = False
            return AlertEvent("RECOVERY", recovery_title, recovery_body, now)

        return None
