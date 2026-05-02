from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from app.history import RollingMetricHistory
from monitors.change import exceeds_threshold


RATE_VIEW_ABI = [
    {
        "inputs": [],
        "name": "annualizedYield",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "apy",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "precision",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

APYUSD_LINK_ABI = [
    {
        "inputs": [],
        "name": "vesting",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]

VESTING_ABI = [
    {
        "inputs": [],
        "name": "vestedAmount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "unvestedAmount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "vestingPeriodRemaining",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
]

ERC20_DECIMALS_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    }
]


@dataclass(frozen=True)
class YieldDistributionSnapshot:
    annualized_yield: float
    apy: float
    vesting_address: str
    vested_amount: float
    unvested_amount: float
    vesting_period_remaining_seconds: int


def fetch_yield_distribution_snapshot(
    web3: Web3,
    *,
    apyusd_address: str,
    apxusd_address: str,
    rate_view_address: str,
) -> YieldDistributionSnapshot:
    rate_view = web3.eth.contract(
        address=Web3.to_checksum_address(rate_view_address),
        abi=RATE_VIEW_ABI,
    )
    apyusd = web3.eth.contract(
        address=Web3.to_checksum_address(apyusd_address),
        abi=APYUSD_LINK_ABI,
    )
    vesting_address = apyusd.functions.vesting().call()
    vesting = web3.eth.contract(
        address=Web3.to_checksum_address(vesting_address),
        abi=VESTING_ABI,
    )
    apxusd = web3.eth.contract(
        address=Web3.to_checksum_address(apxusd_address),
        abi=ERC20_DECIMALS_ABI,
    )
    scale = float(10 ** int(apxusd.functions.decimals().call()))
    precision = float(rate_view.functions.precision().call())
    return YieldDistributionSnapshot(
        annualized_yield=float(rate_view.functions.annualizedYield().call()) / scale,
        apy=float(rate_view.functions.apy().call()) / precision,
        vesting_address=str(vesting_address),
        vested_amount=float(vesting.functions.vestedAmount().call()) / scale,
        unvested_amount=float(vesting.functions.unvestedAmount().call()) / scale,
        vesting_period_remaining_seconds=int(
            vesting.functions.vestingPeriodRemaining().call()
        ),
    )


async def fetch_yield_distribution_snapshot_async(
    web3: Web3,
    *,
    apyusd_address: str,
    apxusd_address: str,
    rate_view_address: str,
) -> YieldDistributionSnapshot:
    return await asyncio.to_thread(
        fetch_yield_distribution_snapshot,
        web3,
        apyusd_address=apyusd_address,
        apxusd_address=apxusd_address,
        rate_view_address=rate_view_address,
    )


def evaluate_yield_distribution(
    *,
    snapshot: YieldDistributionSnapshot,
    apy_change_pct: float,
    annualized_yield_change_pct: float,
    unvested_change_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    metric_specs = [
        (
            "yield_distribution:annualized_yield",
            snapshot.annualized_yield,
            annualized_yield_change_pct,
            "apyUSD 年化收益资产量变化异常",
            "apyUSD 年化收益资产量恢复正常",
            "年化收益资产量",
            "{:,.2f} apxUSD/year",
        ),
        (
            "yield_distribution:apy",
            snapshot.apy,
            apy_change_pct,
            "apyUSD 收益 APY 变化异常",
            "apyUSD 收益 APY 恢复正常",
            "当前 APY",
            "{:.2%}",
        ),
        (
            "yield_distribution:unvested",
            snapshot.unvested_amount,
            unvested_change_pct,
            "apyUSD 未归属收益变化异常",
            "apyUSD 未归属收益恢复正常",
            "未归属收益",
            "{:,.2f} apxUSD",
        ),
    ]
    for key, value, threshold, alert_title, recovery_title, label, value_format in metric_specs:
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
        change = latest_change
        if window_change is not None and abs(window_change.percent) > abs(change.percent):
            change = window_change
        body = (
            f"{label}: {value_format.format(value)}\n"
            f"已归属收益: {snapshot.vested_amount:,.2f} apxUSD\n"
            f"vesting 剩余: {snapshot.vesting_period_remaining_seconds / 86400:.2f} 天\n"
            f"{window_minutes}m 变化: {change.percent:+.2%}"
        )
        event = engine.evaluate(
            metric_key=key,
            breached=exceeds_threshold(change.percent, threshold),
            alert_title=alert_title,
            alert_body=body,
            recovery_title=recovery_title,
            recovery_body=body,
            now=now,
        )
        if event is not None:
            events.append(event)
    return events
