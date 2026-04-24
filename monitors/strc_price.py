from __future__ import annotations

from datetime import datetime

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent


FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"


async def fetch_strc_price(session: ClientSession, *, api_key: str, symbol: str) -> float:
    async with session.get(FINNHUB_QUOTE_URL, params={"symbol": symbol, "token": api_key}) as response:
        response.raise_for_status()
        payload = await response.json()
    return float(payload["c"])


def evaluate_strc_price(*, price: float, threshold: float, engine: AlertEngine, now: datetime) -> AlertEvent | None:
    breached = price < threshold
    distance = max(100.0 - price, 0.0)
    drop_pct = distance / 100.0
    body = f"Current price: ${price:.2f}\nDrop from par: {drop_pct:.2%}\nDistance from par: ${distance:.2f}"
    recovery_body = f"Current price: ${price:.2f}\nDrop from par: {drop_pct:.2%}\nDistance from par: ${distance:.2f}"
    return engine.evaluate(
        metric_key="strc:price",
        breached=breached,
        alert_title="STRC Price Below Threshold",
        alert_body=body,
        recovery_title="STRC Price Recovered",
        recovery_body=recovery_body,
        now=now,
    )
