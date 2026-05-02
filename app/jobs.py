from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiohttp import ClientSession
from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from alert.telegram import TelegramSender
from commands.health import HealthTracker
from app.config import AppConfig, EnvConfig
from app.errors import safe_error_message
from app.history import RollingMetricHistory
from monitors.apyusd import (
    evaluate_price_apxusd,
    evaluate_supply_asset_backing,
    evaluate_total_assets,
    fetch_price_apxusd_async,
    fetch_total_assets_async,
)
from monitors.commit import evaluate_commit_token, fetch_commit_token_snapshot_async
from monitors.curve import evaluate_curve_pool, fetch_curve_pool_snapshot_async
from monitors.morpho import evaluate_morpho_market, fetch_morpho_market
from monitors.peg import evaluate_peg_price, fetch_peg_price
from monitors.pendle import evaluate_pendle_market, fetch_pendle_market
from monitors.security_events import LogScanState, RecentSecurityEventCache
from monitors.solvency import evaluate_solvency, fetch_solvency_snapshot
from monitors.strc_price import evaluate_strc_price, fetch_strc_price
from monitors.supply import evaluate_supply, fetch_total_supply_async
from monitors.yield_distribution import (
    evaluate_yield_distribution,
    fetch_yield_distribution_snapshot_async,
)
from app.runtime_state import RuntimeState, RuntimeStateStore
from app.security_scan import run_security_event_checks
from app.status_cache import StatusCache


async def send_events(
    sender: TelegramSender,
    events: list[AlertEvent],
    *,
    engine: AlertEngine,
    tracker: HealthTracker,
) -> bool:
    delivered = True
    for event in events:
        try:
            await sender.send(event)
        except Exception as e:
            delivered = False
            engine.rollback(event)
            safe_error = safe_error_message(e)
            tracker.record_failure(f"alert:{event.metric_key or event.kind}", safe_error)
            print(
                f"Failed to send alert {event.metric_key or event.kind}: {safe_error}",
                flush=True,
            )
    return delivered


def save_runtime_state(
    store: RuntimeStateStore,
    *,
    engine: AlertEngine,
    history: RollingMetricHistory,
    security_state: LogScanState,
    recent_security_events: RecentSecurityEventCache,
    tracker: HealthTracker,
) -> None:
    try:
        store.save(
            RuntimeState(
                alert_engine=engine,
                history=history,
                security_state=security_state,
                recent_security_events=recent_security_events,
            )
        )
    except Exception as e:
        tracker.record_failure("runtime_state", safe_error_message(e))


