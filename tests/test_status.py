import asyncio
from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from app.config import EnvConfig, load_app_config
from app.history import RollingMetricHistory
from monitors.commit import CommitTokenSnapshot
from monitors.curve import CurvePoolSnapshot
from monitors.pendle import PendleMarketSnapshot
from monitors.solvency import AccountableSolvencySnapshot
from monitors.yield_distribution import YieldDistributionSnapshot
from commands.status import build_status_message
from app.status_cache import StatusCache


def test_status_uses_compact_metric_labels(monkeypatch) -> None:
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

    async def fake_fetch_curve_pool_snapshot_async(web3, *, pool):
        if pool.name == "apxUSD-USDC":
            return CurvePoolSnapshot(
                name=pool.name,
                balances={"apxUSD": 12_490_000.0, "USDC": 12_570_000.0},
                virtual_price=1.000286,
                apxusd_usdc_price=1.0,
            )
        return CurvePoolSnapshot(
            name=pool.name,
            balances={"apyUSD": 2_550_000.0, "apxUSD": 3_430_000.0},
            virtual_price=1.005840,
            apxusd_usdc_price=None,
            apyusd_apxusd_price=1.3552,
            apyusd_price_apxusd=1.3569,
            total_value_apxusd=6_890_000.0,
            value_adjusted_imbalance=0.0047,
        )

    async def fake_fetch_commit_token_snapshot_async(web3, *, token):
        if token.name == "apxUSD Commit":
            return CommitTokenSnapshot(
                name=token.name,
                asset=token.asset,
                total_assets=5_730_000.0,
                total_supply=5_730_000.0,
                supply_cap=100_000_000.0,
                supply_cap_remaining=94_270_000.0,
                unlocking_delay_seconds=14 * 24 * 60 * 60,
            )
        return CommitTokenSnapshot(
            name=token.name,
            asset=token.asset,
            total_assets=11_080.0 if "apxUSD-USDC" in token.name else 12_030.0,
            total_supply=11_080.0 if "apxUSD-USDC" in token.name else 12_030.0,
            supply_cap=50_000_000.0,
            supply_cap_remaining=49_988_920.0,
            unlocking_delay_seconds=14 * 24 * 60 * 60,
        )

    async def fake_fetch_yield_distribution_snapshot_async(*args, **kwargs):
        return YieldDistributionSnapshot(
            annualized_yield=9_390_000.0,
            apy=0.1193,
            vesting_address="vesting",
            vested_amount=1_200.0,
            unvested_amount=518_400.0,
            vesting_period_remaining_seconds=int(20.16 * 24 * 60 * 60),
        )

    monkeypatch.setattr("commands.status.fetch_strc_price", fake_fetch_strc_price)
    monkeypatch.setattr("commands.status.fetch_pendle_market", fake_fetch_pendle_market)
    monkeypatch.setattr("commands.status.fetch_peg_price", fake_fetch_peg_price)
    monkeypatch.setattr("commands.status.fetch_total_supply_async", fake_fetch_total_supply_async)
    monkeypatch.setattr("commands.status.fetch_total_assets_async", fake_fetch_total_assets_async)
    monkeypatch.setattr("commands.status.fetch_price_apxusd_async", fake_fetch_price_apxusd_async)
    monkeypatch.setattr("commands.status.fetch_solvency_snapshot", fake_fetch_solvency_snapshot)
    monkeypatch.setattr("commands.status.fetch_curve_pool_snapshot_async", fake_fetch_curve_pool_snapshot_async)
    monkeypatch.setattr("commands.status.fetch_commit_token_snapshot_async", fake_fetch_commit_token_snapshot_async)
    monkeypatch.setattr("commands.status.fetch_yield_distribution_snapshot_async", fake_fetch_yield_distribution_snapshot_async)

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
    assert "✅ 全部正常" in message
    assert "🛡 Core" in message
    assert "PoR 100.78% | apxUSD $1.0000 | supply 194.99M" in message
    assert "apyUSD 1.3569 apxUSD | assets 72.33M | shares 53.94M" in message
    assert "📈 Pendle" in message
    assert "apxUSD  liq $1.00M | APY 8.00% | PT $0.9600" in message
    assert "apyUSD  liq $1.00M | APY 8.00% | PT $0.9600" in message
    assert "🌊 Curve" in message
    assert "apxUSD-USDC  depth $25.06M | price $1.0000 | vp 1.000286" in message
    assert "apyUSD-apxUSD  value 6.89M | price 1.3552/1.3569 | imb 0.47% | vp 1.005840" in message
    assert "🌾 Yield / Commit" in message
    assert "APY 11.93% | unvested 518.40K | vesting 20.16d" in message
    assert "Commit  apxUSD 5.73M (cap 5.7%) | LP 11.08K / 12.03K" in message
    assert "🌐 Macro / Security" in message
    assert "shares 53.94M" in message
    assert "STRC $101.00 | SATA $101.00" in message
    assert "mint backing normal | security events normal" in message
    assert "供应 (share totalSupply)" not in message
    assert "预警 1m/30m" not in message
    assert "或 ±2.00M" not in message
    assert "预警 &lt;" not in message
    assert "price              " not in message
    assert "TVL" not in message
    assert "100.78%" in message
    assert "异常后60min保持红色" not in message


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

    async def fake_unavailable_fetch(*args, **kwargs):
        raise RuntimeError("not available in status unit test")

    monkeypatch.setattr("commands.status.fetch_strc_price", fake_fetch_strc_price)
    monkeypatch.setattr("commands.status.fetch_pendle_market", fake_fetch_pendle_market)
    monkeypatch.setattr("commands.status.fetch_peg_price", fake_fetch_peg_price)
    monkeypatch.setattr("commands.status.fetch_total_supply_async", fake_fetch_total_supply_async)
    monkeypatch.setattr("commands.status.fetch_total_assets_async", fake_fetch_total_assets_async)
    monkeypatch.setattr("commands.status.fetch_price_apxusd_async", fake_fetch_price_apxusd_async)
    monkeypatch.setattr("commands.status.fetch_solvency_snapshot", fake_fetch_solvency_snapshot)
    monkeypatch.setattr("commands.status.fetch_curve_pool_snapshot_async", fake_unavailable_fetch)
    monkeypatch.setattr("commands.status.fetch_commit_token_snapshot_async", fake_unavailable_fetch)
    monkeypatch.setattr("commands.status.fetch_yield_distribution_snapshot_async", fake_unavailable_fetch)
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
    assert "⚠️ 存在异常告警" in message
    assert "security events active alert" in message


