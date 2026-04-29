from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from monitors.peg import evaluate_peg_price, parse_defillama_price


def test_parse_defillama_price_extracts_coin_price() -> None:
    payload = {
        "coins": {
            "ethereum:0x98A878b1Cd98131B271883B390f68D2c90674665": {
                "price": 0.9965
            }
        }
    }

    assert parse_defillama_price(payload, "ethereum:0x98A878b1Cd98131B271883B390f68D2c90674665") == 0.9965


def test_evaluate_peg_price_alerts_on_deviation() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    event = evaluate_peg_price(token_name="apxUSD", price=0.9965, threshold_pct=0.003, engine=engine, now=now)

    assert event is not None
    assert event.kind == "ALERT"
    assert "价格: $0.9965" in event.body
    assert "偏离: -0.35%" in event.body


def test_evaluate_peg_price_does_not_alert_at_exact_lower_threshold() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    event = evaluate_peg_price(token_name="apxUSD", price=0.997, threshold_pct=0.003, engine=engine, now=now)

    assert event is None


def test_evaluate_peg_price_does_not_alert_at_exact_upper_threshold() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    event = evaluate_peg_price(token_name="apxUSD", price=1.003, threshold_pct=0.003, engine=engine, now=now)

    assert event is None


def test_evaluate_peg_price_alerts_beyond_threshold() -> None:
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)

    event = evaluate_peg_price(token_name="apxUSD", price=0.9969, threshold_pct=0.003, engine=engine, now=now)

    assert event is not None
    assert event.kind == "ALERT"
