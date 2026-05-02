from __future__ import annotations

import asyncio
from datetime import datetime

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from app.config import AppConfig
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

DERIVED_CONTRACT_ABI = [
    {
        "inputs": [],
        "name": "authority",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "denyList",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "unlockToken",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "vesting",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
]
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _security_contract_names(settings: AppConfig) -> dict[str, str]:
    names = {token.address.lower(): token.name for token in settings.supply.tokens}
    names[settings.apyusd.token.address.lower()] = settings.apyusd.token.name
    for market in settings.pendle.markets:
        names[market.address.lower()] = f"Pendle {market.name}"
    for pool in settings.curve.pools:
        names[pool.address.lower()] = f"Curve {pool.name}"
    for token in settings.commit.tokens:
        names[token.address.lower()] = token.name
    if settings.yield_distribution.rate_view is not None:
        rate_view = settings.yield_distribution.rate_view
        names[rate_view.address.lower()] = rate_view.name
    for contract in settings.security.contracts:
        names[contract.address.lower()] = contract.name
    return names


def _read_address_function(web3: Web3, *, address: str, function_name: str) -> str | None:
    try:
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(address),
            abi=DERIVED_CONTRACT_ABI,
        )
        value = getattr(contract.functions, function_name)().call()
    except Exception as e:
        print(f"security_scan: _read_address_function({address}, {function_name}) failed: {e}", flush=True)
        return None
    if not isinstance(value, str) or value.lower() == ZERO_ADDRESS:
        return None
    return value.lower()


def _derive_security_contract_names(web3: Web3, base_names: dict[str, str]) -> dict[str, str]:
    names = dict(base_names)
    for address, name in tuple(base_names.items()):
        authority = _read_address_function(web3, address=address, function_name="authority")
        if authority is not None:
            names.setdefault(authority, f"AccessManager for {name}")
        deny_list = _read_address_function(web3, address=address, function_name="denyList")
        if deny_list is not None:
            names.setdefault(deny_list, "AddressList")
        unlock_token = _read_address_function(web3, address=address, function_name="unlockToken")
        if unlock_token is not None:
            names.setdefault(unlock_token, "UnlockToken")
        vesting = _read_address_function(web3, address=address, function_name="vesting")
        if vesting is not None:
            names.setdefault(vesting, "LinearVestV0")
    return names


async def resolve_security_contract_names(
    web3: Web3,
    *,
    settings: AppConfig,
) -> dict[str, str]:
    base_names = _security_contract_names(settings)
    return await asyncio.to_thread(_derive_security_contract_names, web3, base_names)


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

    contract_names = await resolve_security_contract_names(web3, settings=settings)
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
