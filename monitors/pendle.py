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
            f"Pendle {snapshot.name} Liquidity Drop",
            f"Pendle {snapshot.name} Liquidity Recovered",
            "Current liquidity",
            "${:,.2f}",
        ),
        (
            "pendle_apy",
            snapshot.implied_apy,
            apy_change_pct,
            lambda pct: abs(pct) > apy_change_pct,
            f"Pendle {snapshot.name} PT APY Change",
            f"Pendle {snapshot.name} PT APY Recovered",
            "Current APY",
            "{:.2%}",
        ),
        (
            "pendle_pt_price",
            snapshot.pt_price,
            pt_price_change_pct,
            lambda pct: abs(pct) > pt_price_change_pct,
            f"Pendle {snapshot.name} PT Price Change",
            f"Pendle {snapshot.name} PT Price Recovered",
            "Current PT price",
            "${:.4f}",
        ),
    ]
    for metric, value, _threshold, predicate, alert_title, recovery_title, label, value_format in checks:
        key = f"{metric}:{snapshot.name}"
        change = history.window_change(key, current=value, now=now, window_minutes=window_minutes)
        if change is None:
            history.record(key, value, now)
            continue
        body = f"{label}: {value_format.format(value)}\n{window_minutes}m change: {change.percent:+.2%}"
        event = engine.evaluate(
            metric_key=key,
            breached=predicate(change.percent),
            alert_title=alert_title,
            alert_body=body,
            recovery_title=recovery_title,
            recovery_body=body,
            now=now,
        )
        history.record(key, value, now)
        if event is not None:
            events.append(event)
    return events
