from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

from aiohttp import ClientSession
from web3 import Web3

from alert.engine import AlertEngine
from app.config import AppConfig, EnvConfig
from app.errors import safe_error_message
from .health import HealthTracker
from app.history import RollingMetricHistory
from monitors.peg import fetch_peg_price
from monitors.pendle import fetch_pendle_market
from monitors.strc_price import fetch_strc_price
from monitors.supply import fetch_total_supply_async
from monitors.apyusd import fetch_price_apxusd_async, fetch_total_assets_async
from monitors.commit import fetch_commit_token_snapshot_async
from monitors.curve import fetch_curve_pool_snapshot_async
from monitors.solvency import fetch_solvency_snapshot
from monitors.yield_distribution import fetch_yield_distribution_snapshot_async
from app.status_cache import StatusCache


def _html_error(error: Exception) -> str:
    return escape(safe_error_message(error))


def _cached_status_value(status_cache: StatusCache, key: str):
    cached = status_cache.get(key)
    if cached is None:
        raise RuntimeError(f"No cached status value yet: {key}")
    return cached.value


def _format_amount(value: float, suffix: str = "") -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        rendered = f"{value/1_000_000_000:.2f}B"
    elif abs_value >= 1_000_000:
        rendered = f"{value/1_000_000:.2f}M"
    elif abs_value >= 1_000:
        rendered = f"{value/1_000:.2f}K"
    else:
        rendered = f"{value:.2f}"
    return f"{rendered} {suffix}".rstrip()


