from __future__ import annotations

import asyncio
from datetime import datetime

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from config import AppConfig
from monitors.security_events import (
    PRIVILEGED_EVENT_TOPICS,
    TRANSFER_TOPIC,
    LogScanState,
    RecentSecurityEventCache,
    evaluate_privileged_logs,
    evaluate_token_movements,
    fetch_decimals_async,
    fetch_logs_async,
    parse_token_movements,
)


def _security_contract_names(settings: AppConfig) -> dict[str, str]:
    names = {token.address.lower(): token.name for token in settings.supply.tokens}
    names[settings.apyusd.token.address.lower()] = settings.apyusd.token.name
    for market in settings.pendle.markets:
        names[market.address.lower()] = f"Pendle {market.name}"
    return names


async def run_security_event_checks(
    *,
    web3: Web3,
    settings: AppConfig,
    state: LogScanState,
    recent_security_events: RecentSecurityEventCache,
    token_decimals_by_address: dict[str, int],
    engine: AlertEngine,
    now: datetime,
) -> list[AlertEvent]:
    latest_block = await asyncio.to_thread(lambda: int(web3.eth.block_number))
    block_range = state.next_range(latest_block=latest_block)
    if block_range is None:
        return []
    from_block, to_block = block_range
    if not token_decimals_by_address:
        token_decimals_by_address.update(
            await fetch_decimals_async(web3, tokens=settings.supply.tokens)
        )

    movement_logs = await fetch_logs_async(
        web3,
        addresses=[token.address for token in settings.supply.tokens],
        topics=[TRANSFER_TOPIC],
        from_block=from_block,
        to_block=to_block,
    )
    movements = parse_token_movements(
        movement_logs,
        tokens=settings.supply.tokens,
        decimals_by_address=token_decimals_by_address,
    )
    events = evaluate_token_movements(
        movements,
        tokens=settings.supply.tokens,
        now=now,
    )

    contract_names = _security_contract_names(settings)
    privileged_logs = await fetch_logs_async(
        web3,
        addresses=[Web3.to_checksum_address(a) for a in contract_names],
        topics=[list(PRIVILEGED_EVENT_TOPICS.values())],
        from_block=from_block,
        to_block=to_block,
    )
    events.extend(
        evaluate_privileged_logs(
            privileged_logs,
            contract_names=contract_names,
            now=now,
        )
    )
    recovery_event = recent_security_events.evaluate(
        events=events,
        engine=engine,
        now=now,
    )
    if recovery_event is not None:
        events.append(recovery_event)
    state.mark_pending(to_block)
    return events
