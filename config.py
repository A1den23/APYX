from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import yaml


@dataclass(frozen=True)
class NamedAddress:
    name: str
    address: str


@dataclass(frozen=True)
class SupplyToken:
    name: str
    address: str
    absolute_change_threshold: float


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
    tokens: tuple[SupplyToken, ...]
    threshold_pct: float
    window_minutes: int


@dataclass(frozen=True)
class ApyUsdConfig:
    token: NamedAddress
    total_assets_change_pct: float
    total_assets_absolute_change_threshold: float
    price_apxusd_change_pct: float
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
    apyusd: ApyUsdConfig
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
            tokens=tuple(_load_supply_token(item) for item in data["supply"]["tokens"]),
            threshold_pct=float(data["supply"]["threshold_pct"]),
            window_minutes=int(data["supply"]["window_minutes"]),
        ),
        apyusd=ApyUsdConfig(
            token=NamedAddress(**data["apyusd"]["token"]),
            total_assets_change_pct=float(data["apyusd"]["total_assets_change_pct"]),
            total_assets_absolute_change_threshold=float(
                data["apyusd"]["total_assets_absolute_change_threshold"]
            ),
            price_apxusd_change_pct=float(data["apyusd"]["price_apxusd_change_pct"]),
            window_minutes=int(data["apyusd"]["window_minutes"]),
        ),
        alert=AlertConfig(
            cooldown_minutes=int(data["alert"]["cooldown_minutes"]),
        ),
    )


def _load_supply_token(item: dict) -> SupplyToken:
    return SupplyToken(
        name=item["name"],
        address=item["address"],
        absolute_change_threshold=float(item["absolute_change_threshold"]),
    )


@dataclass(frozen=True)
class EnvConfig:
    finnhub_api_key: str
    telegram_bot_token: str
    telegram_chat_id: str
    eth_rpc_url: str


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_env_config(env_file: str | Path = ".env") -> EnvConfig:
    load_dotenv(env_file)
    return EnvConfig(
        finnhub_api_key=_required_env("FINNHUB_API_KEY"),
        telegram_bot_token=_required_env("TG_BOT_TOKEN"),
        telegram_chat_id=_required_env("TG_CHAT_ID"),
        eth_rpc_url=_required_env("ETH_RPC_URL"),
    )