async def build_status_message(
    *,
    session: ClientSession,
    web3: Web3,
    settings: AppConfig,
    env: EnvConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
    status_cache: StatusCache | None = None,
) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    active = set(engine.active_alerts())
    all_keys: list[str] = []

    # ── Macro ──
    macro_parts: list[str] = []
    for symbol in settings.finnhub.symbols:
        key = f"tradfi:{symbol.symbol}"
        cache_key = "strc:price" if symbol.symbol == settings.finnhub.symbol else key
        try:
            price = (
                _cached_status_value(status_cache, cache_key)
                if status_cache is not None
                else await fetch_strc_price(
                    session, api_key=env.finnhub_api_key, symbol=symbol.symbol
                )
            )
            macro_parts.append(f"{symbol.symbol} ${price:.2f}")
        except Exception as e:
            macro_parts.append(f"{symbol.symbol} ERROR - {_html_error(e)}")
        all_keys.append(key)
        if symbol.symbol == settings.finnhub.symbol:
            all_keys.append("strc:price")

    # ── Pendle ──
    pendle_lines: list[str] = []
    for market in settings.pendle.markets:
        try:
            cache_key = f"pendle:{market.name}"
            snap = (
                _cached_status_value(status_cache, cache_key)
                if status_cache is not None
                else await fetch_pendle_market(
                    session, name=market.name, address=market.address
                )
            )
            pendle_lines.append(
                f"{market.name}  "
                f"liq ${snap.liquidity/1e6:.2f}M | "
                f"APY {snap.implied_apy:.2%} | "
                f"PT ${snap.pt_price:.4f}"
            )
        except Exception as e:
            pendle_lines.append(f"{market.name}  ERROR - {_html_error(e)}")
        all_keys.extend([
            f"pendle_liquidity:{market.name}",
            f"pendle_apy:{market.name}",
            f"pendle_pt_price:{market.name}",
        ])

    # ── Curve ──
    curve_lines: list[str] = []
    for pool in settings.curve.pools:
        try:
            cache_key = f"curve:{pool.name}"
            snap = (
                _cached_status_value(status_cache, cache_key)
                if status_cache is not None
                else await fetch_curve_pool_snapshot_async(web3, pool=pool)
            )
            if snap.apxusd_usdc_price is not None:
                depth = sum(snap.balances.values())
                curve_lines.append(
                    f"{pool.name}  depth ${depth/1e6:.2f}M | "
                    f"price ${snap.apxusd_usdc_price:.4f} | "
                    f"vp {snap.virtual_price:.6f}"
                )
            elif snap.total_value_apxusd is not None:
                price_part = "n/a"
                if (
                    snap.apyusd_apxusd_price is not None
                    and snap.apyusd_price_apxusd is not None
                ):
                    deviation = (
                        snap.apyusd_apxusd_price / snap.apyusd_price_apxusd - 1.0
                    )
                    price_part = (
                        f"{snap.apyusd_apxusd_price:.4f}/"
                        f"{snap.apyusd_price_apxusd:.4f} "
                        f"({deviation:+.2%})"
                    )
                imbalance = (
                    f"{snap.value_adjusted_imbalance:.2%}"
                    if snap.value_adjusted_imbalance is not None
                    else "n/a"
                )
                curve_lines.append(
                    f"{pool.name}  value {snap.total_value_apxusd/1e6:.2f}M | "
                    f"price {price_part} | "
                    f"imb {imbalance} | "
                    f"vp {snap.virtual_price:.6f}"
                )
            else:
                curve_lines.append(f"{pool.name}  vp {snap.virtual_price:.6f}")
        except Exception as e:
            curve_lines.append(f"{pool.name}  ERROR - {_html_error(e)}")
        all_keys.extend(
            [
                *(
                    [f"curve_virtual_price:{pool.name}"]
                    if "virtual_price" in pool.metrics
                    else []
                ),
                *(
                    [f"curve_imbalance:{pool.name}"]
                    if "imbalance" in pool.metrics
                    else []
                ),
                *(
                    [f"curve_value_adjusted_imbalance:{pool.name}"]
                    if "value_adjusted_imbalance" in pool.metrics
                    else []
                ),
                *(
                    [f"curve_price:{pool.name}"]
                    if (
                        "apxusd_usdc_price" in pool.metrics
                        or "apyusd_apxusd_price" in pool.metrics
                    )
                    else []
                ),
                *(
                    [f"curve_total_value:{pool.name}"]
                    if "total_value" in pool.metrics
                    else []
                ),
                *[
                    f"curve_balance:{pool.name}:{coin.name}"
                    for coin in pool.coins
                    if "balances" in pool.metrics
                ],
            ]
        )

    # ── Commit ──
    commit_apx = "n/a"
    commit_lps: list[str] = []
    for token in settings.commit.tokens:
        try:
            cache_key = f"commit:{token.name}"
            snap = (
                _cached_status_value(status_cache, cache_key)
                if status_cache is not None
                else await fetch_commit_token_snapshot_async(web3, token=token)
            )
            cap_usage = (
                0.0 if snap.supply_cap <= 0 else snap.total_supply / snap.supply_cap
            )
            if token.name == "apxUSD Commit":
                commit_apx = (
                    f"{_format_amount(snap.total_assets)} (cap {cap_usage:.1%})"
                )
            else:
                commit_lps.append(_format_amount(snap.total_assets))
        except Exception as e:
            if token.name == "apxUSD Commit":
                commit_apx = f"ERROR - {_html_error(e)}"
            else:
                commit_lps.append(f"ERROR - {_html_error(e)}")
        all_keys.extend(
            [
                f"commit_cap_usage:{token.name}",
                f"commit_assets:{token.name}",
                f"commit_unlock_delay:{token.name}",
            ]
        )

    # ── Yield ──
    yield_line = "yield distribution n/a"
    if settings.yield_distribution.rate_view is not None:
        all_keys.extend([
            "yield_distribution:annualized_yield",
            "yield_distribution:apy",
            "yield_distribution:unvested",
        ])
        try:
            snap = (
                _cached_status_value(status_cache, "yield_distribution")
                if status_cache is not None
                else await fetch_yield_distribution_snapshot_async(
                    web3,
                    apyusd_address=settings.apyusd.token.address,
                    apxusd_address=settings.peg.token.address,
                    rate_view_address=settings.yield_distribution.rate_view.address,
                )
            )
            yield_line = (
                f"APY {snap.apy:.2%} | "
                f"unvested {_format_amount(snap.unvested_amount)} | "
                f"vesting {snap.vesting_period_remaining_seconds/86400:.2f}d"
            )
        except Exception as e:
            yield_line = f"yield distribution ERROR - {_html_error(e)}"

    # ── Core ──
    por_part = "PoR ERROR"
    updated_part = ""
    try:
        solvency = (
            _cached_status_value(status_cache, "solvency:accountable")
            if status_cache is not None
            else await fetch_solvency_snapshot(
                session, url=settings.solvency.accountable_url
            )
        )
        updated_part = solvency.timestamp.astimezone(
            timezone(timedelta(hours=8))
        ).strftime("%m/%d %H:%M")
        por_part = f"PoR {solvency.collateralization:.2%}"
    except Exception as e:
        por_part = f"PoR ERROR - {_html_error(e)}"
    all_keys.append("solvency:accountable")

    peg_part = "apxUSD price ERROR"
    try:
        peg_key = f"peg:{settings.peg.token.name}"
        peg_price = (
            _cached_status_value(status_cache, peg_key)
            if status_cache is not None
            else await fetch_peg_price(session, address=settings.peg.token.address)
        )
        peg_part = f"apxUSD ${peg_price:.4f}"
    except Exception as e:
        peg_part = f"apxUSD ERROR - {_html_error(e)}"
    all_keys.append(f"peg:{settings.peg.token.name}")

    apx_supply_part = "supply ERROR"
    apy_supply_part = "shares ERROR"
    for token in settings.supply.tokens:
        try:
            cache_key = f"supply:{token.name}"
            supply = (
                _cached_status_value(status_cache, cache_key)
                if status_cache is not None
                else await fetch_total_supply_async(web3, address=token.address)
            )
            if token.name == "apyUSD":
                apy_supply_part = f"shares {supply/1e6:.2f}M"
            else:
                apx_supply_part = f"supply {supply/1e6:.2f}M"
        except Exception as e:
            if token.name == "apyUSD":
                apy_supply_part = f"shares ERROR - {_html_error(e)}"
            else:
                apx_supply_part = f"supply ERROR - {_html_error(e)}"
        all_keys.append(f"supply:{token.name}")

    apy_assets_part = "assets ERROR"
    try:
        cache_key = f"total_assets:{settings.apyusd.token.name}"
        total_assets = (
            _cached_status_value(status_cache, cache_key)
            if status_cache is not None
            else await fetch_total_assets_async(
                web3, address=settings.apyusd.token.address
            )
        )
        apy_assets_part = f"assets {total_assets/1e6:.2f}M"
    except Exception as e:
        apy_assets_part = f"assets ERROR - {_html_error(e)}"
    all_keys.append(f"total_assets:{settings.apyusd.token.name}")

    apy_price_part = "apyUSD price ERROR"
    try:
        price_apxusd = (
            _cached_status_value(status_cache, "apyusd_price_apxusd")
            if status_cache is not None
            else await fetch_price_apxusd_async(
                web3, address=settings.apyusd.token.address
            )
        )
        apy_price_part = f"apyUSD {price_apxusd:.4f} apxUSD"
    except Exception as e:
        apy_price_part = f"apyUSD ERROR - {_html_error(e)}"
    all_keys.append("apyusd_price_apxusd")

    mint_backing_key = f"mint_backing:{settings.apyusd.token.name}"
    mint_backing_part = (
        f"mint backing {'active alert' if mint_backing_key in active else 'normal'}"
    )
    all_keys.append(mint_backing_key)

    security_events_key = "security_events"
    security_events_part = (
        f"security events {'active alert' if security_events_key in active else 'normal'}"
    )
    all_keys.append(security_events_key)

    # ── 组装 ──
    now_str = now.astimezone(timezone(timedelta(hours=8))).strftime("%m/%d %H:%M")
    has_alert = any(k in active for k in all_keys)
    result = [
        f"📊 APYX Monitor  {now_str}",
        "⚠️ 存在异常告警" if has_alert else "✅ 全部正常",
        "",
        "🛡 Core",
        f"{por_part} | {peg_part} | {apx_supply_part}",
        f"{apy_price_part} | {apy_assets_part} | {apy_supply_part}",
        "",
        "📈 Pendle",
        *pendle_lines,
    ]
    if curve_lines:
        result.extend(["", "🌊 Curve", *curve_lines])

    result.extend(
        [
            "",
            "🌾 Yield / Commit",
            yield_line,
            f"Commit  apxUSD {commit_apx} | LP {' / '.join(commit_lps) if commit_lps else 'n/a'}",
            "",
            "🌐 Macro / Security",
            " | ".join(macro_parts) if macro_parts else "macro n/a",
            f"{mint_backing_part} | {security_events_part}",
        ]
    )
    if updated_part:
        result.append(f"updated {updated_part}")

    if has_alert:
        result.append("")
        result.append("⚠️ 存在异常告警")

    return "\n".join(result), "HTML"


