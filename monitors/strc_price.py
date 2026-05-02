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


def evaluate_strc_price(
    *,
    price: float,
    threshold: float,
    engine: AlertEngine,
    now: datetime,
    symbol: str = "STRC",
) -> AlertEvent | None:
    breached = price < threshold
    distance = max(100.0 - price, 0.0)
    drop_pct = distance / 100.0
    body = f"当前价格: ${price:.2f}\n相对面值跌幅: {drop_pct:.2%}\n距离面值: ${distance:.2f}"
    recovery_body = body
    return engine.evaluate(
        metric_key=f"tradfi:{symbol}",
        breached=breached,
        alert_title=f"{symbol} 价格跌破阈值",
        alert_body=body,
        recovery_title=f"{symbol} 价格恢复正常",
        recovery_body=recovery_body,
        now=now,
    )
