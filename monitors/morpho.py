from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import asyncio

from aiohttp import ClientSession
from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from app.config import MorphoMarketConfig
from app.history import RollingMetricHistory


MORPHO_GRAPHQL_URL = "https://blue-api.morpho.org/graphql"
MORPHO_MARKET_QUERY = """
query MorphoMarket($marketId: String!, $chainId: Int!) {
    marketById(marketId: $marketId, chainId: $chainId) {
    marketId
    oracle {
      address
    }
    loanAsset {
      symbol
      decimals
    }
    collateralAsset {
      symbol
      decimals
    }
    state {
      borrowApy
      borrowAssetsUsd
      supplyAssetsUsd
      utilization
    }
  }
}
"""

ORACLE_ABI = [
    {
        "inputs": [],
        "name": "price",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]


@dataclass(frozen=True)
class MorphoMarketSnapshot:
    name: str
    total_market_size_usd: float
    total_liquidity_usd: float
    borrow_rate: float
    utilization: float
    oracle_address: str
    loan_asset_symbol: str
    collateral_asset_symbol: str
    oracle_price: float | None = None


async def fetch_morpho_market(
    session: ClientSession,
    *,
    web3: Web3 | None = None,
    market: MorphoMarketConfig,
) -> MorphoMarketSnapshot:
    payload = {
        "query": MORPHO_MARKET_QUERY,
        "variables": {
            "marketId": market.market_id,
            "chainId": market.chain_id,
        },
    }
    async with session.post(MORPHO_GRAPHQL_URL, json=payload) as response:
        response.raise_for_status()
        data = await response.json()
    snapshot = parse_morpho_market(market.name, data)
    if web3 is None:
        return snapshot
    oracle_price = await fetch_oracle_price_async(
        web3,
        oracle_address=snapshot.oracle_address,
        collateral_decimals=int(data["data"]["marketById"]["collateralAsset"]["decimals"]),
        loan_decimals=int(data["data"]["marketById"]["loanAsset"]["decimals"]),
    )
    return MorphoMarketSnapshot(
        name=snapshot.name,
        total_market_size_usd=snapshot.total_market_size_usd,
        total_liquidity_usd=snapshot.total_liquidity_usd,
        borrow_rate=snapshot.borrow_rate,
        utilization=snapshot.utilization,
        oracle_address=snapshot.oracle_address,
        oracle_price=oracle_price,
        loan_asset_symbol=snapshot.loan_asset_symbol,
        collateral_asset_symbol=snapshot.collateral_asset_symbol,
    )


def fetch_oracle_price(
    web3: Web3,
    *,
    oracle_address: str,
    collateral_decimals: int,
    loan_decimals: int,
) -> float:
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(oracle_address),
        abi=ORACLE_ABI,
    )
    raw_price = int(contract.functions.price().call())
    scale = float(10 ** (36 + loan_decimals - collateral_decimals))
    return float(raw_price) / scale


async def fetch_oracle_price_async(
    web3: Web3,
    *,
    oracle_address: str,
    collateral_decimals: int,
    loan_decimals: int,
) -> float:
    return await asyncio.to_thread(
        fetch_oracle_price,
        web3,
        oracle_address=oracle_address,
        collateral_decimals=collateral_decimals,
        loan_decimals=loan_decimals,
    )


def parse_morpho_market(name: str, payload: dict) -> MorphoMarketSnapshot:
    if payload.get("errors"):
        message = payload["errors"][0].get("message", "Morpho API error")
        raise RuntimeError(message)
    market = payload["data"]["marketById"]
    state = market["state"]
    total_market_size_usd = float(state["supplyAssetsUsd"])
    borrowed_usd = float(state["borrowAssetsUsd"])
    return MorphoMarketSnapshot(
        name=name,
        total_market_size_usd=total_market_size_usd,
        total_liquidity_usd=max(total_market_size_usd - borrowed_usd, 0.0),
        borrow_rate=float(state["borrowApy"]),
        utilization=float(state["utilization"]),
        oracle_address=str(market["oracle"]["address"]),
        loan_asset_symbol=str(market["loanAsset"]["symbol"]),
        collateral_asset_symbol=str(market["collateralAsset"]["symbol"]),
    )


def evaluate_morpho_market(
    *,
    snapshot: MorphoMarketSnapshot,
    total_market_size_drop_pct: float,
    total_liquidity_drop_pct: float,
    borrow_rate_change_pct: float,
    oracle_price_change_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    checks = [
        (
            "morpho_total_market_size",
            snapshot.total_market_size_usd,
            lambda pct: pct < -total_market_size_drop_pct,
            f"Morpho {snapshot.name} Total Market Size 下降",
            f"Morpho {snapshot.name} Total Market Size 恢复",
            "当前 Total Market Size",
            "${:,.2f}",
        ),
        (
            "morpho_total_liquidity",
            snapshot.total_liquidity_usd,
            lambda pct: pct < -total_liquidity_drop_pct,
            f"Morpho {snapshot.name} Total Liquidity 下降",
            f"Morpho {snapshot.name} Total Liquidity 恢复",
            "当前 Total Liquidity",
            "${:,.2f}",
        ),
        (
            "morpho_borrow_rate",
            snapshot.borrow_rate,
            lambda pct: abs(pct) > borrow_rate_change_pct,
            f"Morpho {snapshot.name} borrow rate 变化异常",
            f"Morpho {snapshot.name} borrow rate 恢复正常",
            "当前 borrow rate",
            "{:.2%}",
        ),
    ]
    if snapshot.oracle_price is not None:
        checks.append(
            (
                "morpho_oracle_price",
                snapshot.oracle_price,
                lambda pct: abs(pct) > oracle_price_change_pct,
                f"Morpho {snapshot.name} oracle price 变化异常",
                f"Morpho {snapshot.name} oracle price 恢复正常",
                "当前 oracle price",
                "${:.4f}",
            )
        )
    for metric, value, predicate, alert_title, recovery_title, label, value_format in checks:
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
        body = (
            f"{label}: {value_format.format(value)}\n"
            + "\n".join(lines)
        )
        event = engine.evaluate(
            metric_key=key,
            breached=breached,
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
