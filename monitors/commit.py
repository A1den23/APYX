from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from app.config import CommitTokenConfig
from app.history import RollingMetricHistory
from monitors.change import evaluate_dual_change


COMMIT_TOKEN_ABI = [
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
    {
        "constant": True,
        "inputs": [],
        "name": "supplyCap",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "supplyCapRemaining",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "unlockingDelay",
        "outputs": [{"name": "", "type": "uint48"}],
        "type": "function",
    },
]


@dataclass(frozen=True)
class CommitTokenSnapshot:
    name: str
    asset: str
    total_assets: float
    total_supply: float
    supply_cap: float
    supply_cap_remaining: float
    unlocking_delay_seconds: int


def fetch_commit_token_snapshot(
    web3: Web3,
    *,
    token: CommitTokenConfig,
) -> CommitTokenSnapshot:
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(token.address),
        abi=COMMIT_TOKEN_ABI,
    )
    decimals = int(contract.functions.decimals().call())
    scale = float(10**decimals)
    return CommitTokenSnapshot(
        name=token.name,
        asset=token.asset,
        total_assets=float(contract.functions.totalAssets().call()) / scale,
        total_supply=float(contract.functions.totalSupply().call()) / scale,
        supply_cap=float(contract.functions.supplyCap().call()) / scale,
        supply_cap_remaining=float(contract.functions.supplyCapRemaining().call())
        / scale,
        unlocking_delay_seconds=int(contract.functions.unlockingDelay().call()),
    )


async def fetch_commit_token_snapshot_async(
    web3: Web3,
    *,
    token: CommitTokenConfig,
) -> CommitTokenSnapshot:
    return await asyncio.to_thread(fetch_commit_token_snapshot, web3, token=token)


def evaluate_commit_token(
    *,
    snapshot: CommitTokenSnapshot,
    cap_usage_warning_pct: float,
    assets_change_pct: float,
    assets_absolute_change_threshold: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    cap_usage = (
        0.0 if snapshot.supply_cap <= 0 else snapshot.total_supply / snapshot.supply_cap
    )
    body = (
        f"当前锁仓: {snapshot.total_assets:,.2f} {snapshot.asset}\n"
        f"供应上限: {snapshot.supply_cap:,.2f}\n"
        f"剩余额度: {snapshot.supply_cap_remaining:,.2f}\n"
        f"cap 使用率: {cap_usage:.2%}"
    )
    event = engine.evaluate(
        metric_key=f"commit_cap_usage:{snapshot.name}",
        breached=cap_usage >= cap_usage_warning_pct,
        alert_title=f"{snapshot.name} cap 使用率过高",
        alert_body=body,
        recovery_title=f"{snapshot.name} cap 使用率恢复",
        recovery_body=body,
        now=now,
    )
    if event is not None:
        events.append(event)

    key = f"commit_assets:{snapshot.name}"
    latest_change = history.latest_change(key, current=snapshot.total_assets)
    window_change = history.window_change(
        key,
        current=snapshot.total_assets,
        now=now,
        window_minutes=window_minutes,
    )
    history.record(key, snapshot.total_assets, now)
    if latest_change is not None:
        check = evaluate_dual_change(
            latest_change=latest_change,
            window_change=window_change,
            pct_threshold=assets_change_pct,
            absolute_threshold=assets_absolute_change_threshold,
            absolute_unit=snapshot.asset,
            window_label=f"{window_minutes}m",
        )
        body = (
            f"当前锁仓资产: {snapshot.total_assets:,.2f} {snapshot.asset}\n"
            + "\n".join(check.lines)
        )
        event = engine.evaluate(
            metric_key=key,
            breached=check.breached,
            alert_title=f"{snapshot.name} 资产变化异常",
            alert_body=body,
            recovery_title=f"{snapshot.name} 资产恢复正常",
            recovery_body=body,
            now=now,
        )
        if event is not None:
            events.append(event)

    delay_key = f"commit_unlock_delay:{snapshot.name}"
    previous_delay = history.latest_sample(delay_key)
    history.record(delay_key, float(snapshot.unlocking_delay_seconds), now)
    if previous_delay is not None:
        body = (
            f"当前解锁延迟: {snapshot.unlocking_delay_seconds / 86400:.2f} 天\n"
            f"上一轮: {previous_delay.value / 86400:.2f} 天"
        )
        event = engine.evaluate(
            metric_key=delay_key,
            breached=previous_delay.value != snapshot.unlocking_delay_seconds,
            alert_title=f"{snapshot.name} 解锁延迟变化",
            alert_body=body,
            recovery_title=f"{snapshot.name} 解锁延迟稳定",
            recovery_body=body,
            now=now,
        )
        if event is not None:
            events.append(event)

    return events
