from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from app.config import CurvePool
from app.history import MetricChange, RollingMetricHistory
from monitors.change import exceeds_threshold


CURVE_POOL_ABI = [
    {
        "inputs": [],
        "name": "get_balances",
        "outputs": [{"name": "", "type": "uint256[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "get_virtual_price",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "i", "type": "int128"},
            {"name": "j", "type": "int128"},
            {"name": "dx", "type": "uint256"},
        ],
        "name": "get_dy",
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
class CurvePoolSnapshot:
    name: str
    balances: dict[str, float]
    virtual_price: float
    apxusd_usdc_price: float | None
    apyusd_apxusd_price: float | None = None
    apyusd_price_apxusd: float | None = None
    total_value_apxusd: float | None = None
    value_adjusted_imbalance: float | None = None
    metrics: tuple[str, ...] = (
        "balances",
        "imbalance",
        "virtual_price",
        "apxusd_usdc_price",
    )
    price_deviation_pct: float | None = None
    total_value_drop_pct: float | None = None


def _erc20_decimals(web3: Web3, address: str) -> int:
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(address),
        abi=ERC20_DECIMALS_ABI,
    )
    return int(contract.functions.decimals().call())


def fetch_curve_pool_snapshot(web3: Web3, *, pool: CurvePool) -> CurvePoolSnapshot:
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(pool.address),
        abi=CURVE_POOL_ABI,
    )
    raw_balances = contract.functions.get_balances().call()
    balances: dict[str, float] = {}
    decimals_by_name: dict[str, int] = {}
    for coin, raw_balance in zip(pool.coins, raw_balances, strict=False):
        decimals = _erc20_decimals(web3, coin.address)
        decimals_by_name[coin.name] = decimals
        balances[coin.name] = float(raw_balance) / float(10**decimals)

    virtual_price = float(contract.functions.get_virtual_price().call()) / 1e18
    apxusd_usdc_price = _fetch_apxusd_usdc_price(
        contract,
        pool=pool,
        decimals_by_name=decimals_by_name,
    )
    apyusd_apxusd_price = _fetch_apyusd_apxusd_price(
        contract,
        pool=pool,
        decimals_by_name=decimals_by_name,
    )
    apyusd_price_apxusd = _fetch_apyusd_price_apxusd(web3, pool=pool)
    total_value_apxusd = _total_value_apxusd(
        balances=balances,
        apyusd_price_apxusd=apyusd_price_apxusd,
    )
    value_adjusted_imbalance = _value_adjusted_imbalance(
        balances=balances,
        apyusd_price_apxusd=apyusd_price_apxusd,
    )
    return CurvePoolSnapshot(
        name=pool.name,
        balances=balances,
        virtual_price=virtual_price,
        apxusd_usdc_price=apxusd_usdc_price,
        apyusd_apxusd_price=apyusd_apxusd_price,
        apyusd_price_apxusd=apyusd_price_apxusd,
        total_value_apxusd=total_value_apxusd,
        value_adjusted_imbalance=value_adjusted_imbalance,
        metrics=pool.metrics,
        price_deviation_pct=pool.price_deviation_pct,
        total_value_drop_pct=pool.total_value_drop_pct,
    )


async def fetch_curve_pool_snapshot_async(
    web3: Web3,
    *,
    pool: CurvePool,
) -> CurvePoolSnapshot:
    return await asyncio.to_thread(fetch_curve_pool_snapshot, web3, pool=pool)


def _fetch_apxusd_usdc_price(
    contract,
    *,
    pool: CurvePool,
    decimals_by_name: dict[str, int],
) -> float | None:
    names = [coin.name for coin in pool.coins]
    if "apxUSD" not in names or "USDC" not in names:
        return None
    apx_index = names.index("apxUSD")
    usdc_index = names.index("USDC")
    dx = 10 ** decimals_by_name["apxUSD"]
    raw_dy = contract.functions.get_dy(apx_index, usdc_index, dx).call()
    return float(raw_dy) / float(10 ** decimals_by_name["USDC"])


def _fetch_apyusd_apxusd_price(
    contract,
    *,
    pool: CurvePool,
    decimals_by_name: dict[str, int],
) -> float | None:
    names = [coin.name for coin in pool.coins]
    if "apyUSD" not in names or "apxUSD" not in names:
        return None
    apy_index = names.index("apyUSD")
    apx_index = names.index("apxUSD")
    dx = 10 ** decimals_by_name["apyUSD"]
    raw_dy = contract.functions.get_dy(apy_index, apx_index, dx).call()
    return float(raw_dy) / float(10 ** decimals_by_name["apxUSD"])


def _fetch_apyusd_price_apxusd(web3: Web3, *, pool: CurvePool) -> float | None:
    apyusd = next((coin for coin in pool.coins if coin.name == "apyUSD"), None)
    if apyusd is None:
        return None
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(apyusd.address),
        abi=[
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
        ],
    )
    decimals = int(contract.functions.decimals().call())
    one_share = 10**decimals
    return float(contract.functions.previewRedeem(one_share).call()) / float(one_share)


