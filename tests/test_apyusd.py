from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors import apyusd as apyusd_module
from monitors.apyusd import (
    evaluate_price_apxusd,
    evaluate_total_assets,
    fetch_price_apxusd,
    fetch_total_assets,
)


class FunctionCall:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


class FakeFunctions:
    def totalAssets(self):
        return FunctionCall(72_328_062_095629830000000000)

    def decimals(self):
        return FunctionCall(18)

    def previewRedeem(self, shares):
        assert shares == 10**18
        return FunctionCall(1_356_889_598_721_176_900)


class FakeEth:
    def contract(self, *, address, abi):
        assert address == "0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A"

        class Contract:
            functions = FakeFunctions()

        return Contract()


class FakeWeb3:
    eth = FakeEth()


def test_fetch_total_assets_reads_erc4626_total_assets(monkeypatch) -> None:
    monkeypatch.setattr(apyusd_module.Web3, "to_checksum_address", lambda address: address)

    assert fetch_total_assets(
        FakeWeb3(),
        address="0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A",
    ) == 72328062.09562983


def test_fetch_price_apxusd_reads_preview_redeem(monkeypatch) -> None:
    monkeypatch.setattr(apyusd_module.Web3, "to_checksum_address", lambda address: address)

    assert fetch_price_apxusd(
        FakeWeb3(),
        address="0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A",
    ) == 1.3568895987211769


def test_evaluate_total_assets_alerts_on_previous_sample_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("total_assets:apyUSD", 1000000.0, now - timedelta(minutes=1))

    event = evaluate_total_assets(
        token_name="apyUSD",
        total_assets=870000.0,
        threshold_pct=0.10,
        absolute_change_threshold=5000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apyUSD totalAssets Change"
    assert "Current totalAssets: 870,000.00 apxUSD" in event.body
    assert "1m change: -13.00%" in event.body
    assert "1m absolute change: -130,000.00 apxUSD" in event.body
    assert "30m change: N/A" in event.body


def test_evaluate_total_assets_alerts_on_absolute_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("total_assets:apyUSD", 72000000.0, now - timedelta(minutes=1))

    event = evaluate_total_assets(
        token_name="apyUSD",
        total_assets=77500000.0,
        threshold_pct=0.10,
        absolute_change_threshold=5000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert "1m change: +7.64%" in event.body
    assert "1m absolute change: +5,500,000.00 apxUSD" in event.body


def test_evaluate_total_assets_alerts_on_window_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("total_assets:apyUSD", 70000000.0, now - timedelta(minutes=30))
    history.record("total_assets:apyUSD", 76500000.0, now - timedelta(minutes=1))

    event = evaluate_total_assets(
        token_name="apyUSD",
        total_assets=77000000.0,
        threshold_pct=0.10,
        absolute_change_threshold=5000000.0,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apyUSD totalAssets Change"
    assert "1m change: +0.65%" in event.body
    assert "30m change: +10.00%" in event.body
    assert "30m absolute change: +7,000,000.00 apxUSD" in event.body


def test_evaluate_price_apxusd_alerts_on_previous_sample_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("apyusd_price_apxusd", 1.20, now - timedelta(minutes=1))

    event = evaluate_price_apxusd(
        price_apxusd=1.34,
        threshold_pct=0.05,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apyUSD priceAPXUSD Change"
    assert "Current priceAPXUSD: 1.3400 apxUSD" in event.body
    assert "1m change: +11.67%" in event.body
    assert "30m change: N/A" in event.body


def test_evaluate_price_apxusd_alerts_on_window_change() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("apyusd_price_apxusd", 1.20, now - timedelta(minutes=30))
    history.record("apyusd_price_apxusd", 1.25, now - timedelta(minutes=1))

    event = evaluate_price_apxusd(
        price_apxusd=1.27,
        threshold_pct=0.05,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is not None
    assert event.title == "apyUSD priceAPXUSD Change"
    assert "1m change: +1.60%" in event.body
    assert "30m change: +5.83%" in event.body


def test_evaluate_price_apxusd_does_not_alert_without_baseline() -> None:
    history = RollingMetricHistory()
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)

    event = evaluate_price_apxusd(
        price_apxusd=1.34,
        threshold_pct=0.05,
        window_minutes=30,
        history=history,
        engine=engine,
        now=now,
    )

    assert event is None
