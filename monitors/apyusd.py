from __future__ import annotations

import asyncio
from datetime import datetime

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from app.history import RollingMetricHistory
from monitors.change import evaluate_dual_change, exceeds_threshold


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
    absolute_change_threshold: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    key = f"total_assets:{token_name}"
    latest_change = history.latest_change(key, current=total_assets)
    window_change = history.window_change(
        key, current=total_assets, now=now, window_minutes=window_minutes
    )
    history.record(key, total_assets, now)
    if latest_change is None:
        return None
    check = evaluate_dual_change(
        latest_change=latest_change,
        window_change=window_change,
        pct_threshold=threshold_pct,
        absolute_threshold=absolute_change_threshold,
        absolute_unit="apxUSD",
        window_label=f"{window_minutes}m",
    )
    body = (
        f"Current totalAssets: {total_assets:,.2f} apxUSD\n"
        + "\n".join(check.lines)
    )
    return engine.evaluate(
        metric_key=key,
        breached=check.breached,
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
    latest_change = history.latest_change(key, current=price_apxusd)
    window_change = history.window_change(
        key, current=price_apxusd, now=now, window_minutes=window_minutes
    )
    history.record(key, price_apxusd, now)
    if latest_change is None:
        return None
    lines = [f"1m change: {latest_change.percent:+.2%}"]
    breached = exceeds_threshold(latest_change.percent, threshold_pct)
    if window_change is None:
        lines.append(f"{window_minutes}m change: N/A")
    else:
        lines.append(f"{window_minutes}m change: {window_change.percent:+.2%}")
        breached = breached or exceeds_threshold(window_change.percent, threshold_pct)
    body = f"Current priceAPXUSD: {price_apxusd:.4f} apxUSD\n" + "\n".join(lines)
    return engine.evaluate(
        metric_key=key,
        breached=breached,
        alert_title="apyUSD priceAPXUSD Change",
        alert_body=body,
        recovery_title="apyUSD priceAPXUSD Normal",
        recovery_body=body,
        now=now,
    )


def evaluate_supply_asset_backing(
    *,
    token_name: str,
    previous_supply: float,
    current_supply: float,
    previous_total_assets: float,
    current_total_assets: float,
    price_apxusd: float,
    min_supply_increase: float,
    min_backing_ratio: float,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    supply_delta = current_supply - previous_supply
    if supply_delta <= min_supply_increase:
        return None
    asset_delta = current_total_assets - previous_total_assets
    required_asset_delta = supply_delta * price_apxusd
    if required_asset_delta <= 0:
        return None
    backing_ratio = asset_delta / required_asset_delta
    breached = backing_ratio < min_backing_ratio
    body = (
        f"Share supply increase: {supply_delta:,.2f} {token_name}\n"
        f"Required asset increase: {required_asset_delta:,.2f} apxUSD\n"
        f"Actual asset increase: {asset_delta:,.2f} apxUSD\n"
        f"Backing ratio: {backing_ratio:.2%}\n"
        f"Minimum backing ratio: {min_backing_ratio:.2%}"
    )
    return engine.evaluate(
        metric_key=f"mint_backing:{token_name}",
        breached=breached,
        alert_title=f"{token_name} Mint Backing Mismatch",
        alert_body=body,
        recovery_title=f"{token_name} Mint Backing Normal",
        recovery_body=body,
        now=now,
    )
