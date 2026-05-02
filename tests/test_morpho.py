from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from app.history import RollingMetricHistory
from monitors.morpho import (
    MorphoMarketSnapshot,
    evaluate_morpho_market,
    fetch_oracle_price,
    parse_morpho_market,
)


class FunctionCall:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


class OracleFunctions:
    def price(self):
        return FunctionCall(925_000_000_000_000_000_000_000)


class FakeEth:
    def contract(self, *, address, abi):
        assert address == "oracle"

        class Contract:
            functions = OracleFunctions()

        return Contract()


class FakeWeb3:
    eth = FakeEth()


def test_parse_morpho_market_extracts_market_size_liquidity_and_borrow_rate() -> None:
    payload = {
        "data": {
            "marketById": {
                "marketId": "0xa75b",
                "oracle": {"address": "0xoracle"},
                "loanAsset": {"symbol": "USDC", "decimals": 6},
                "collateralAsset": {"symbol": "PT-apyUSD-18JUN2026", "decimals": 18},
                "state": {
                    "borrowApy": 0.0444,
                    "borrowAssetsUsd": 20_480_000.0,
                    "supplyAssetsUsd": 23_103_000.0,
                    "utilization": 0.8864,
                },
            }
        }
    }

    snapshot = parse_morpho_market("PT-apyUSD-18JUN2026-USDC", payload)

    assert snapshot == MorphoMarketSnapshot(
        name="PT-apyUSD-18JUN2026-USDC",
        total_market_size_usd=23_103_000.0,
        total_liquidity_usd=2_623_000.0,
        borrow_rate=0.0444,
        utilization=0.8864,
        oracle_address="0xoracle",
        oracle_price=None,
        loan_asset_symbol="USDC",
        collateral_asset_symbol="PT-apyUSD-18JUN2026",
    )


def test_fetch_oracle_price_normalizes_price_to_loan_asset_units(monkeypatch) -> None:
    monkeypatch.setattr("monitors.morpho.Web3.to_checksum_address", lambda address: address)

    price = fetch_oracle_price(
        FakeWeb3(),
        oracle_address="oracle",
        collateral_decimals=18,
        loan_decimals=6,
    )

    assert price == 0.925


