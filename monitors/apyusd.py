from __future__ import annotations

import asyncio
from datetime import datetime
from math import isclose

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from history import RollingMetricHistory


ERC4626_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "totalAssets",
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
    {
        "constant": True,
        "inputs": [{"name": "shares", "type": "uint256"}],
        "name": "previewRedeem",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]


def fetch_total_assets(web3: Web3, *, address: str) -> float:
    contract = web3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC4626_ABI)
    raw_assets = contract.functions.totalAssets().call()
    decimals = contract.functions.decimals().call()
    return float(raw_assets) / float(10**decimals)


async def fetch_total_assets_async(web3: Web3, *, address: str) -> float:
    return await asyncio.to_thread(fetch_total_assets, web3, address=address)


def fetch_price_apxusd(web3: Web3, *, address: str) -> float:
    contract = web3.eth.contract(address=Web3.to_checksum_address(address), abi=ERC4626_ABI)
    decimals = contract.functions.decimals().call()
    one_share = 10**decimals
    raw_assets = contract.functions.previewRedeem(one_share).call()
    return float(raw_assets) / float(one_share)


async def fetch_price_apxusd_async(web3: Web3, *, address: str) -> float:
    return await asyncio.to_thread(fetch_price_apxusd, web3, address=address)


def evaluate_total_assets(
    *,
    token_name: str,
    total_assets: float,
    threshold_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    key = f"total_assets:{token_name}"
    change = history.window_change(
        key,
        current=total_assets,
        now=now,
        window_minutes=window_minutes,
    )
    history.record(key, total_assets, now)
    if change is None:
        return None
    body = f"Current totalAssets: {total_assets:,.2f} apxUSD\n1h change: {change.percent:+.2%}"
    return engine.evaluate(
        metric_key=key,
        breached=_exceeds_threshold(change.percent, threshold_pct),
        alert_title=f"{token_name} totalAssets Change",
        alert_body=body,
        recovery_title=f"{token_name} totalAssets Normal",
        recovery_body=body,
        now=now,
    )


def evaluate_price_apxusd(
    *,
    price_apxusd: float,
    threshold_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    key = "apyusd_price_apxusd"
    change = history.window_change(
        key,
        current=price_apxusd,
        now=now,
        window_minutes=window_minutes,
    )
    history.record(key, price_apxusd, now)
    if change is None:
        return None
    body = f"Current priceAPXUSD: {price_apxusd:.4f} apxUSD\n1h change: {change.percent:+.2%}"
    return engine.evaluate(
        metric_key=key,
        breached=_exceeds_threshold(change.percent, threshold_pct),
        alert_title="apyUSD priceAPXUSD Change",
        alert_body=body,
        recovery_title="apyUSD priceAPXUSD Normal",
        recovery_body=body,
        now=now,
    )


def _exceeds_threshold(value: float, threshold: float) -> bool:
    magnitude = abs(value)
    return magnitude > threshold and not isclose(
        magnitude, threshold, rel_tol=0.0, abs_tol=1e-12
    )
