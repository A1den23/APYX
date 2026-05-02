from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from app.config import CurveCoin, CurvePool
from app.history import RollingMetricHistory
from monitors.curve import (
    CurvePoolSnapshot,
    evaluate_curve_pool,
    fetch_curve_pool_snapshot,
)


class FunctionCall:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


class PoolFunctions:
    def get_balances(self):
        return FunctionCall([100_000_000 * 10**18, 95_000_000 * 10**6])

    def get_virtual_price(self):
        return FunctionCall(1_002_000_000_000_000_000)

    def get_dy(self, i, j, dx):
        assert (i, j, dx) == (0, 1, 10**18)
        return FunctionCall(998_500)


class ApyPoolFunctions:
    def get_balances(self):
        return FunctionCall([2_000_000 * 10**18, 3_000_000 * 10**18])

    def get_virtual_price(self):
        return FunctionCall(1_002_000_000_000_000_000)

    def get_dy(self, i, j, dx):
        assert (i, j, dx) == (0, 1, 10**18)
        return FunctionCall(1_350_000_000_000_000_000)


class TokenFunctions:
    def __init__(self, decimals, preview_redeem=None):
        self._decimals = decimals
        self._preview_redeem = preview_redeem

    def decimals(self):
        return FunctionCall(self._decimals)

    def previewRedeem(self, shares):
        assert self._preview_redeem is not None
        assert shares == 10**self._decimals
        return FunctionCall(self._preview_redeem)


class FakeEth:
    def contract(self, *, address, abi):
        class Contract:
            pass

        contract = Contract()
        if address == "pool":
            contract.functions = PoolFunctions()
        elif address == "apy_pool":
            contract.functions = ApyPoolFunctions()
        elif address == "apx":
            contract.functions = TokenFunctions(18)
        elif address == "apy":
            contract.functions = TokenFunctions(18, preview_redeem=1_360_000_000_000_000_000)
        elif address == "usdc":
            contract.functions = TokenFunctions(6)
        else:
            raise AssertionError(address)
        return contract


class FakeWeb3:
    eth = FakeEth()


def test_fetch_curve_pool_snapshot_reads_balances_virtual_price_and_swap_price(monkeypatch) -> None:
    monkeypatch.setattr("monitors.curve.Web3.to_checksum_address", lambda address: address)
    pool = CurvePool(
        name="apxUSD-USDC",
        address="pool",
        coins=(
            CurveCoin(name="apxUSD", address="apx"),
            CurveCoin(name="USDC", address="usdc"),
        ),
    )

    snapshot = fetch_curve_pool_snapshot(FakeWeb3(), pool=pool)

    assert snapshot.name == "apxUSD-USDC"
    assert snapshot.balances["apxUSD"] == 100_000_000
    assert snapshot.balances["USDC"] == 95_000_000
    assert snapshot.virtual_price == 1.002
    assert snapshot.apxusd_usdc_price == 0.9985


def test_fetch_curve_pool_snapshot_reads_apyusd_apxusd_value_and_relative_price(monkeypatch) -> None:
    monkeypatch.setattr("monitors.curve.Web3.to_checksum_address", lambda address: address)
    pool = CurvePool(
        name="apyUSD-apxUSD",
        address="apy_pool",
        coins=(
            CurveCoin(name="apyUSD", address="apy"),
            CurveCoin(name="apxUSD", address="apx"),
        ),
        metrics=("total_value", "apyusd_apxusd_price", "virtual_price"),
        price_deviation_pct=0.015,
    )

    snapshot = fetch_curve_pool_snapshot(FakeWeb3(), pool=pool)

    assert snapshot.name == "apyUSD-apxUSD"
    assert snapshot.balances["apyUSD"] == 2_000_000
    assert snapshot.balances["apxUSD"] == 3_000_000
    assert snapshot.virtual_price == 1.002
    assert snapshot.apyusd_apxusd_price == 1.35
    assert snapshot.apyusd_price_apxusd == 1.36
    assert snapshot.total_value_apxusd == 5_720_000
    assert snapshot.value_adjusted_imbalance == 0.04895104895104895


