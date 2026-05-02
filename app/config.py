from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
import yaml


@dataclass(frozen=True)
class FinnhubSymbolConfig:
    symbol: str
    threshold_price: float


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
    symbols: tuple[FinnhubSymbolConfig, ...]


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
class MorphoMarketConfig:
    name: str
    market_id: str
    chain_id: int = 1


@dataclass(frozen=True)
class MorphoConfig:
    markets: tuple[MorphoMarketConfig, ...]
    total_market_size_drop_pct: float
    total_liquidity_drop_pct: float
    borrow_rate_change_pct: float
    oracle_price_change_pct: float
    window_minutes: int


@dataclass(frozen=True)
class CurveCoin:
    name: str
    address: str


@dataclass(frozen=True)
class CurvePool:
    name: str
    address: str
    coins: tuple[CurveCoin, ...]
    metrics: tuple[str, ...] = field(
        default=("balances", "imbalance", "virtual_price", "apxusd_usdc_price")
    )
    price_deviation_pct: float | None = None
    total_value_drop_pct: float | None = None


@dataclass(frozen=True)
class CurveConfig:
    pools: tuple[CurvePool, ...]
    balance_drop_pct: float
    imbalance_pct: float
    virtual_price_change_pct: float
    price_deviation_pct: float
    window_minutes: int
    total_value_drop_pct: float | None = None


@dataclass(frozen=True)
class SupplyConfig:
    tokens: tuple[SupplyToken, ...]
    threshold_pct: float
    window_minutes: int


@dataclass(frozen=True)
class CommitTokenConfig:
    name: str
    address: str
    asset: str
    absolute_change_threshold: float


@dataclass(frozen=True)
class CommitConfig:
    tokens: tuple[CommitTokenConfig, ...]
    cap_usage_warning_pct: float
    assets_change_pct: float
    assets_absolute_change_threshold: float
    window_minutes: int


@dataclass(frozen=True)
class ApyUsdConfig:
    token: NamedAddress
    total_assets_change_pct: float
    total_assets_absolute_change_threshold: float
    price_apxusd_change_pct: float
    window_minutes: int


@dataclass(frozen=True)
class YieldDistributionConfig:
    rate_view: NamedAddress | None
    apy_change_pct: float
    annualized_yield_change_pct: float
    unvested_change_pct: float
    window_minutes: int


@dataclass(frozen=True)
class SecurityConfig:
    start_block_lookback: int
    max_blocks_per_scan: int
    recent_event_hold_minutes: int
    apyusd_min_supply_increase: float
    apyusd_min_backing_ratio: float
    contracts: tuple[NamedAddress, ...]


@dataclass(frozen=True)
class SolvencyConfig:
    accountable_url: str
    warning_collateralization: float
    critical_collateralization: float
    max_data_age_minutes: int


@dataclass(frozen=True)
class AlertConfig:
    cooldown_minutes: int


@dataclass(frozen=True)
class RuntimeConfig:
    state_path: str
    http_timeout_seconds: int


@dataclass(frozen=True)
class AppConfig:
    finnhub: FinnhubConfig
    peg: PegConfig
    pendle: PendleConfig
    morpho: MorphoConfig
    curve: CurveConfig
    supply: SupplyConfig
    commit: CommitConfig
    apyusd: ApyUsdConfig
    yield_distribution: YieldDistributionConfig
    security: SecurityConfig
    solvency: SolvencyConfig
    alert: AlertConfig
    runtime: RuntimeConfig


def load_app_config(path: str | Path = "config.yaml") -> AppConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return AppConfig(
        finnhub=_load_finnhub_config(data["finnhub"]),
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
        morpho=_load_morpho_config(data.get("morpho", {})),
        curve=_load_curve_config(data.get("curve", {})),
        supply=SupplyConfig(
            tokens=tuple(_load_supply_token(item) for item in data["supply"]["tokens"]),
            threshold_pct=float(data["supply"]["threshold_pct"]),
            window_minutes=int(data["supply"]["window_minutes"]),
        ),
        commit=_load_commit_config(data.get("commit", {})),
        apyusd=ApyUsdConfig(
            token=NamedAddress(**data["apyusd"]["token"]),
            total_assets_change_pct=float(data["apyusd"]["total_assets_change_pct"]),
            total_assets_absolute_change_threshold=float(
                data["apyusd"]["total_assets_absolute_change_threshold"]
            ),
            price_apxusd_change_pct=float(data["apyusd"]["price_apxusd_change_pct"]),
            window_minutes=int(data["apyusd"]["window_minutes"]),
        ),
        yield_distribution=_load_yield_distribution_config(
            data.get("yield_distribution", {})
        ),
        security=_load_security_config(data.get("security", {})),
        solvency=_load_solvency_config(data["solvency"]),
        alert=AlertConfig(
            cooldown_minutes=int(data["alert"]["cooldown_minutes"]),
        ),
        runtime=_load_runtime_config(data.get("runtime", {})),
    )


def _load_finnhub_config(data: dict) -> FinnhubConfig:
    legacy_symbol = str(data["symbol"])
    legacy_threshold = float(data["threshold_price"])
    symbols_data = data.get("symbols")
    if symbols_data is None:
        symbols = (
            FinnhubSymbolConfig(
                symbol=legacy_symbol,
                threshold_price=legacy_threshold,
            ),
        )
    else:
        symbols = tuple(
            FinnhubSymbolConfig(
                symbol=str(item["symbol"]),
                threshold_price=float(item["threshold_price"]),
            )
            for item in symbols_data
        )
    return FinnhubConfig(
        symbol=legacy_symbol,
        threshold_price=legacy_threshold,
        symbols=symbols,
    )


