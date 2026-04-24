from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors.tvl import evaluate_tvl, parse_tvl


def test_parse_tvl_accepts_numeric_payload() -> None:
    assert parse_tvl(1234567.89) == 1234567.89


def test_parse_tvl_accepts_json_tvl_field() -> None:
    assert parse_tvl({"tvl": 1234567.89}) == 1234567.89


def test_evaluate_tvl_alerts_on_one_hour_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("tvl:apxUSD", 1000000.0, now - timedelta(minutes=60))

    event = evaluate_tvl(
        token_name="apxUSD",
        tvl=870000.0,
        threshold_pct=0.10,
        window_minutes=60,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apxUSD TVL Change"
    assert "Current TVL: $870,000.00" in event.body
    assert "1h change: -13.00%" in event.body


def test_evaluate_tvl_does_not_alert_without_baseline() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)

    event = evaluate_tvl(
        token_name="apxUSD",
        tvl=1000000.0,
        threshold_pct=0.10,
        window_minutes=60,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is None


def test_evaluate_tvl_does_not_alert_at_exact_threshold() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("tvl:apxUSD", 1.0, now - timedelta(minutes=60))

    event = evaluate_tvl(
        token_name="apxUSD",
        tvl=1.1,
        threshold_pct=0.10,
        window_minutes=60,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is None


def test_evaluate_tvl_sends_recovery_after_active_alert() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("tvl:apxUSD", 1000000.0, now - timedelta(minutes=60))
    evaluate_tvl(
        token_name="apxUSD",
        tvl=870000.0,
        threshold_pct=0.10,
        window_minutes=60,
        history=history,
        engine=engine,
        now=now,
    )

    event = evaluate_tvl(
        token_name="apxUSD",
        tvl=950000.0,
        threshold_pct=0.10,
        window_minutes=60,
        history=history,
        engine=engine,
        now=now + timedelta(minutes=1),
    )

    assert event is not None
    assert event.kind == "RECOVERY"
    assert event.title == "apxUSD TVL Normal"
