from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

from aiohttp import ClientSession
from web3 import Web3

from alert.engine import AlertEngine
from config import AppConfig, EnvConfig
from errors import safe_error_message
from health import HealthTracker
from history import RollingMetricHistory
from monitors.peg import fetch_peg_price
from monitors.pendle import fetch_pendle_market
from monitors.strc_price import fetch_strc_price
from monitors.supply import fetch_total_supply_async
from monitors.apyusd import fetch_price_apxusd_async, fetch_total_assets_async


def _html_error(error: Exception) -> str:
    return escape(safe_error_message(error))


def _display_width(s: str) -> int:
    return sum(2 if ord(c) > 0x7F else 1 for c in s)


def _rpad(s: str, width: int) -> str:
    return s + " " * max(1, width - _display_width(s))


_LABEL_COL = 18


async def build_status_message(
    *,
    session: ClientSession,
    web3: Web3,
    settings: AppConfig,
    env: EnvConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    active = set(engine.active_alerts())

    section_data: list[tuple[str, list[str], list[str]]] = []

    # ── 🌐 宏观风险 ──
    lines: list[str] = []
    keys: list[str] = []
    try:
        strc_price = await fetch_strc_price(session, api_key=env.finnhub_api_key, symbol=settings.finnhub.symbol)
        lines.append(f"  STRC  <b>${strc_price:.2f}</b>  预警 &lt;${settings.finnhub.threshold_price:.2f}")
    except Exception as e:
        lines.append(f"  STRC  ERROR - {_html_error(e)}")
    keys.append("strc:price")
    section_data.append(("🌐 宏观风险", lines, keys))

    # ── 📈 Pendle 市场 ──
    lines = []
    keys = []
    for market in settings.pendle.markets:
        try:
            snap = await fetch_pendle_market(session, name=market.name, address=market.address)
            lines.append(f"  <b>{market.name}</b>")
            lines.append(f"    流动性  <b>${snap.liquidity/1e6:.2f}M</b>  预警 ↓{settings.pendle.liquidity_drop_pct:.0%}")
            lines.append(f"    APY  <b>{snap.implied_apy:.2%}</b>  预警 ±{settings.pendle.apy_change_pct:.0%}")
            lines.append(f"    PT价格  <b>${snap.pt_price:.4f}</b>  预警 ±{settings.pendle.pt_price_change_pct:.0%}")
        except Exception as e:
            lines.append(f"  <b>{market.name}</b>  ERROR - {_html_error(e)}")
        keys.extend([
            f"pendle_liquidity:{market.name}",
            f"pendle_apy:{market.name}",
            f"pendle_pt_price:{market.name}",
        ])
    section_data.append(("📈 Pendle 市场", lines, keys))

    # ── 🔐 协议安全 ──
    lines = []
    keys = []

    # apxUSD metrics
    lines.append("  <b>apxUSD</b>")
    try:
        peg_price = await fetch_peg_price(session, address=settings.peg.token.address)
        lines.append(f"    {_rpad('价格', _LABEL_COL)} <b>${peg_price:.4f}</b>  预警 偏离&gt;{settings.peg.threshold_pct:.2%}")
    except Exception as e:
        lines.append(f"    价格  ERROR - {_html_error(e)}")
    keys.append(f"peg:{settings.peg.token.name}")

    for token in settings.supply.tokens:
        if token.name == "apyUSD":
            continue
        try:
            supply = await fetch_total_supply_async(web3, address=token.address)
            lines.append(
                f"    {_rpad('供应', _LABEL_COL)} <b>{supply/1e6:.2f}M</b>  "
                f"预警 1m/30m ±{settings.supply.threshold_pct:.0%} "
                f"或 ±{token.absolute_change_threshold/1e6:.2f}M"
            )
        except Exception as e:
            lines.append(f"    供应  ERROR - {_html_error(e)}")
        keys.append(f"supply:{token.name}")

    # apyUSD metrics
    lines.append("  <b>apyUSD</b>")
    for token in settings.supply.tokens:
        if token.name != "apyUSD":
            continue
        try:
            supply = await fetch_total_supply_async(web3, address=token.address)
            lines.append(
                f"    {_rpad('供应 (share totalSupply)', _LABEL_COL)} <b>{supply/1e6:.2f}M</b>  "
                f"预警 1m/30m ±{settings.supply.threshold_pct:.0%} "
                f"或 ±{token.absolute_change_threshold/1e6:.2f}M"
            )
        except Exception as e:
            lines.append(f"    供应  ERROR - {_html_error(e)}")
        keys.append(f"supply:{token.name}")

    try:
        total_assets = await fetch_total_assets_async(
            web3, address=settings.apyusd.token.address
        )
        lines.append(
            f"    {_rpad('totalAssets', _LABEL_COL)} <b>{total_assets/1e6:.2f}M apxUSD</b>  "
            f"预警 1m/30m ±{settings.apyusd.total_assets_change_pct:.0%} "
            f"或 ±{settings.apyusd.total_assets_absolute_change_threshold/1e6:.2f}M"
        )
    except Exception as e:
        lines.append(f"    totalAssets  ERROR - {_html_error(e)}")
    keys.append(f"total_assets:{settings.apyusd.token.name}")

    try:
        price_apxusd = await fetch_price_apxusd_async(
            web3, address=settings.apyusd.token.address
        )
        lines.append(
            f"    {_rpad('priceAPXUSD', _LABEL_COL)} <b>{price_apxusd:.4f} apxUSD</b>  "
            f"预警 1m/30m ±{settings.apyusd.price_apxusd_change_pct:.0%}"
        )
    except Exception as e:
        lines.append(f"    priceAPXUSD  ERROR - {_html_error(e)}")
    keys.append("apyusd_price_apxusd")

    lines.append(
        f"    {_rpad('mint backing', _LABEL_COL)} 预警 新增share&gt;"
        f"{settings.security.apyusd_min_supply_increase/1e6:.2f}M 且背书&lt;"
        f"{settings.security.apyusd_min_backing_ratio:.0%}"
    )
    keys.append(f"mint_backing:{settings.apyusd.token.name}")

    lines.append(
        f"    {_rpad('链上安全事件', _LABEL_COL)} 预警 大额mint/burn、权限、升级、暂停事件"
    )
    keys.append("security_events")

    section_data.append(("🔐 协议安全", lines, keys))

    # ── 组装 ──
    now_str = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y/%m/%d %H:%M:%S")
    result = [f"📊 <b>APYX Monitor</b>  {now_str}", ""]
    has_alert = False

    for title, items, sec_keys in section_data:
        section_has_alert = any(k in active for k in sec_keys)
        if section_has_alert:
            has_alert = True
        icon = "🔴" if section_has_alert else "🟢"
        result.append(f"{icon} {title}")
        result.extend(items)
        result.append("")

    result.append("────────────────────────")
    if has_alert:
        result.append("⚠️ 存在异常告警")
    else:
        result.append("✅ 全部正常")

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
