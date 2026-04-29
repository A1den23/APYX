from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from monitors.strc_price import evaluate_strc_price


def test_evaluate_strc_price_alerts_below_threshold() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    event = evaluate_strc_price(price=94.25, threshold=95.0, engine=engine, now=now)

    assert event is not None
    assert event.kind == "ALERT"
    assert "当前价格: $94.25" in event.body
    assert "相对面值跌幅: 5.75%" in event.body
    assert "距离面值: $5.75" in event.body


def test_evaluate_strc_price_recovers_at_threshold() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)
    evaluate_strc_price(price=94.25, threshold=95.0, engine=engine, now=now)

    event = evaluate_strc_price(price=95.00, threshold=95.0, engine=engine, now=now + timedelta(minutes=1))

    assert event is not None
    assert event.kind == "RECOVERY"


def test_evaluate_strc_price_recovery_above_par_has_no_negative_drop_or_distance() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)
    evaluate_strc_price(price=94.25, threshold=95.0, engine=engine, now=now)

    event = evaluate_strc_price(price=101.00, threshold=95.0, engine=engine, now=now + timedelta(minutes=1))

    assert event is not None
    assert event.kind == "RECOVERY"
    assert "相对面值跌幅: 0.00%" in event.body
    assert "距离面值: $0.00" in event.body
