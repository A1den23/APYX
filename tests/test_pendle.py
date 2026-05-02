from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from app.history import RollingMetricHistory
from monitors.pendle import PendleMarketSnapshot, evaluate_pendle_market, parse_pendle_market


def test_parse_pendle_market_extracts_snapshot() -> None:
    payload = {
        "liquidity": {"usd": 2500000},
        "impliedApy": 0.081,
        "pt": {"price": {"usd": 0.962}},
    }

    snapshot = parse_pendle_market("apxUSD", payload)

    assert snapshot == PendleMarketSnapshot(name="apxUSD", liquidity=2500000.0, implied_apy=0.081, pt_price=0.962)


def test_evaluate_pendle_market_alerts_on_liquidity_drop() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("pendle_liquidity:apxUSD", 1000000.0, now - timedelta(minutes=30))

    events = evaluate_pendle_market(
        snapshot=PendleMarketSnapshot("apxUSD", liquidity=890000.0, implied_apy=0.08, pt_price=0.96),
        liquidity_drop_pct=0.10,
        apy_change_pct=0.10,
        pt_price_change_pct=0.10,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert len(events) == 1
    assert events[0].title == "Pendle apxUSD 流动性下降"
    assert "当前流动性: $890,000.00" in events[0].body
    assert "30m 变化: -11.00%" in events[0].body


def test_evaluate_pendle_market_alerts_on_immediate_changes() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("pendle_liquidity:apxUSD", 1_000_000.0, now - timedelta(minutes=1))
    history.record("pendle_apy:apxUSD", 0.08, now - timedelta(minutes=1))
    history.record("pendle_pt_price:apxUSD", 0.96, now - timedelta(minutes=1))

    events = evaluate_pendle_market(
        snapshot=PendleMarketSnapshot(
            "apxUSD",
            liquidity=890_000.0,
            implied_apy=0.10,
            pt_price=0.84,
        ),
        liquidity_drop_pct=0.10,
        apy_change_pct=0.10,
        pt_price_change_pct=0.10,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    titles = {event.title for event in events}
    assert "Pendle apxUSD 流动性下降" in titles
    assert "Pendle apxUSD PT APY 变化异常" in titles
    assert "Pendle apxUSD PT 价格变化异常" in titles
    assert all("1m 变化:" in event.body for event in events)
    assert all("30m 变化: 暂无" in event.body for event in events)
