from __future__ import annotations

from datetime import datetime
from math import isclose

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent
from history import RollingMetricHistory

STABLECOIN_URL = "https://stablecoins.llama.fi/stablecoins"


async def fetch_tvl(session: ClientSession, *, stablecoin_id: str) -> float:
    async with session.get(STABLECOIN_URL) as response:
        response.raise_for_status()
        payload = await response.json()
    return parse_tvl(payload, stablecoin_id)


def parse_tvl(payload: dict, stablecoin_id: str) -> float:
    for asset in payload["peggedAssets"]:
        if str(asset["id"]) == str(stablecoin_id):
            return float(asset["circulating"]["peggedUSD"])
    raise ValueError(f"Stablecoin {stablecoin_id} not found")


def _exceeds_threshold(value: float, threshold: float) -> bool:
    magnitude = abs(value)
    return magnitude > threshold and not isclose(
        magnitude, threshold, rel_tol=0.0, abs_tol=1e-12
    )


def evaluate_tvl(
    *,
    token_name: str,
    tvl: float,
    threshold_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    key = f"tvl:{token_name}"
    change = history.window_change(key, current=tvl, now=now, window_minutes=window_minutes)
    history.record(key, tvl, now)
    if change is None:
        return None
    body = f"Current TVL: ${tvl:,.2f}\n1h change: {change.percent:+.2%}"
    return engine.evaluate(
        metric_key=key,
        breached=_exceeds_threshold(change.percent, threshold_pct),
        alert_title=f"{token_name} TVL Change",
        alert_body=body,
        recovery_title=f"{token_name} TVL Normal",
        recovery_body=body,
        now=now,
    )
