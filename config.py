from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class NamedAddress:
    name: str
    address: str


@dataclass(frozen=True)
class TvlToken:
    name: str
    url: str


@dataclass(frozen=True)
class FinnhubConfig:
    symbol: str
    threshold_price: float


@dataclass(frozen=True)
class PegConfig:
    token: NamedAddress
    threshold_pct: float


@dataclass(frozen=True)
class PendleConfig:
    markets: tuple[NamedAddress, ...]
    liquidity_drop_pct: float
    apy_change_pct: float
    pt_price_change_pct: float
    window_minutes: int


@dataclass(frozen=True)
class SupplyConfig:
    tokens: tuple[NamedAddress, ...]
    threshold_pct: float


@dataclass(frozen=True)
class TvlConfig:
    tokens: tuple[TvlToken, ...]
    threshold_pct: float
    window_minutes: int


@dataclass(frozen=True)
class AlertConfig:
    cooldown_minutes: int


@dataclass(frozen=True)
class AppConfig:
    finnhub: FinnhubConfig
    peg: PegConfig
    pendle: PendleConfig
    supply: SupplyConfig
    tvl: TvlConfig
    alert: AlertConfig


def load_app_config(path: str | Path = "config.yaml") -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AppConfig(
        finnhub=FinnhubConfig(
            symbol=data["finnhub"]["symbol"],
            threshold_price=float(data["finnhub"]["threshold_price"]),
        ),
        peg=PegConfig(
            token=NamedAddress(**data["peg"]["token"]),
            threshold_pct=float(data["peg"]["threshold_pct"]),
        ),
        pendle=PendleConfig(
            markets=tuple(NamedAddress(**item) for item in data["pendle"]["markets"]),
            liquidity_drop_pct=float(data["pendle"]["liquidity_drop_pct"]),
            apy_change_pct=float(data["pendle"]["apy_change_pct"]),
            pt_price_change_pct=float(data["pendle"]["pt_price_change_pct"]),
            window_minutes=int(data["pendle"]["window_minutes"]),
        ),
        supply=SupplyConfig(
            tokens=tuple(NamedAddress(**item) for item in data["supply"]["tokens"]),
            threshold_pct=float(data["supply"]["threshold_pct"]),
        ),
        tvl=TvlConfig(
            tokens=tuple(TvlToken(**item) for item in data["tvl"]["tokens"]),
            threshold_pct=float(data["tvl"]["threshold_pct"]),
            window_minutes=int(data["tvl"]["window_minutes"]),
        ),
        alert=AlertConfig(
            cooldown_minutes=int(data["alert"]["cooldown_minutes"]),
        ),
    )
