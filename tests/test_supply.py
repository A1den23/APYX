from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors.supply import evaluate_supply


def test_evaluate_supply_alerts_on_previous_sample_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("supply:apyUSD", 1000000.0, now - timedelta(minutes=1))

    event = evaluate_supply(
        token_name="apyUSD",
        supply=1110000.0,
        threshold_pct=0.10,
        absolute_change_threshold=2000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apyUSD Supply Change"
    assert "Current supply: 1,110,000.00" in event.body
    assert "1m change: +11.00%" in event.body
    assert "1m absolute change: +110,000.00" in event.body
    assert "30m change: N/A" in event.body


def test_evaluate_supply_alerts_on_absolute_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("supply:apxUSD", 195000000.0, now - timedelta(minutes=1))

    event = evaluate_supply(
        token_name="apxUSD",
        supply=201000000.0,
        threshold_pct=0.10,
        absolute_change_threshold=5000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apxUSD Supply Change"
    assert "1m change: +3.08%" in event.body
    assert "1m absolute change: +6,000,000.00" in event.body


def test_evaluate_supply_alerts_on_window_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("supply:apxUSD", 100000000.0, now - timedelta(minutes=30))
    history.record("supply:apxUSD", 119000000.0, now - timedelta(minutes=1))

    event = evaluate_supply(
        token_name="apxUSD",
        supply=120000000.0,
        threshold_pct=0.10,
        absolute_change_threshold=5000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apxUSD Supply Change"
    assert "1m change: +0.84%" in event.body
    assert "30m change: +20.00%" in event.body
    assert "30m absolute change: +20,000,000.00" in event.body


def test_evaluate_supply_does_not_alert_without_previous_sample() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)

    event = evaluate_supply(
        token_name="apyUSD",
        supply=1000000.0,
        threshold_pct=0.10,
        absolute_change_threshold=2000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is None


def test_evaluate_supply_does_not_alert_at_exact_threshold() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("supply:apyUSD", 1.0, now - timedelta(minutes=1))

    event = evaluate_supply(
        token_name="apyUSD",
        supply=1.1,
        threshold_pct=0.10,
        absolute_change_threshold=2000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is None


def test_evaluate_supply_sends_recovery_after_active_alert() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("supply:apyUSD", 1000000.0, now - timedelta(minutes=1))
    evaluate_supply(
        token_name="apyUSD",
        supply=1110000.0,
        threshold_pct=0.10,
        absolute_change_threshold=2000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    event = evaluate_supply(
        token_name="apyUSD",
        supply=1111000.0,
        threshold_pct=0.10,
        absolute_change_threshold=2000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now + timedelta(minutes=1),
    )

    assert event is not None
    assert event.kind == "RECOVERY"
    assert event.title == "apyUSD Supply Normal"
