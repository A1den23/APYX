from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent


DEFILLAMA_PRICE_URL = "https://coins.llama.fi/prices/current"


def coin_id(address: str) -> str:
    return f"ethereum:{address}"


async def fetch_peg_price(session: ClientSession, *, address: str) -> float:
    key = coin_id(address)
    async with session.get(f"{DEFILLAMA_PRICE_URL}/{key}") as response:
        response.raise_for_status()
        payload = await response.json()
    return parse_defillama_price(payload, key)


def parse_defillama_price(payload: dict, key: str) -> float:
    return float(payload["coins"][key]["price"])


def evaluate_peg_price(
    *,
    token_name: str,
    price: float,
    threshold_pct: float,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    deviation = price - 1.0
    decimal_deviation = Decimal(str(price)) - Decimal("1.0")
    breached = abs(decimal_deviation) > Decimal(str(threshold_pct))
    body = f"价格: ${price:.4f}\n偏离: {deviation:+.2%}"
    return engine.evaluate(
        metric_key=f"peg:{token_name}",
        breached=breached,
        alert_title=f"{token_name} 脱锚预警",
        alert_body=body,
        recovery_title=f"{token_name} 脱锚恢复正常",
        recovery_body=body,
        now=now,
    )