async def run_one_minute_checks(
    *,
    session: ClientSession,
    web3: Web3,
    settings: AppConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
    sender: TelegramSender,
    tracker: HealthTracker,
    security_state: LogScanState,
    recent_security_events: RecentSecurityEventCache,
    token_decimals_by_address: dict[str, int],
    status_cache: StatusCache | None = None,
    state_store: RuntimeStateStore | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []
    previous_apyusd_supply = None
    current_apyusd_supply = None
    previous_apyusd_total_assets = None
    current_apyusd_total_assets = None

    try:
        peg_price = await fetch_peg_price(session, address=settings.peg.token.address)
        if status_cache is not None:
            status_cache.set(f"peg:{settings.peg.token.name}", peg_price, now)
        peg_event = evaluate_peg_price(
            token_name=settings.peg.token.name,
            price=peg_price,
            threshold_pct=settings.peg.threshold_pct,
            engine=engine,
            now=now,
        )
        if peg_event is not None:
            events.append(peg_event)
        tracker.record_success("peg")
    except Exception as e:
        tracker.record_failure("peg", safe_error_message(e))

    for token in settings.supply.tokens:
        key = f"supply:{token.name}"
        try:
            previous_sample = history.latest_sample(key)
            supply = await fetch_total_supply_async(web3, address=token.address)
            if status_cache is not None:
                status_cache.set(key, supply, now)
            if token.name == settings.apyusd.token.name:
                previous_apyusd_supply = (
                    previous_sample.value if previous_sample else None
                )
                current_apyusd_supply = supply
            supply_event = evaluate_supply(
                token_name=token.name,
                supply=supply,
                threshold_pct=settings.supply.threshold_pct,
                absolute_change_threshold=token.absolute_change_threshold,
                window_minutes=settings.supply.window_minutes,
                history=history,
                engine=engine,
                now=now,
            )
            if supply_event is not None:
                events.append(supply_event)
            tracker.record_success(key)
        except Exception as e:
            tracker.record_failure(key, safe_error_message(e))

    key = f"total_assets:{settings.apyusd.token.name}"
    try:
        previous_sample = history.latest_sample(key)
        total_assets = await fetch_total_assets_async(
            web3, address=settings.apyusd.token.address
        )
        if status_cache is not None:
            status_cache.set(key, total_assets, now)
        previous_apyusd_total_assets = previous_sample.value if previous_sample else None
        current_apyusd_total_assets = total_assets
        total_assets_event = evaluate_total_assets(
            token_name=settings.apyusd.token.name,
            total_assets=total_assets,
            threshold_pct=settings.apyusd.total_assets_change_pct,
            absolute_change_threshold=settings.apyusd.total_assets_absolute_change_threshold,
            window_minutes=settings.apyusd.window_minutes,
            history=history,
            engine=engine,
            now=now,
        )
        if total_assets_event is not None:
            events.append(total_assets_event)
        tracker.record_success(key)
    except Exception as e:
        tracker.record_failure(key, safe_error_message(e))

    try:
        price_apxusd = await fetch_price_apxusd_async(
            web3, address=settings.apyusd.token.address
        )
        if status_cache is not None:
            status_cache.set("apyusd_price_apxusd", price_apxusd, now)
        price_event = evaluate_price_apxusd(
            price_apxusd=price_apxusd,
            threshold_pct=settings.apyusd.price_apxusd_change_pct,
            window_minutes=settings.apyusd.window_minutes,
            history=history,
            engine=engine,
            now=now,
        )
        if price_event is not None:
            events.append(price_event)
        if (
            previous_apyusd_supply is not None
            and current_apyusd_supply is not None
            and previous_apyusd_total_assets is not None
            and current_apyusd_total_assets is not None
        ):
            backing_event = evaluate_supply_asset_backing(
                token_name=settings.apyusd.token.name,
                previous_supply=previous_apyusd_supply,
                current_supply=current_apyusd_supply,
                previous_total_assets=previous_apyusd_total_assets,
                current_total_assets=current_apyusd_total_assets,
                price_apxusd=price_apxusd,
                min_supply_increase=settings.security.apyusd_min_supply_increase,
                min_backing_ratio=settings.security.apyusd_min_backing_ratio,
                engine=engine,
                now=now,
            )
            if backing_event is not None:
                events.append(backing_event)
        tracker.record_success(f"mint_backing:{settings.apyusd.token.name}")
        tracker.record_success("apyusd_price_apxusd")
    except Exception as e:
        tracker.record_failure("apyusd_price_apxusd", safe_error_message(e))
        tracker.record_failure(f"mint_backing:{settings.apyusd.token.name}", safe_error_message(e))

    try:
        events.extend(
            await run_security_event_checks(
                web3=web3,
                settings=settings,
                state=security_state,
                recent_security_events=recent_security_events,
                token_decimals_by_address=token_decimals_by_address,
                engine=engine,
                now=now,
            )
        )
        tracker.record_success("security_events")
    except Exception as e:
        tracker.record_failure("security_events", safe_error_message(e))

    for market in settings.pendle.markets:
        key = f"pendle:{market.name}"
        try:
            snapshot = await fetch_pendle_market(
                session, name=market.name, address=market.address
            )
            if status_cache is not None:
                status_cache.set(key, snapshot, now)
            events.extend(
                evaluate_pendle_market(
                    snapshot=snapshot,
                    liquidity_drop_pct=settings.pendle.liquidity_drop_pct,
                    apy_change_pct=settings.pendle.apy_change_pct,
                    pt_price_change_pct=settings.pendle.pt_price_change_pct,
                    window_minutes=settings.pendle.window_minutes,
                    history=history,
                    engine=engine,
                    now=now,
                )
            )
            tracker.record_success(key)
        except Exception as e:
            tracker.record_failure(key, safe_error_message(e))

    for market in settings.morpho.markets:
        key = f"morpho:{market.name}"
        try:
            snapshot = await fetch_morpho_market(session, web3=web3, market=market)
            if status_cache is not None:
                status_cache.set(key, snapshot, now)
            events.extend(
                evaluate_morpho_market(
                    snapshot=snapshot,
                    total_market_size_drop_pct=(
                        settings.morpho.total_market_size_drop_pct
                    ),
                    total_liquidity_drop_pct=(
                        settings.morpho.total_liquidity_drop_pct
                    ),
                    borrow_rate_change_pct=settings.morpho.borrow_rate_change_pct,
                    oracle_price_change_pct=settings.morpho.oracle_price_change_pct,
                    window_minutes=settings.morpho.window_minutes,
                    history=history,
                    engine=engine,
                    now=now,
                )
            )
            tracker.record_success(key)
        except Exception as e:
            tracker.record_failure(key, safe_error_message(e))

    for pool in settings.curve.pools:
        key = f"curve:{pool.name}"
        try:
            snapshot = await fetch_curve_pool_snapshot_async(web3, pool=pool)
            if status_cache is not None:
                status_cache.set(key, snapshot, now)
            events.extend(
                evaluate_curve_pool(
                    snapshot=snapshot,
                    balance_drop_pct=settings.curve.balance_drop_pct,
                    imbalance_pct=settings.curve.imbalance_pct,
                    virtual_price_change_pct=settings.curve.virtual_price_change_pct,
                    price_deviation_pct=settings.curve.price_deviation_pct,
                    window_minutes=settings.curve.window_minutes,
                    history=history,
                    engine=engine,
                    now=now,
                )
            )
            tracker.record_success(key)
        except Exception as e:
            tracker.record_failure(key, safe_error_message(e))

    for token in settings.commit.tokens:
        key = f"commit:{token.name}"
        try:
            snapshot = await fetch_commit_token_snapshot_async(web3, token=token)
            if status_cache is not None:
                status_cache.set(key, snapshot, now)
            events.extend(
                evaluate_commit_token(
                    snapshot=snapshot,
                    cap_usage_warning_pct=settings.commit.cap_usage_warning_pct,
                    assets_change_pct=settings.commit.assets_change_pct,
                    assets_absolute_change_threshold=token.absolute_change_threshold,
                    window_minutes=settings.commit.window_minutes,
                    history=history,
                    engine=engine,
                    now=now,
                )
            )
            tracker.record_success(key)
        except Exception as e:
            tracker.record_failure(key, safe_error_message(e))

    if settings.yield_distribution.rate_view is not None:
        try:
            snapshot = await fetch_yield_distribution_snapshot_async(
                web3,
                apyusd_address=settings.apyusd.token.address,
                apxusd_address=settings.peg.token.address,
                rate_view_address=settings.yield_distribution.rate_view.address,
            )
            if status_cache is not None:
                status_cache.set("yield_distribution", snapshot, now)
            events.extend(
                evaluate_yield_distribution(
                    snapshot=snapshot,
                    apy_change_pct=settings.yield_distribution.apy_change_pct,
                    annualized_yield_change_pct=(
                        settings.yield_distribution.annualized_yield_change_pct
                    ),
                    unvested_change_pct=settings.yield_distribution.unvested_change_pct,
                    window_minutes=settings.yield_distribution.window_minutes,
                    history=history,
                    engine=engine,
                    now=now,
                )
            )
            tracker.record_success("yield_distribution")
        except Exception as e:
            tracker.record_failure("yield_distribution", safe_error_message(e))

    delivered = await send_events(sender, events, engine=engine, tracker=tracker)
    if delivered:
        security_state.commit_pending()
    if state_store is not None:
        save_runtime_state(
            state_store,
            engine=engine,
            history=history,
            security_state=security_state,
            recent_security_events=recent_security_events,
            tracker=tracker,
        )


async def run_five_minute_checks(
    *,
    session: ClientSession,
    web3: Web3,
    settings: AppConfig,
    env: EnvConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
    sender: TelegramSender,
    tracker: HealthTracker,
    security_state: LogScanState,
    recent_security_events: RecentSecurityEventCache,
    status_cache: StatusCache | None = None,
    state_store: RuntimeStateStore | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []

    for symbol in settings.finnhub.symbols:
        key = f"tradfi:{symbol.symbol}"
        try:
            price = await fetch_strc_price(
                session, api_key=env.finnhub_api_key, symbol=symbol.symbol
            )
            if status_cache is not None:
                status_cache.set(key, price, now)
                if symbol.symbol == settings.finnhub.symbol:
                    status_cache.set("strc:price", price, now)
            strc_event = evaluate_strc_price(
                price=price,
                threshold=symbol.threshold_price,
                engine=engine,
                now=now,
                symbol=symbol.symbol,
            )
            if strc_event is not None:
                events.append(strc_event)
            tracker.record_success(key)
            if symbol.symbol == settings.finnhub.symbol:
                tracker.record_success("strc")
        except Exception as e:
            tracker.record_failure(key, safe_error_message(e))
            if symbol.symbol == settings.finnhub.symbol:
                tracker.record_failure("strc", safe_error_message(e))

    try:
        solvency = await fetch_solvency_snapshot(
            session, url=settings.solvency.accountable_url
        )
        if status_cache is not None:
            status_cache.set("solvency:accountable", solvency, now)
        solvency_event = evaluate_solvency(
            snapshot=solvency,
            warning_collateralization=settings.solvency.warning_collateralization,
            critical_collateralization=settings.solvency.critical_collateralization,
            max_data_age=timedelta(minutes=settings.solvency.max_data_age_minutes),
            engine=engine,
            now=now,
        )
        if solvency_event is not None:
            events.append(solvency_event)
        tracker.record_success("solvency:accountable")
    except Exception as e:
        tracker.record_failure("solvency:accountable", safe_error_message(e))

    await send_events(sender, events, engine=engine, tracker=tracker)
    if state_store is not None:
        save_runtime_state(
            state_store,
            engine=engine,
            history=history,
            security_state=security_state,
            recent_security_events=recent_security_events,
            tracker=tracker,
        )
