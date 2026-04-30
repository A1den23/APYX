from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from app.history import RollingMetricHistory
from monitors.yield_distribution import (
    YieldDistributionSnapshot,
    evaluate_yield_distribution,
    fetch_yield_distribution_snapshot,
)


class FunctionCall:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


class RateViewFunctions:
    def annualizedYield(self):
        return FunctionCall(12_000_000 * 10**18)

    def apy(self):
        return FunctionCall(12_7 * 10**15)

    def precision(self):
        return FunctionCall(10**18)


class ApyUsdFunctions:
    def vesting(self):
        return FunctionCall("vesting")


class VestingFunctions:
    def vestedAmount(self):
        return FunctionCall(1_000_000 * 10**18)

    def unvestedAmount(self):
        return FunctionCall(5_000_000 * 10**18)

    def vestingPeriodRemaining(self):
        return FunctionCall(20 * 24 * 60 * 60)


class TokenFunctions:
    def decimals(self):
        return FunctionCall(18)


class FakeEth:
    def contract(self, *, address, abi):
        class Contract:
            pass

        contract = Contract()
        if address == "rate":
            contract.functions = RateViewFunctions()
        elif address == "apy":
            contract.functions = ApyUsdFunctions()
        elif address == "vesting":
            contract.functions = VestingFunctions()
        elif address == "apx":
            contract.functions = TokenFunctions()
        else:
            raise AssertionError(address)
        return contract


class FakeWeb3:
    eth = FakeEth()


def test_fetch_yield_distribution_snapshot_reads_rate_view_and_vesting(monkeypatch) -> None:
    monkeypatch.setattr("monitors.yield_distribution.Web3.to_checksum_address", lambda address: address)

    snapshot = fetch_yield_distribution_snapshot(
        FakeWeb3(),
        apyusd_address="apy",
        apxusd_address="apx",
        rate_view_address="rate",
    )

    assert snapshot.annualized_yield == 12_000_000
    assert snapshot.apy == 0.127
    assert snapshot.vesting_address == "vesting"
    assert snapshot.vested_amount == 1_000_000
    assert snapshot.unvested_amount == 5_000_000
    assert snapshot.vesting_period_remaining_seconds == 20 * 24 * 60 * 60


def test_evaluate_yield_distribution_alerts_on_apy_and_unvested_changes() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 30, 8, 0, tzinfo=timezone.utc)
    history.record("yield_distribution:apy", 0.12, now - timedelta(minutes=30))
    history.record("yield_distribution:unvested", 5_000_000, now - timedelta(minutes=30))

    events = evaluate_yield_distribution(
        snapshot=YieldDistributionSnapshot(
            annualized_yield=9_000_000,
            apy=0.08,
            vesting_address="vesting",
            vested_amount=1_000_000,
            unvested_amount=3_500_000,
            vesting_period_remaining_seconds=20 * 24 * 60 * 60,
        ),
        apy_change_pct=0.10,
        annualized_yield_change_pct=0.10,
        unvested_change_pct=0.20,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    titles = {event.title for event in events}
    assert "apyUSD 收益 APY 变化异常" in titles
    assert "apyUSD 未归属收益变化异常" in titles
