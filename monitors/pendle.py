from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent
from app.history import RollingMetricHistory


@dataclass(frozen=True)
class PendleMarketSnapshot:
    name: str
    liquidity: float
    implied_apy: float
    pt_price: float


PENDLE_MARKET_URL = "https://api-v2.pendle.finance/core/v1/1/markets"


async def fetch_pendle_market(session: ClientSession, *, name: str, address: str) -> PendleMarketSnapshot:
    async with session.get(f"{PENDLE_MARKET_URL}/{address}") as response:
        response.raise_for_status()
        payload = await response.json()
    return parse_pendle_market(name, payload)


def parse_pendle_market(name: str, payload: dict) -> PendleMarketSnapshot:
    return PendleMarketSnapshot(
        name=name,
        liquidity=float(payload["liquidity"]["usd"]),
        implied_apy=float(payload["impliedApy"]),
        pt_price=float(payload["pt"]["price"]["usd"]),
    )


def evaluate_pendle_market(
    *,
    snapshot: PendleMarketSnapshot,
    liquidity_drop_pct: float,
    apy_change_pct: float,
    pt_price_change_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    checks = [
        (
            "pendle_liquidity",
            snapshot.liquidity,
            liquidity_drop_pct,
            lambda pct: pct < -liquidity_drop_pct,
            f"Pendle {snapshot.name} 流动性下降",
            f"Pendle {snapshot.name} 流动性恢复",
            "当前流动性",
            "${:,.2f}",
        ),
        (
            "pendle_apy",
            snapshot.implied_apy,
            apy_change_pct,
            lambda pct: abs(pct) > apy_change_pct,
            f"Pendle {snapshot.name} PT APY 变化异常",
            f"Pendle {snapshot.name} PT APY 恢复正常",
            "当前 APY",
            "{:.2%}",
        ),
        (
            "pendle_pt_price",
            snapshot.pt_price,
            pt_price_change_pct,
            lambda pct: abs(pct) > pt_price_change_pct,
            f"Pendle {snapshot.name} PT 价格变化异常",
            f"Pendle {snapshot.name} PT 价格恢复正常",
            "当前 PT 价格",
            "${:.4f}",
        ),
    ]
    for metric, value, _threshold, predicate, alert_title, recovery_title, label, value_format in checks:
        key = f"{metric}:{snapshot.name}"
        latest_change = history.latest_change(key, current=value)
        window_change = history.window_change(
            key,
            current=value,
            now=now,
            window_minutes=window_minutes,
        )
        history.record(key, value, now)
        if latest_change is None:
            continue
        lines = [f"1m 变化: {latest_change.percent:+.2%}"]
        breached = predicate(latest_change.percent)
        if window_change is None:
            lines.append(f"{window_minutes}m 变化: 暂无")
        else:
            lines.append(f"{window_minutes}m 变化: {window_change.percent:+.2%}")
            breached = breached or predicate(window_change.percent)
        body = f"{label}: {value_format.format(value)}\n" + "\n".join(lines)
        event = engine.evaluate(
            metric_key=key,
            breached=breached,
            alert_title=alert_title,
            alert_body=body,
            recovery_title=recovery_title,
            recovery_body=body,
            now=now,
        )
        if event is not None:
            events.append(event)
    return events
