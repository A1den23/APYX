from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine


def test_alert_engine_deduplicates_within_cooldown() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    first = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    second = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9950",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=1),
    )

    assert first is not None
    assert first.kind == "ALERT"
    assert second is None


def test_alert_engine_sends_recovery_once() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    recovery = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=False,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=1),
    )
    duplicate = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=False,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=2),
    )

    assert recovery is not None
    assert recovery.kind == "RECOVERY"
    assert duplicate is None


def test_alert_engine_sends_new_alert_immediately_after_recovery() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    first = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    recovery = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=False,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=1),
    )
    second = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9950",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=2),
    )

    assert first is not None
    assert first.kind == "ALERT"
    assert recovery is not None
    assert recovery.kind == "RECOVERY"
    assert second is not None
    assert second.kind == "ALERT"


def test_alert_engine_repeats_continuous_breach_after_cooldown() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    first = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    repeat = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9950",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=5),
    )

    assert first is not None
    assert first.kind == "ALERT"
    assert repeat is not None
    assert repeat.kind == "ALERT"


def test_alert_engine_can_rollback_failed_alert_delivery() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
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

    engine.rollback(event)
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
    assert retry.kind == "ALERT"


def test_alert_engine_can_rollback_failed_recovery_delivery() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    recovery = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=False,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=1),
    )
    assert recovery is not None

    engine.rollback(recovery)
    retry = engine.evaluate(
        metric_key="peg:apxUSD",
        breached=False,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now + timedelta(minutes=2),
    )

    assert retry is not None
    assert retry.kind == "RECOVERY"
