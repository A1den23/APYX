import asyncio
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from config import EnvConfig, load_app_config
from history import RollingMetricHistory
from monitors.solvency import AccountableSolvencySnapshot
from status import build_status_message


def test_status_labels_apyusd_supply_as_share_total_supply(monkeypatch) -> None:
    settings = load_app_config()
    env = EnvConfig(
        finnhub_api_key="key",
        telegram_bot_token="token",
        telegram_chat_id="chat",
        eth_rpc_url="rpc",
    )

    async def fake_fetch_strc_price(session, *, api_key: str, symbol: str) -> float:
        return 101.0

    async def fake_fetch_pendle_market(session, *, name: str, address: str):
        class Snapshot:
            liquidity = 1_000_000.0
            implied_apy = 0.08
            pt_price = 0.96

        return Snapshot()

    async def fake_fetch_peg_price(session, *, address: str) -> float:
        return 1.0

    async def fake_fetch_total_supply_async(web3, *, address: str) -> float:
        return 53_939_627.60 if address.endswith("A329Fe8a6A") else 194_987_002.0

    async def fake_fetch_total_assets_async(web3, *, address: str) -> float:
        return 72_328_062.10

    async def fake_fetch_price_apxusd_async(web3, *, address: str) -> float:
        return 1.3569

    async def fake_fetch_solvency_snapshot(session, *, url: str):
        return AccountableSolvencySnapshot(
            collateralization=1.007765,
            total_reserves=201_414_546.13,
            total_supply=199_862_614.0,
            net=1_551_932.13,
            timestamp=datetime(2026, 4, 26, 9, 20, 8, tzinfo=timezone.utc),
            verifiability="100",
            interval="live",
        )

    monkeypatch.setattr("status.fetch_strc_price", fake_fetch_strc_price)
    monkeypatch.setattr("status.fetch_pendle_market", fake_fetch_pendle_market)
    monkeypatch.setattr("status.fetch_peg_price", fake_fetch_peg_price)
    monkeypatch.setattr("status.fetch_total_supply_async", fake_fetch_total_supply_async)
    monkeypatch.setattr("status.fetch_total_assets_async", fake_fetch_total_assets_async)
    monkeypatch.setattr("status.fetch_price_apxusd_async", fake_fetch_price_apxusd_async)
    monkeypatch.setattr("status.fetch_solvency_snapshot", fake_fetch_solvency_snapshot)

    message, parse_mode = asyncio.run(
        build_status_message(
            session=object(),
            web3=object(),
            settings=settings,
            env=env,
            history=RollingMetricHistory(),
            engine=AlertEngine(cooldown=timedelta(minutes=5)),
        )
    )

    assert parse_mode == "HTML"
    assert "<b>apyUSD</b>" in message
    assert "供应 (share totalSupply)" in message
    assert "或 ±2.00M" in message
    assert "TVL" not in message
    assert "totalAssets" in message
    assert "priceAPXUSD" in message
    assert "Accountable PoR" in message
    assert "偿付率" in message
    assert "100.78%" in message


def test_status_marks_protocol_security_red_when_security_events_active(monkeypatch) -> None:
    settings = load_app_config()
    env = EnvConfig(
        finnhub_api_key="key",
        telegram_bot_token="token",
        telegram_chat_id="chat",
        eth_rpc_url="rpc",
    )

    async def fake_fetch_strc_price(session, *, api_key: str, symbol: str) -> float:
        return 101.0

    async def fake_fetch_pendle_market(session, *, name: str, address: str):
        class Snapshot:
            liquidity = 1_000_000.0
            implied_apy = 0.08
            pt_price = 0.96

        return Snapshot()

    async def fake_fetch_peg_price(session, *, address: str) -> float:
        return 1.0

    async def fake_fetch_total_supply_async(web3, *, address: str) -> float:
        return 53_939_627.60 if address.endswith("A329Fe8a6A") else 194_987_002.0

    async def fake_fetch_total_assets_async(web3, *, address: str) -> float:
        return 72_328_062.10

    async def fake_fetch_price_apxusd_async(web3, *, address: str) -> float:
        return 1.3569

    async def fake_fetch_solvency_snapshot(session, *, url: str):
        return AccountableSolvencySnapshot(
            collateralization=1.03,
            total_reserves=205_000_000.0,
            total_supply=199_000_000.0,
            net=6_000_000.0,
            timestamp=datetime(2026, 4, 26, 9, 20, 8, tzinfo=timezone.utc),
            verifiability="100",
            interval="live",
        )

    monkeypatch.setattr("status.fetch_strc_price", fake_fetch_strc_price)
    monkeypatch.setattr("status.fetch_pendle_market", fake_fetch_pendle_market)
    monkeypatch.setattr("status.fetch_peg_price", fake_fetch_peg_price)
    monkeypatch.setattr("status.fetch_total_supply_async", fake_fetch_total_supply_async)
    monkeypatch.setattr("status.fetch_total_assets_async", fake_fetch_total_assets_async)
    monkeypatch.setattr("status.fetch_price_apxusd_async", fake_fetch_price_apxusd_async)
    monkeypatch.setattr("status.fetch_solvency_snapshot", fake_fetch_solvency_snapshot)
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    engine.evaluate(
        metric_key="security_events",
        breached=True,
        alert_title="Security Events Recent",
        alert_body="Event: RoleGranted",
        recovery_title="Security Events Normal",
        recovery_body="No recent security events",
        now=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )

    message, parse_mode = asyncio.run(
        build_status_message(
            session=object(),
            web3=object(),
            settings=settings,
            env=env,
            history=RollingMetricHistory(),
            engine=engine,
        )
    )

    assert parse_mode == "HTML"
    assert "🔴 🔐 协议安全" in message
    assert "⚠️ 存在异常告警" in message