def test_status_uses_cache_without_live_fetches(monkeypatch) -> None:
    settings = load_app_config()
    env = EnvConfig(
        finnhub_api_key="key",
        telegram_bot_token="token",
        telegram_chat_id="chat",
        eth_rpc_url="rpc",
    )
    now = datetime(2026, 4, 26, 9, 20, 8, tzinfo=timezone.utc)
    cache = StatusCache()
    cache.set("strc:price", 101.0, now)
    cache.set(
        "pendle:apxUSD",
        PendleMarketSnapshot(
            name="apxUSD",
            liquidity=1_000_000.0,
            implied_apy=0.08,
            pt_price=0.96,
        ),
        now,
    )
    cache.set(
        "pendle:apyUSD",
        PendleMarketSnapshot(
            name="apyUSD",
            liquidity=2_000_000.0,
            implied_apy=0.09,
            pt_price=0.97,
        ),
        now,
    )
    cache.set(
        "solvency:accountable",
        AccountableSolvencySnapshot(
            collateralization=1.007765,
            total_reserves=201_414_546.13,
            total_supply=199_862_614.0,
            net=1_551_932.13,
            timestamp=now,
            verifiability="100",
            interval="live",
        ),
        now,
    )
    cache.set("peg:apxUSD", 1.0, now)
    cache.set("supply:apxUSD", 194_987_002.0, now)
    cache.set("supply:apyUSD", 53_939_627.60, now)
    cache.set("total_assets:apyUSD", 72_328_062.10, now)
    cache.set("apyusd_price_apxusd", 1.3569, now)

    async def fail_fetch(*args, **kwargs):
        raise AssertionError("status should use cached values")

    monkeypatch.setattr("commands.status.fetch_strc_price", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_pendle_market", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_peg_price", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_total_supply_async", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_total_assets_async", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_price_apxusd_async", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_solvency_snapshot", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_curve_pool_snapshot_async", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_commit_token_snapshot_async", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_yield_distribution_snapshot_async", fail_fetch)

    message, parse_mode = asyncio.run(
        build_status_message(
            session=object(),
            web3=object(),
            settings=settings,
            env=env,
            history=RollingMetricHistory(),
            engine=AlertEngine(cooldown=timedelta(minutes=5)),
            status_cache=cache,
        )
    )

    assert parse_mode == "HTML"
    assert "STRC $101.00" in message
    assert "liq $1.00M | APY 8.00% | PT $0.9600" in message
    assert "shares 53.94M" in message


def test_status_cache_miss_does_not_fall_back_to_live_fetch(monkeypatch) -> None:
    settings = load_app_config()
    env = EnvConfig(
        finnhub_api_key="key",
        telegram_bot_token="token",
        telegram_chat_id="chat",
        eth_rpc_url="rpc",
    )

    async def fail_fetch(*args, **kwargs):
        raise AssertionError("status should not live fetch when cache is provided")

    monkeypatch.setattr("commands.status.fetch_strc_price", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_curve_pool_snapshot_async", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_commit_token_snapshot_async", fail_fetch)
    monkeypatch.setattr("commands.status.fetch_yield_distribution_snapshot_async", fail_fetch)

    message, parse_mode = asyncio.run(
        build_status_message(
            session=object(),
            web3=object(),
            settings=settings,
            env=env,
            history=RollingMetricHistory(),
            engine=AlertEngine(cooldown=timedelta(minutes=5)),
            status_cache=StatusCache(),
        )
    )

    assert parse_mode == "HTML"
    assert "STRC ERROR - No cached status value yet: strc:price" in message
