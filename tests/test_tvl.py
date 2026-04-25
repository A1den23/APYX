import asyncio
from datetime import datetime, timedelta, timezone

from config import NamedAddress
from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors.tvl import evaluate_tvl, fetch_tvl_for_token


def test_fetch_tvl_for_token_uses_onchain_total_supply(monkeypatch) -> None:
    async def fake_fetch_total_supply_async(web3, *, address: str) -> float:
        assert address == "0x98A878b1Cd98131B271883B390f68D2c90674665"
        return 194987002.0

    monkeypatch.setattr("monitors.tvl.fetch_total_supply_async", fake_fetch_total_supply_async)
    token = NamedAddress(
        name="apxUSD",
        address="0x98A878b1Cd98131B271883B390f68D2c90674665",
    )

    assert asyncio.run(fetch_tvl_for_token(None, object(), token)) == 194987002.0


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
