from __future__ import annotations

from collections.abc import Iterable

from app.rpc_status import RpcEndpointStatus


def build_rpc_message(statuses: Iterable[RpcEndpointStatus]) -> str:
    lines = ["ETH RPC status:"]
    for status in statuses:
        state = "OK" if status.connected else "FAIL"
        active = " (active)" if status.active else ""
        if status.connected:
            detail = (
                f"block={status.block_number}"
                if status.block_number is not None
                else "connected"
            )
        else:
            detail = status.error or "unavailable"
        lines.append(f"[{state}] {status.role} {status.label}{active} - {detail}")
    return "\n".join(lines)