async def build_health_message(
    *,
    tracker: HealthTracker,
    engine: AlertEngine,
) -> str:
    now = datetime.now(timezone.utc)
    up = tracker.uptime
    days = up.days
    hours, rem = divmod(up.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    if days:
        uptime_str = f"{days}d {hours}h {minutes}m"
    elif hours:
        uptime_str = f"{hours}h {minutes}m {seconds}s"
    else:
        uptime_str = f"{minutes}m {seconds}s"

    snap = tracker.snapshot()
    monitor_count = sum(1 for m in snap.values() if m.interval_seconds > 0)
    total, ok, fail = tracker.total_runs()
    rate = f"{ok/total*100:.1f}%" if total else "N/A"

    lines = [
        f"🩺 APYX 健康自检  {now.astimezone(timezone(timedelta(hours=8))).strftime('%Y/%m/%d %H:%M:%S')}",
        "",
        "【Daemon】",
        f"✅ 运行中  uptime: {uptime_str}",
        f"监控器: {monitor_count} 启用",
        "",
        "【总运行】",
    ]

    if fail == 0:
        lines.append(f"🟢 总运行: {total}  成功 {ok}  失败 {fail}  ({rate})")
    else:
        lines.append(f"🔴 总运行: {total}  成功 {ok}  失败 {fail}  ({rate})")

    # 快照新鲜度
    lines.append("")
    now_utc = datetime.now(timezone.utc)
    stale_items: list[tuple[str, float, float]] = []
    fresh_items: list[tuple[str, float, float]] = []
    for name, m in sorted(snap.items()):
        if m.interval_seconds <= 0:
            continue
        if m.last_success_at:
            age_minutes = (now_utc - m.last_success_at).total_seconds() / 60
            interval_min = m.interval_seconds / 60
            if age_minutes > interval_min * 2:
                stale_items.append((name, age_minutes, interval_min))
            else:
                fresh_items.append((name, age_minutes, interval_min))
        else:
            stale_items.append((name, 999, m.interval_seconds / 60))

    if stale_items:
        lines.append("🔴 存在过期数据")
        for name, age, interval in stale_items:
            lines.append(f"  ❌ {name}  {age:.1f}min (间隔 {interval:.0f}min)")
    else:
        lines.append("🟢 全部新鲜")
        if fresh_items:
            oldest = max(fresh_items, key=lambda x: x[1])
            newest = min(fresh_items, key=lambda x: x[1])
            lines.append(f"  最老: {oldest[0]}  {oldest[1]:.1f}min (间隔 {oldest[2]:.0f}min)")
            lines.append(f"  最新: {newest[0]}  {newest[1]:.1f}min")

    # 错误分布
    errors = [(name, m.last_error) for name, m in snap.items() if m.last_error]
    lines.append("")
    if errors:
        lines.append("【最近错误】")
        for name, err in errors:
            lines.append(f"  ❌ {name}: {err}")
    else:
        lines.append("【过去错误】  无错误")

    # 告警
    active = engine.active_alerts()
    lines.append("")
    lines.append(f"【告警】  当前 {len(active)} 条活跃")

    return "\n".join(lines)
