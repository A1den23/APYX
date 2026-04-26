import asyncio
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine, AlertEvent
from commands.health import HealthTracker
from main import send_events


class FailingSender:
    async def send(self, event: AlertEvent) -> None:
        raise RuntimeError("send failed token=secret")


class RecordingSender:
    def __init__(self) -> None:
        self.events: list[AlertEvent] = []

    async def send(self, event: AlertEvent) -> None:
        self.events.append(event)


def test_send_events_rolls_back_failed_delivery_and_records_safe_error() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    tracker = HealthTracker()
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)
    event = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    assert event is not None

    asyncio.run(
        send_events(
            FailingSender(),
            events=[event],
            engine=engine,
            tracker=tracker,
        )
    )

    retry = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9950",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=1),
    )
    assert retry is not None

    errors = [m.last_error for m in tracker.snapshot().values() if m.last_error]
    assert errors
    assert "secret" not in errors[0]
    assert "token=<redacted>" in errors[0]


def test_send_events_returns_false_when_any_delivery_fails() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    tracker = HealthTracker()
    event = AlertEvent(
        "ALERT",
        "apxUSD Large Mint",
        "Amount: 6,000,000.00 apxUSD",
        datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc),
    )

    delivered = asyncio.run(
        send_events(
            FailingSender(),
            events=[event],
            engine=engine,
            tracker=tracker,
        )
    )

    assert delivered is False


def test_send_events_returns_true_when_all_deliveries_succeed() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    tracker = HealthTracker()
    event = AlertEvent(
        "ALERT",
        "apxUSD Large Mint",
        "Amount: 6,000,000.00 apxUSD",
        datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc),
    )
    sender = RecordingSender()

    delivered = asyncio.run(
        send_events(
            sender,
            events=[event],
            engine=engine,
            tracker=tracker,
        )
    )

    assert delivered is True
    assert sender.events == [event]