def _total_value_apxusd(
    *,
    balances: dict[str, float],
    apyusd_price_apxusd: float | None,
) -> float | None:
    if "apyUSD" not in balances or "apxUSD" not in balances:
        return None
    if apyusd_price_apxusd is None:
        return None
    return balances["apyUSD"] * apyusd_price_apxusd + balances["apxUSD"]


def _value_adjusted_imbalance(
    *,
    balances: dict[str, float],
    apyusd_price_apxusd: float | None,
) -> float | None:
    if "apyUSD" not in balances or "apxUSD" not in balances:
        return None
    if apyusd_price_apxusd is None:
        return None
    values = [
        balances["apyUSD"] * apyusd_price_apxusd,
        balances["apxUSD"],
    ]
    average = sum(values) / len(values)
    if average == 0:
        return 0.0
    return max(abs(value - average) / average for value in values)


def evaluate_curve_pool(
    *,
    snapshot: CurvePoolSnapshot,
    balance_drop_pct: float,
    imbalance_pct: float,
    virtual_price_change_pct: float,
    price_deviation_pct: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    metrics = set(snapshot.metrics)
    if "balances" in metrics:
        for coin_name, balance in snapshot.balances.items():
            key = f"curve_balance:{snapshot.name}:{coin_name}"
            latest_change = history.latest_change(key, current=balance)
            window_change = history.window_change(
                key, current=balance, now=now, window_minutes=window_minutes
            )
            history.record(key, balance, now)
            if latest_change is None:
                continue
            lines = _dual_window_change_lines(
                latest_change=latest_change,
                window_change=window_change,
                window_minutes=window_minutes,
            )
            body = (
                f"当前余额: {balance:,.2f} {coin_name}\n"
                + "\n".join(lines)
            )
            event = engine.evaluate(
                metric_key=key,
                breached=_drop_breached(
                    latest_change=latest_change,
                    window_change=window_change,
                    threshold=balance_drop_pct,
                ),
                alert_title=f"Curve {snapshot.name} {coin_name} 余额下降",
                alert_body=body,
                recovery_title=f"Curve {snapshot.name} {coin_name} 余额恢复",
                recovery_body=body,
                now=now,
            )
            if event is not None:
                events.append(event)

    if "total_value" in metrics and snapshot.total_value_apxusd is not None:
        events.extend(
            _evaluate_total_value(
                snapshot=snapshot,
                threshold=snapshot.total_value_drop_pct or balance_drop_pct,
                window_minutes=window_minutes,
                history=history,
                engine=engine,
                now=now,
            )
        )

    if "virtual_price" in metrics:
        events.extend(
            _evaluate_point_metric(
                key=f"curve_virtual_price:{snapshot.name}",
                value=snapshot.virtual_price,
                label="virtual price",
                threshold=virtual_price_change_pct,
                window_minutes=window_minutes,
                history=history,
                engine=engine,
                now=now,
                alert_title=f"Curve {snapshot.name} virtual price 变化异常",
                recovery_title=f"Curve {snapshot.name} virtual price 恢复",
            )
        )

    if "imbalance" in metrics:
        imbalance = _stable_pool_imbalance(snapshot.balances)
        body = f"当前不平衡度: {imbalance:.2%}\n阈值: {imbalance_pct:.2%}"
        event = engine.evaluate(
            metric_key=f"curve_imbalance:{snapshot.name}",
            breached=imbalance > imbalance_pct,
            alert_title=f"Curve {snapshot.name} 池子不平衡",
            alert_body=body,
            recovery_title=f"Curve {snapshot.name} 池子平衡恢复",
            recovery_body=body,
            now=now,
        )
        if event is not None:
            events.append(event)

    if (
        "value_adjusted_imbalance" in metrics
        and snapshot.value_adjusted_imbalance is not None
    ):
        body = (
            f"当前价值不平衡度: {snapshot.value_adjusted_imbalance:.2%}\n"
            f"阈值: {imbalance_pct:.2%}"
        )
        if snapshot.apyusd_price_apxusd is not None:
            body += f"\nVault priceAPXUSD: {snapshot.apyusd_price_apxusd:.6f}"
        event = engine.evaluate(
            metric_key=f"curve_value_adjusted_imbalance:{snapshot.name}",
            breached=snapshot.value_adjusted_imbalance > imbalance_pct,
            alert_title=f"Curve {snapshot.name} value-adjusted 池子不平衡",
            alert_body=body,
            recovery_title=f"Curve {snapshot.name} value-adjusted 池子平衡恢复",
            recovery_body=body,
            now=now,
        )
        if event is not None:
            events.append(event)

    threshold = snapshot.price_deviation_pct or price_deviation_pct
    if "apxusd_usdc_price" in metrics and snapshot.apxusd_usdc_price is not None:
        deviation = snapshot.apxusd_usdc_price - 1.0
        body = (
            f"apxUSD -> USDC 价格: ${snapshot.apxusd_usdc_price:.4f}\n"
            f"偏离: {deviation:+.2%}\n"
            f"阈值: {threshold:.2%}"
        )
        event = engine.evaluate(
            metric_key=f"curve_price:{snapshot.name}",
            breached=exceeds_threshold(deviation, threshold),
            alert_title=f"Curve {snapshot.name} 价格偏离",
            alert_body=body,
            recovery_title=f"Curve {snapshot.name} 价格恢复",
            recovery_body=body,
            now=now,
        )
        if event is not None:
            events.append(event)

    if (
        "apyusd_apxusd_price" in metrics
        and snapshot.apyusd_apxusd_price is not None
        and snapshot.apyusd_price_apxusd is not None
        and snapshot.apyusd_price_apxusd > 0
    ):
        deviation = snapshot.apyusd_apxusd_price / snapshot.apyusd_price_apxusd - 1.0
        body = (
            f"Curve apyUSD -> apxUSD 价格: {snapshot.apyusd_apxusd_price:.6f}\n"
            f"Vault priceAPXUSD: {snapshot.apyusd_price_apxusd:.6f}\n"
            f"偏离: {deviation:+.2%}\n"
            f"阈值: {threshold:.2%}"
        )
        event = engine.evaluate(
            metric_key=f"curve_apyusd_price:{snapshot.name}",
            breached=exceeds_threshold(deviation, threshold),
            alert_title=f"Curve {snapshot.name} apyUSD 价格偏离",
            alert_body=body,
            recovery_title=f"Curve {snapshot.name} apyUSD 价格恢复",
            recovery_body=body,
            now=now,
        )
        if event is not None:
            events.append(event)

    return events


def _evaluate_total_value(
    *,
    snapshot: CurvePoolSnapshot,
    threshold: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
) -> list[AlertEvent]:
    assert snapshot.total_value_apxusd is not None
    key = f"curve_total_value:{snapshot.name}"
    latest_change = history.latest_change(key, current=snapshot.total_value_apxusd)
    window_change = history.window_change(
        key,
        current=snapshot.total_value_apxusd,
        now=now,
        window_minutes=window_minutes,
    )
    history.record(key, snapshot.total_value_apxusd, now)
    if latest_change is None:
        return []
    lines = _dual_window_change_lines(
        latest_change=latest_change,
        window_change=window_change,
        window_minutes=window_minutes,
    )
    body = (
        f"当前总价值: {snapshot.total_value_apxusd:,.2f} apxUSD\n"
        + "\n".join(lines)
        + "\n"
        f"阈值: -{threshold:.2%}"
    )
    event = engine.evaluate(
        metric_key=key,
        breached=_drop_breached(
            latest_change=latest_change,
            window_change=window_change,
            threshold=threshold,
        ),
        alert_title=f"Curve {snapshot.name} 总价值下降",
        alert_body=body,
        recovery_title=f"Curve {snapshot.name} 总价值恢复",
        recovery_body=body,
        now=now,
    )
    return [event] if event is not None else []


def _evaluate_point_metric(
    *,
    key: str,
    value: float,
    label: str,
    threshold: float,
    window_minutes: int,
    history: RollingMetricHistory,
    engine: AlertEngine,
    now: datetime,
    alert_title: str,
    recovery_title: str,
) -> list[AlertEvent]:
    latest_change = history.latest_change(key, current=value)
    window_change = history.window_change(
        key, current=value, now=now, window_minutes=window_minutes
    )
    history.record(key, value, now)
    if latest_change is None:
        return []
    lines = _dual_window_change_lines(
        latest_change=latest_change,
        window_change=window_change,
        window_minutes=window_minutes,
    )
    body = f"当前 {label}: {value:.6f}\n" + "\n".join(lines)
    event = engine.evaluate(
        metric_key=key,
        breached=_absolute_change_breached(
            latest_change=latest_change,
            window_change=window_change,
            threshold=threshold,
        ),
        alert_title=alert_title,
        alert_body=body,
        recovery_title=recovery_title,
        recovery_body=body,
        now=now,
    )
    return [event] if event is not None else []


def _dual_window_change_lines(
    *,
    latest_change: MetricChange,
    window_change: MetricChange | None,
    window_minutes: int,
) -> list[str]:
    lines = [f"1m 变化: {latest_change.percent:+.2%}"]
    if window_change is None:
        lines.append(f"{window_minutes}m 变化: 暂无")
    else:
        lines.append(f"{window_minutes}m 变化: {window_change.percent:+.2%}")
    return lines


def _drop_breached(
    *,
    latest_change: MetricChange,
    window_change: MetricChange | None,
    threshold: float,
) -> bool:
    return latest_change.percent < -threshold or (
        window_change is not None and window_change.percent < -threshold
    )


def _absolute_change_breached(
    *,
    latest_change: MetricChange,
    window_change: MetricChange | None,
    threshold: float,
) -> bool:
    return exceeds_threshold(latest_change.percent, threshold) or (
        window_change is not None and exceeds_threshold(window_change.percent, threshold)
    )


def _stable_pool_imbalance(balances: dict[str, float]) -> float:
    values = [value for value in balances.values() if value > 0]
    if len(values) < 2:
        return 0.0
    average = sum(values) / len(values)
    if average == 0:
        return 0.0
    return max(abs(value - average) / average for value in values)
