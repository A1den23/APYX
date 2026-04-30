from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from app.config import CommitTokenConfig
from app.history import RollingMetricHistory
from monitors.commit import (
    CommitTokenSnapshot,
    evaluate_commit_token,
    fetch_commit_token_snapshot,
)


class FunctionCall:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


class FakeFunctions:
    def totalAssets(self):
        return FunctionCall(45_000_000 * 10**18)

    def totalSupply(self):
        return FunctionCall(45_000_000 * 10**18)

    def decimals(self):
        return FunctionCall(18)

    def supplyCap(self):
        return FunctionCall(50_000_000 * 10**18)

    def supplyCapRemaining(self):
        return FunctionCall(5_000_000 * 10**18)

    def unlockingDelay(self):
        return FunctionCall(14 * 24 * 60 * 60)


class FakeEth:
    def contract(self, *, address, abi):
        assert address == "commit"

        class Contract:
            functions = FakeFunctions()

        return Contract()


class FakeWeb3:
    eth = FakeEth()


def test_fetch_commit_token_snapshot_reads_assets_cap_and_delay(monkeypatch) -> None:
    monkeypatch.setattr("monitors.commit.Web3.to_checksum_address", lambda address: address)
    token = CommitTokenConfig(
        name="apxUSD Commit",
        address="commit",
        asset="apxUSD",
        absolute_change_threshold=5_000_000,
    )

    snapshot = fetch_commit_token_snapshot(FakeWeb3(), token=token)

    assert snapshot.name == "apxUSD Commit"
    assert snapshot.total_assets == 45_000_000
    assert snapshot.total_supply == 45_000_000
    assert snapshot.supply_cap == 50_000_000
    assert snapshot.supply_cap_remaining == 5_000_000
    assert snapshot.unlocking_delay_seconds == 14 * 24 * 60 * 60


def test_evaluate_commit_token_alerts_on_cap_usage_and_asset_drop() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 30, 8, 0, tzinfo=timezone.utc)
    history.record("commit_assets:apxUSD Commit", 60_000_000, now - timedelta(minutes=30))

    events = evaluate_commit_token(
        snapshot=CommitTokenSnapshot(
            name="apxUSD Commit",
            asset="apxUSD",
            total_assets=45_000_000,
            total_supply=45_000_000,
            supply_cap=50_000_000,
            supply_cap_remaining=5_000_000,
            unlocking_delay_seconds=14 * 24 * 60 * 60,
        ),
        cap_usage_warning_pct=0.90,
        assets_change_pct=0.10,
        assets_absolute_change_threshold=5_000_000,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    titles = {event.title for event in events}
    assert "apxUSD Commit cap 使用率过高" in titles
    assert "apxUSD Commit 资产变化异常" in titles
