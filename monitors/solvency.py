from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aiohttp import ClientSession

from alert.engine import AlertEngine, AlertEvent


DEFAULT_ACCOUNTABLE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://accountable.apyx.fi",
    "Referer": "https://accountable.apyx.fi/",
}


@dataclass(frozen=True)
class AccountableSolvencySnapshot:
    collateralization: float
    total_reserves: float
    total_supply: float
    net: float
    timestamp: datetime
    verifiability: str
    interval: str


async def fetch_solvency_snapshot(
    session: ClientSession,
    *,
    url: str,
) -> AccountableSolvencySnapshot:
    async with session.get(url, headers=DEFAULT_ACCOUNTABLE_HEADERS) as response:
        response.raise_for_status()
        payload = await response.json()
    return parse_accountable_dashboard(payload)


def parse_accountable_dashboard(payload: dict) -> AccountableSolvencySnapshot:
    if payload.get("res") != "ok":
        raise ValueError("Accountable dashboard response is not ok")

    data = payload["data"]
    reserves = data["reserves"]
    ts_ms = int(data["ts"])
    timestamp = datetime.fromtimestamp(ts_ms / 1000, timezone.utc)

    return AccountableSolvencySnapshot(
        collateralization=float(data["collateralization"]),
        total_reserves=float(reserves["total_reserves"]["value"]),
        total_supply=float(reserves["total_supply"]["value"]),
        net=float(data["net"]),
        timestamp=timestamp,
        verifiability=str(reserves.get("verifiability", "")),
        interval=str(reserves.get("interval", "")),
    )


def evaluate_solvency(
    *,
    snapshot: AccountableSolvencySnapshot,
    warning_collateralization: float,
    critical_collateralization: float,
    max_data_age: timedelta,
    engine: AlertEngine,
    now: datetime,
) -> AlertEvent | None:
    data_age = max(now - snapshot.timestamp, timedelta())
    critical = (
        snapshot.collateralization < critical_collateralization
        or snapshot.total_reserves < snapshot.total_supply
        or snapshot.net < 0
    )
    stale = data_age > max_data_age
    warning = snapshot.collateralization < warning_collateralization

    reasons: list[str] = []
    if snapshot.total_reserves < snapshot.total_supply or snapshot.net < 0:
        reasons.append("Reserves are below supply")
    if snapshot.collateralization < critical_collateralization:
        reasons.append(
            f"Collateralization is below critical threshold: {critical_collateralization:.2%}"
        )
    elif snapshot.collateralization < warning_collateralization:
        reasons.append(
            f"Collateralization is below warning threshold: {warning_collateralization:.2%}"
        )
    if stale:
        reasons.append(f"Data is older than {max_data_age.total_seconds() / 60:.0f} minutes")

    body = _solvency_body(
        snapshot=snapshot,
        data_age=data_age,
        warning_collateralization=warning_collateralization,
        critical_collateralization=critical_collateralization,
        reasons=reasons,
    )

    if critical:
        alert_title = "APYX Solvency Critical"
    elif stale:
        alert_title = "APYX Solvency Data Stale"
    else:
        alert_title = "APYX Solvency Warning"

    return engine.evaluate(
        metric_key="solvency:accountable",
        breached=critical or stale or warning,
        alert_title=alert_title,
        alert_body=body,
        recovery_title="APYX Solvency Normal",
        recovery_body=body,
        now=now,
    )


def _solvency_body(
    *,
    snapshot: AccountableSolvencySnapshot,
    data_age: timedelta,
    warning_collateralization: float,
    critical_collateralization: float,
    reasons: list[str],
) -> str:
    lines = [
        f"Collateralization: {snapshot.collateralization:.2%}",
        f"Total reserves: ${snapshot.total_reserves:,.2f}",
        f"Total supply: ${snapshot.total_supply:,.2f}",
        f"Net reserves: ${snapshot.net:,.2f}",
        f"Data age: {data_age.total_seconds() / 60:.1f} minutes",
        f"Warning threshold: {warning_collateralization:.2%}",
        f"Critical threshold: {critical_collateralization:.2%}",
    ]
    if reasons:
        lines.append("Reasons: " + "; ".join(reasons))
    return "\n".join(lines)