def test_evaluate_morpho_market_alerts_on_liquidity_drop_and_borrow_rate_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 5, 2, 10, 30, tzinfo=timezone.utc)
    history.record(
        "morpho_total_market_size:PT-apyUSD-18JUN2026-USDC",
        23_000_000.0,
        now - timedelta(minutes=30),
    )
    history.record(
        "morpho_total_liquidity:PT-apyUSD-18JUN2026-USDC",
        5_000_000.0,
        now - timedelta(minutes=30),
    )
    history.record(
        "morpho_borrow_rate:PT-apyUSD-18JUN2026-USDC",
        0.04,
        now - timedelta(minutes=30),
    )

    events = evaluate_morpho_market(
        snapshot=MorphoMarketSnapshot(
            name="PT-apyUSD-18JUN2026-USDC",
            total_market_size_usd=22_000_000.0,
            total_liquidity_usd=4_000_000.0,
            borrow_rate=0.05,
            utilization=0.8182,
            oracle_address="0xoracle",
            oracle_price=0.95,
            loan_asset_symbol="USDC",
            collateral_asset_symbol="PT-apyUSD-18JUN2026",
        ),
        total_market_size_drop_pct=0.10,
        total_liquidity_drop_pct=0.10,
        borrow_rate_change_pct=0.10,
        oracle_price_change_pct=0.02,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert [event.title for event in events] == [
        "Morpho PT-apyUSD-18JUN2026-USDC Total Liquidity 下降",
        "Morpho PT-apyUSD-18JUN2026-USDC borrow rate 变化异常",
    ]
    assert "当前 Total Liquidity: $4,000,000.00" in events[0].body
    assert "30m 变化: -20.00%" in events[0].body
    assert "当前 borrow rate: 5.00%" in events[1].body


def test_evaluate_morpho_market_alerts_on_oracle_price_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 5, 2, 10, 30, tzinfo=timezone.utc)
    history.record(
        "morpho_oracle_price:PT-apyUSD-18JUN2026-USDC",
        0.95,
        now - timedelta(minutes=1),
    )

    events = evaluate_morpho_market(
        snapshot=MorphoMarketSnapshot(
            name="PT-apyUSD-18JUN2026-USDC",
            total_market_size_usd=23_000_000.0,
            total_liquidity_usd=5_000_000.0,
            borrow_rate=0.04,
            utilization=0.78,
            oracle_address="0xoracle",
            oracle_price=0.925,
            loan_asset_symbol="USDC",
            collateral_asset_symbol="PT-apyUSD-18JUN2026",
        ),
        total_market_size_drop_pct=0.10,
        total_liquidity_drop_pct=0.10,
        borrow_rate_change_pct=0.10,
        oracle_price_change_pct=0.02,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert len(events) == 1
    assert events[0].title == "Morpho PT-apyUSD-18JUN2026-USDC oracle price 变化异常"
    assert "当前 oracle price: $0.9250" in events[0].body
    assert "1m 变化: -2.63%" in events[0].body


def test_evaluate_morpho_market_alerts_on_immediate_market_size_drop() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 5, 2, 10, 30, tzinfo=timezone.utc)
    history.record(
        "morpho_total_market_size:PT-apyUSD-18JUN2026-USDC",
        23_000_000.0,
        now - timedelta(minutes=1),
    )
    history.record(
        "morpho_total_liquidity:PT-apyUSD-18JUN2026-USDC",
        5_000_000.0,
        now - timedelta(minutes=1),
    )
    history.record(
        "morpho_borrow_rate:PT-apyUSD-18JUN2026-USDC",
        0.04,
        now - timedelta(minutes=1),
    )

    events = evaluate_morpho_market(
        snapshot=MorphoMarketSnapshot(
            name="PT-apyUSD-18JUN2026-USDC",
            total_market_size_usd=20_000_000.0,
            total_liquidity_usd=4_800_000.0,
            borrow_rate=0.041,
            utilization=0.76,
            oracle_address="0xoracle",
            oracle_price=0.95,
            loan_asset_symbol="USDC",
            collateral_asset_symbol="PT-apyUSD-18JUN2026",
        ),
        total_market_size_drop_pct=0.10,
        total_liquidity_drop_pct=0.10,
        borrow_rate_change_pct=0.10,
        oracle_price_change_pct=0.02,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert len(events) == 1
    assert events[0].title == "Morpho PT-apyUSD-18JUN2026-USDC Total Market Size 下降"
    assert "1m 变化: -13.04%" in events[0].body
    assert "30m 变化: 暂无" in events[0].body


def test_evaluate_morpho_market_records_each_metric_once() -> None:
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    snapshot = MorphoMarketSnapshot(
        name="test",
        total_market_size_usd=1_000_000.0,
        total_liquidity_usd=500_000.0,
        borrow_rate=0.05,
        utilization=0.8,
        oracle_address="0xoracle",
        loan_asset_symbol="USDC",
        collateral_asset_symbol="PT",
        oracle_price=1.0,
    )
    # Seed history so latest_change is not None
    history.record("morpho_total_market_size:test", 1_100_000.0, now - timedelta(minutes=2))
    history.record("morpho_total_liquidity:test", 550_000.0, now - timedelta(minutes=2))
    history.record("morpho_borrow_rate:test", 0.04, now - timedelta(minutes=2))
    history.record("morpho_oracle_price:test", 1.01, now - timedelta(minutes=2))

    evaluate_morpho_market(
        snapshot=snapshot,
        total_market_size_drop_pct=0.1,
        total_liquidity_drop_pct=0.1,
        borrow_rate_change_pct=0.2,
        oracle_price_change_pct=0.05,
        window_minutes=10,
        history=history,
        engine=engine,
        now=now,
    )

    # Each metric key should have exactly 2 samples: seed + 1 record
    for key in [
        "morpho_total_market_size:test",
        "morpho_total_liquidity:test",
        "morpho_borrow_rate:test",
        "morpho_oracle_price:test",
    ]:
        samples = list(history._samples[key])
        assert len(samples) == 2, f"{key} has {len(samples)} samples, expected 2"
