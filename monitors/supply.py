from __future__ import annotations

import asyncio
from datetime import datetime
from math import isclose

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from history import RollingMetricHistory


ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
]


def _exceeds_threshold(value: float, threshold: float) -> bool:
    magnitude = abs(value)
    return magnitude > threshold and not isclose(
        magnitude, threshold, rel_tol=0.0, abs_tol=1e-12
    )


def fetch_total_supply(web3: Web3, *, address: str) -> float:
    contract = web3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC20_ABI)
    raw_supply = contract.functions.totalSupply().call()
    decimals = contract.functions.decimals().call()
    return float(raw_supply) / float(10**decimals)


async def fetch_total_supply_async(web3: Web3, *, address: str) -> float:
    return await asyncio.to_thread(fetch_total_supply, web3, address=address)


def evaluate_supply(
    *,
    token_name: str,
    supply: float,
    threshold_pct: float,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    key = f"supply:{token_name}"
    change = history.latest_change(key, current=supply)
    history.record(key, supply, now)
    if change is None:
        return None
    body = f"Current supply: {supply:,.2f}\nChange: {change.percent:+.2%}"
    return engine.evaluate(
        metric_key=key,
        breached=_exceeds_threshold(change.percent, threshold_pct),
        alert_title=f"{token_name} Supply Change",
        alert_body=body,
        recovery_title=f"{token_name} Supply Normal",
        recovery_body=body,
        now=now,
    )
