from __future__ import annotations

import asyncio
from datetime import datetime

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from app.history import RollingMetricHistory
from monitors.change import evaluate_dual_change


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
    absolute_change_threshold: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    key = f"supply:{token_name}"
    latest_change = history.latest_change(key, current=supply)
    window_change = history.window_change(
        key, current=supply, now=now, window_minutes=window_minutes
    )
    history.record(key, supply, now)
    if latest_change is None:
        return None
    check = evaluate_dual_change(
        latest_change=latest_change,
        window_change=window_change,
        pct_threshold=threshold_pct,
        absolute_threshold=absolute_change_threshold,
        window_label=f"{window_minutes}m",
    )
    body = (
        f"Current supply: {supply:,.2f}\n"
        + "\n".join(check.lines)
    )
    return engine.evaluate(
        metric_key=key,
        breached=check.breached,
        alert_title=f"{token_name} Supply Change",
        alert_body=body,
        recovery_title=f"{token_name} Supply Normal",
        recovery_body=body,
        now=now,
    )
