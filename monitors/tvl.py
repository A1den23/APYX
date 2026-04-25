from __future__ import annotations

from datetime import datetime
from math import isclose

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from config import NamedAddress
from history import RollingMetricHistory
from monitors.supply import fetch_total_supply_async


async def fetch_tvl_for_token(
    session: object, web3: Web3, token: NamedAddress
) -> float:
    return await fetch_total_supply_async(web3, address=token.address)


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