def _load_supply_token(item: dict) -> SupplyToken:
    return SupplyToken(
        name=item["name"],
        address=item["address"],
        absolute_change_threshold=float(item["absolute_change_threshold"]),
    )


def _load_curve_config(data: dict) -> CurveConfig:
    return CurveConfig(
        pools=tuple(_load_curve_pool(item) for item in data.get("pools", ())),
        balance_drop_pct=float(data.get("balance_drop_pct", 0.10)),
        imbalance_pct=float(data.get("imbalance_pct", 0.20)),
        virtual_price_change_pct=float(data.get("virtual_price_change_pct", 0.01)),
        price_deviation_pct=float(data.get("price_deviation_pct", 0.003)),
        window_minutes=int(data.get("window_minutes", 30)),
        total_value_drop_pct=(
            float(data["total_value_drop_pct"])
            if "total_value_drop_pct" in data
            else None
        ),
    )


def _load_morpho_config(data: dict) -> MorphoConfig:
    return MorphoConfig(
        markets=tuple(
            MorphoMarketConfig(
                name=str(item["name"]),
                market_id=str(item["market_id"]),
                chain_id=int(item.get("chain_id", 1)),
            )
            for item in data.get("markets", ())
        ),
        total_market_size_drop_pct=float(
            data.get("total_market_size_drop_pct", 0.10)
        ),
        total_liquidity_drop_pct=float(data.get("total_liquidity_drop_pct", 0.10)),
        borrow_rate_change_pct=float(data.get("borrow_rate_change_pct", 0.10)),
        oracle_price_change_pct=float(data.get("oracle_price_change_pct", 0.02)),
        window_minutes=int(data.get("window_minutes", 30)),
    )


def _load_curve_pool(item: dict) -> CurvePool:
    return CurvePool(
        name=str(item["name"]),
        address=str(item["address"]),
        coins=tuple(CurveCoin(**coin) for coin in item["coins"]),
        metrics=tuple(
            str(metric)
            for metric in item.get(
                "metrics",
                ("balances", "imbalance", "virtual_price", "apxusd_usdc_price"),
            )
        ),
        price_deviation_pct=(
            float(item["price_deviation_pct"])
            if "price_deviation_pct" in item
            else None
        ),
        total_value_drop_pct=(
            float(item["total_value_drop_pct"])
            if "total_value_drop_pct" in item
            else None
        ),
    )


def _load_commit_config(data: dict) -> CommitConfig:
    assets_absolute_change_threshold = float(
        data.get("assets_absolute_change_threshold", 5_000_000)
    )
    return CommitConfig(
        tokens=tuple(
            _load_commit_token(
                item,
                default_absolute_change_threshold=assets_absolute_change_threshold,
            )
            for item in data.get("tokens", ())
        ),
        cap_usage_warning_pct=float(data.get("cap_usage_warning_pct", 0.90)),
        assets_change_pct=float(data.get("assets_change_pct", 0.10)),
        assets_absolute_change_threshold=assets_absolute_change_threshold,
        window_minutes=int(data.get("window_minutes", 30)),
    )


def _load_commit_token(
    item: dict,
    *,
    default_absolute_change_threshold: float,
) -> CommitTokenConfig:
    return CommitTokenConfig(
        name=str(item["name"]),
        address=str(item["address"]),
        asset=str(item["asset"]),
        absolute_change_threshold=float(
            item.get(
                "absolute_change_threshold",
                default_absolute_change_threshold,
            )
        ),
    )


def _load_yield_distribution_config(data: dict) -> YieldDistributionConfig:
    rate_view_data = data.get("rate_view")
    return YieldDistributionConfig(
        rate_view=NamedAddress(**rate_view_data) if rate_view_data else None,
        apy_change_pct=float(data.get("apy_change_pct", 0.10)),
        annualized_yield_change_pct=float(
            data.get("annualized_yield_change_pct", data.get("apr_change_pct", 0.10))
        ),
        unvested_change_pct=float(data.get("unvested_change_pct", 0.20)),
        window_minutes=int(data.get("window_minutes", 30)),
    )


def _load_security_config(data: dict) -> SecurityConfig:
    return SecurityConfig(
        start_block_lookback=int(data.get("start_block_lookback", 25)),
        max_blocks_per_scan=int(data.get("max_blocks_per_scan", 100)),
        recent_event_hold_minutes=int(data.get("recent_event_hold_minutes", 60)),
        apyusd_min_supply_increase=float(data.get("apyusd_min_supply_increase", 100000)),
        apyusd_min_backing_ratio=float(data.get("apyusd_min_backing_ratio", 0.99)),
        contracts=tuple(NamedAddress(**item) for item in data.get("contracts", ())),
    )


def _load_solvency_config(data: dict) -> SolvencyConfig:
    return SolvencyConfig(
        accountable_url=data["accountable_url"],
        warning_collateralization=float(data["warning_collateralization"]),
        critical_collateralization=float(data["critical_collateralization"]),
        max_data_age_minutes=int(data["max_data_age_minutes"]),
    )


def _load_runtime_config(data: dict) -> RuntimeConfig:
    return RuntimeConfig(
        state_path=str(data.get("state_path", "state/runtime-state.json")),
        http_timeout_seconds=int(data.get("http_timeout_seconds", 20)),
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
