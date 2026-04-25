import asyncio
from datetime import timedelta

from alert.engine import AlertEngine
from config import EnvConfig, load_app_config
from history import RollingMetricHistory
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

    async def fake_fetch_tvl_for_token(session, web3, token) -> float:
        return 194_987_002.0

    async def fake_fetch_total_assets_async(web3, *, address: str) -> float:
        return 72_328_062.10

    async def fake_fetch_price_apxusd_async(web3, *, address: str) -> float:
        return 1.3569

    monkeypatch.setattr("status.fetch_strc_price", fake_fetch_strc_price)
    monkeypatch.setattr("status.fetch_pendle_market", fake_fetch_pendle_market)
    monkeypatch.setattr("status.fetch_peg_price", fake_fetch_peg_price)
    monkeypatch.setattr("status.fetch_total_supply_async", fake_fetch_total_supply_async)
    monkeypatch.setattr("status.fetch_tvl_for_token", fake_fetch_tvl_for_token)
    monkeypatch.setattr("status.fetch_total_assets_async", fake_fetch_total_assets_async)
    monkeypatch.setattr("status.fetch_price_apxusd_async", fake_fetch_price_apxusd_async)

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
    assert "apyUSD 供应 (share totalSupply)" in message
    assert "apyUSD totalAssets" in message
    assert "apyUSD priceAPXUSD" in message
