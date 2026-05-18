from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RpcEndpointStatus:
    role: str
    label: str
    active: bool
    connected: bool
    block_number: int | None = None
    error: str | None = None
