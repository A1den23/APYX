from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from app.config import SupplyToken

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
TRANSFER_TOPIC = Web3.keccak(text="Transfer(address,address,uint256)").hex()
PRIVILEGED_EVENT_TOPICS = {
    signature: Web3.keccak(text=signature).hex()
    for signature in (
        "RoleGranted(bytes32,address,address)",
        "RoleRevoked(bytes32,address,address)",
        "OwnershipTransferred(address,address)",
        "AdminChanged(address,address)",
        "Upgraded(address)",
        "BeaconUpgraded(address)",
        "Paused(address)",
        "Unpaused(address)",
    )
}
_PRIVILEGED_TOPIC_NAMES = {
    topic.lower(): signature.split("(", 1)[0]
    for signature, topic in PRIVILEGED_EVENT_TOPICS.items()
}


@dataclass
class LogScanState:
    start_block_lookback: int
    max_blocks_per_scan: int
    last_scanned_block: int | None = None
    pending_scanned_block: int | None = None

    def next_range(self, *, latest_block: int) -> tuple[int, int] | None:
        if self.last_scanned_block is None:
            from_block = max(0, latest_block - self.start_block_lookback + 1)
        else:
            from_block = self.last_scanned_block + 1
        if from_block > latest_block:
            return None
        to_block = min(latest_block, from_block + self.max_blocks_per_scan - 1)
        return from_block, to_block

    def mark_scanned(self, block_number: int) -> None:
        self.last_scanned_block = block_number
        self.pending_scanned_block = None

    def mark_pending(self, block_number: int) -> None:
        self.pending_scanned_block = block_number

    def commit_pending(self) -> None:
        if self.pending_scanned_block is not None:
            self.mark_scanned(self.pending_scanned_block)

    def clear_pending(self) -> None:
        self.pending_scanned_block = None

    def to_dict(self) -> dict:
        return {
            "start_block_lookback": self.start_block_lookback,
            "max_blocks_per_scan": self.max_blocks_per_scan,
            "last_scanned_block": self.last_scanned_block,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LogScanState":
        return cls(
            start_block_lookback=int(data["start_block_lookback"]),
            max_blocks_per_scan=int(data["max_blocks_per_scan"]),
            last_scanned_block=data.get("last_scanned_block"),
        )


@dataclass
class RecentSecurityEventCache:
    hold_duration: timedelta
    last_event_at: datetime | None = None
    last_event_title: str = ""
    last_event_body: str = ""

    def evaluate(
        self,
        *,
        events: list[AlertEvent],
        engine: AlertEngine,
        now: datetime,
    ) -> AlertEvent | None:
        if events:
            latest_event = events[-1]
            self.last_event_at = now
            self.last_event_title = latest_event.title
            self.last_event_body = latest_event.body
            engine.evaluate(
                metric_key="security_events",
                breached=True,
                alert_title="Security Events Recent",
                alert_body=self._status_body(now),
                recovery_title="Security Events Normal",
                recovery_body="No security events in the last hour.",
                now=now,
            )
            return None

        if self.last_event_at is None:
            return None

        if now - self.last_event_at < self.hold_duration:
            return None

        return engine.evaluate(
            metric_key="security_events",
            breached=False,
            alert_title="Security Events Recent",
            alert_body=self._status_body(now),
            recovery_title="Security Events Normal",
            recovery_body="No security events in the last hour.",
            now=now,
        )

    def _status_body(self, now: datetime) -> str:
        if self.last_event_at is None:
            return "No security events in the last hour."
        age_minutes = (now - self.last_event_at).total_seconds() / 60
        return (
            f"Last event: {self.last_event_title}\n"
            f"Age: {age_minutes:.1f} minutes\n"
            f"{self.last_event_body}"
        )

    def to_dict(self) -> dict:
        return {
            "hold_duration_seconds": self.hold_duration.total_seconds(),
            "last_event_at": (
                self.last_event_at.isoformat()
                if self.last_event_at is not None
                else None
            ),
            "last_event_title": self.last_event_title,
            "last_event_body": self.last_event_body,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecentSecurityEventCache":
        last_event_at = data.get("last_event_at")
        return cls(
            hold_duration=timedelta(
                seconds=float(data.get("hold_duration_seconds", 3600))
            ),
            last_event_at=(
                datetime.fromisoformat(last_event_at)
                if last_event_at is not None
                else None
            ),
            last_event_title=str(data.get("last_event_title", "")),
            last_event_body=str(data.get("last_event_body", "")),
        )


@dataclass(frozen=True)
class TokenMovement:
    token_name: str
    token_address: str
    kind: str
    amount: float
    counterparty: str
    transaction_hash: str
    block_number: int
    log_index: int


def _hex(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return "0x" + value.hex()
    return value.hex()


def _topic_to_address(topic: Any) -> str:
    raw = _hex(topic).lower().removeprefix("0x")
    return "0x" + raw[-40:]


def _raw_uint256(value: Any) -> int:
    raw = _hex(value).removeprefix("0x")
    return int(raw or "0", 16)


def _tx_hash(log: dict[str, Any]) -> str:
    return _hex(log.get("transactionHash", ""))


def parse_token_movements(
    logs: list[dict[str, Any]],
    *,
    tokens: tuple[SupplyToken, ...],
    decimals_by_address: dict[str, int],
) -> list[TokenMovement]:
    names = {token.address.lower(): token.name for token in tokens}
    movements: list[TokenMovement] = []
    for log in logs:
        topics = log.get("topics", [])
        if len(topics) < 3 or _hex(topics[0]).lower() != TRANSFER_TOPIC.lower():
            continue
        token_address = str(log["address"]).lower()
        from_address = _topic_to_address(topics[1])
        to_address = _topic_to_address(topics[2])
        if from_address != ZERO_ADDRESS and to_address != ZERO_ADDRESS:
            continue
        decimals = decimals_by_address[token_address]
        amount = _raw_uint256(log.get("data", "0x0")) / float(10**decimals)
        movements.append(
            TokenMovement(
                token_name=names[token_address],
                token_address=token_address,
                kind="mint" if from_address == ZERO_ADDRESS else "burn",
                amount=amount,
                counterparty=to_address if from_address == ZERO_ADDRESS else from_address,
                transaction_hash=_tx_hash(log),
                block_number=int(log["blockNumber"]),
                log_index=int(log.get("logIndex", 0)),
            )
        )
    return movements


def evaluate_token_movements(
    movements: list[TokenMovement],
    *,
    tokens: tuple[SupplyToken, ...],
    now: datetime,
) -> list[AlertEvent]:
    thresholds = {token.name: token.absolute_change_threshold for token in tokens}
    events: list[AlertEvent] = []
    for movement in movements:
        threshold = thresholds[movement.token_name]
        if movement.amount <= threshold:
            continue
        kind_title = "Mint" if movement.kind == "mint" else "Burn"
        body = (
            f"Amount: {movement.amount:,.2f} {movement.token_name}\n"
            f"Threshold: {threshold:,.2f} {movement.token_name}\n"
            f"Counterparty: {movement.counterparty}\n"
            f"Block: {movement.block_number}\n"
            f"Tx: {movement.transaction_hash}"
        )
        events.append(
            AlertEvent(
                "ALERT",
                f"{movement.token_name} Large {kind_title}",
                body,
                now,
            )
        )
    return events


def evaluate_privileged_logs(
    logs: list[dict[str, Any]],
    *,
    contract_names: dict[str, str],
    now: datetime,
) -> list[AlertEvent]:
    events: list[AlertEvent] = []
    for log in logs:
        topics = log.get("topics", [])
        if not topics:
            continue
        event_name = _PRIVILEGED_TOPIC_NAMES.get(_hex(topics[0]).lower())
        if event_name is None:
            continue
        address = str(log["address"]).lower()
        contract_name = contract_names.get(address, address)
        body = (
            f"Event: {event_name}\n"
            f"Contract: {contract_name} ({address})\n"
            f"Block: {int(log['blockNumber'])}\n"
            f"Tx: {_tx_hash(log)}"
        )
        events.append(
            AlertEvent(
                "ALERT",
                f"{contract_name} Privileged Event",
                body,
                now,
            )
        )
    return events


def fetch_decimals(web3: Web3, *, tokens: tuple[SupplyToken, ...]) -> dict[str, int]:
    from monitors.supply import ERC20_ABI

    decimals: dict[str, int] = {}
    for token in tokens:
        contract = web3.eth.contract(address=Web3.to_checksum_address(token.address), abi=ERC20_ABI)
        decimals[token.address.lower()] = int(contract.functions.decimals().call())
    return decimals


async def fetch_decimals_async(
    web3: Web3,
    *,
    tokens: tuple[SupplyToken, ...],
) -> dict[str, int]:
    return await asyncio.to_thread(fetch_decimals, web3, tokens=tokens)


def fetch_logs(
    web3: Web3,
    *,
    addresses: list[str],
    topics: list[Any],
    from_block: int,
    to_block: int,
) -> list[dict[str, Any]]:
    return list(
        web3.eth.get_logs(
            {
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": addresses,
                "topics": topics,
            }
        )
    )


async def fetch_logs_async(
    web3: Web3,
    *,
    addresses: list[str],
    topics: list[Any],
    from_block: int,
    to_block: int,
) -> list[dict[str, Any]]:
    return await asyncio.to_thread(
        fetch_logs,
        web3,
        addresses=addresses,
        topics=topics,
        from_block=from_block,
        to_block=to_block,
    )