def test_evaluate_curve_pool_alerts_on_balance_drop_and_price_deviation() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 30, 8, 0, tzinfo=timezone.utc)
    history.record("curve_balance:apxUSD-USDC:apxUSD", 100_000_000, now - timedelta(minutes=30))
    history.record("curve_virtual_price:apxUSD-USDC", 1.0, now - timedelta(minutes=30))

    events = evaluate_curve_pool(
        snapshot=CurvePoolSnapshot(
            name="apxUSD-USDC",
            balances={"apxUSD": 80_000_000, "USDC": 110_000_000},
            virtual_price=1.02,
            apxusd_usdc_price=0.995,
        ),
        balance_drop_pct=0.10,
        imbalance_pct=0.20,
        virtual_price_change_pct=0.01,
        price_deviation_pct=0.003,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    titles = {event.title for event in events}
    assert "Curve apxUSD-USDC apxUSD 余额下降" in titles
    assert "Curve apxUSD-USDC virtual price 变化异常" in titles
    assert "Curve apxUSD-USDC 价格偏离" in titles


def test_evaluate_curve_pool_alerts_on_apyusd_apxusd_value_price_and_virtual_price_only() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 30, 8, 0, tzinfo=timezone.utc)
    history.record("curve_total_value:apyUSD-apxUSD", 10_000_000, now - timedelta(minutes=30))
    history.record("curve_virtual_price:apyUSD-apxUSD", 1.0, now - timedelta(minutes=30))

    events = evaluate_curve_pool(
        snapshot=CurvePoolSnapshot(
            name="apyUSD-apxUSD",
            balances={"apyUSD": 2_000_000, "apxUSD": 3_000_000},
            virtual_price=1.02,
            apxusd_usdc_price=None,
            apyusd_apxusd_price=1.33,
            apyusd_price_apxusd=1.36,
            total_value_apxusd=8_000_000,
            metrics=("total_value", "apyusd_apxusd_price", "virtual_price"),
            price_deviation_pct=0.015,
            total_value_drop_pct=None,
        ),
        balance_drop_pct=0.10,
        imbalance_pct=0.20,
        virtual_price_change_pct=0.01,
        price_deviation_pct=0.003,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    titles = {event.title for event in events}
    assert "Curve apyUSD-apxUSD 总价值下降" in titles
    assert "Curve apyUSD-apxUSD virtual price 变化异常" in titles
    assert "Curve apyUSD-apxUSD apyUSD 价格偏离" in titles
    assert "Curve apyUSD-apxUSD apyUSD 余额下降" not in titles
    assert "Curve apyUSD-apxUSD 池子不平衡" not in titles


def test_evaluate_curve_pool_alerts_on_immediate_historical_metric_changes() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 30, 8, 0, tzinfo=timezone.utc)
    history.record(
        "curve_balance:apyUSD-apxUSD:apyUSD",
        2_000_000,
        now - timedelta(minutes=1),
    )
    history.record(
        "curve_total_value:apyUSD-apxUSD",
        10_000_000,
        now - timedelta(minutes=1),
    )
    history.record(
        "curve_virtual_price:apyUSD-apxUSD",
        1.0,
        now - timedelta(minutes=1),
    )

    events = evaluate_curve_pool(
        snapshot=CurvePoolSnapshot(
            name="apyUSD-apxUSD",
            balances={"apyUSD": 1_700_000},
            virtual_price=1.02,
            apxusd_usdc_price=None,
            total_value_apxusd=8_500_000,
            metrics=("balances", "total_value", "virtual_price"),
        ),
        balance_drop_pct=0.10,
        imbalance_pct=0.20,
        virtual_price_change_pct=0.01,
        price_deviation_pct=0.003,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    titles = {event.title for event in events}
    assert "Curve apyUSD-apxUSD apyUSD 余额下降" in titles
    assert "Curve apyUSD-apxUSD 总价值下降" in titles
    assert "Curve apyUSD-apxUSD virtual price 变化异常" in titles
    assert all("1m 变化:" in event.body for event in events)
    assert all("30m 变化: 暂无" in event.body for event in events)


def test_evaluate_curve_pool_alerts_on_value_adjusted_imbalance() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 30, 8, 0, tzinfo=timezone.utc)

    events = evaluate_curve_pool(
        snapshot=CurvePoolSnapshot(
            name="apyUSD-apxUSD",
            balances={"apyUSD": 2_000_000, "apxUSD": 1_000_000},
            virtual_price=1.0,
            apxusd_usdc_price=None,
            apyusd_apxusd_price=1.35,
            apyusd_price_apxusd=1.36,
            total_value_apxusd=3_720_000,
            value_adjusted_imbalance=0.4594594594594595,
            metrics=("value_adjusted_imbalance",),
            price_deviation_pct=0.015,
            total_value_drop_pct=None,
        ),
        balance_drop_pct=0.10,
        imbalance_pct=0.20,
        virtual_price_change_pct=0.01,
        price_deviation_pct=0.003,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert len(events) == 1
    assert events[0].metric_key == "curve_value_adjusted_imbalance:apyUSD-apxUSD"
    assert events[0].title == "Curve apyUSD-apxUSD value-adjusted 池子不平衡"
    assert "当前价值不平衡度: 45.95%" in events[0].body
