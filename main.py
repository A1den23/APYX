from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from aiohttp import ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from web3 import Web3

from alert.engine import AlertEngine, AlertEvent
from alert.telegram import TelegramSender
from config import AppConfig, EnvConfig, load_app_config, load_env_config
from errors import safe_error_message
from health import HealthTracker
from history import RollingMetricHistory
from status import build_status_message, build_health_message
from strategy import build_strategy_message
from monitors.apyusd import (
    evaluate_supply_asset_backing,
    evaluate_price_apxusd,
    evaluate_total_assets,
    fetch_price_apxusd_async,
    fetch_total_assets_async,
)
from monitors.peg import evaluate_peg_price, fetch_peg_price
from monitors.pendle import evaluate_pendle_market, fetch_pendle_market
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
from monitors.strc_price import evaluate_strc_price, fetch_strc_price
from monitors.supply import evaluate_supply, fetch_total_supply_async


RPC_TIMEOUT_SECONDS = 20
JOB_MISFIRE_GRACE_SECONDS = 30


async def send_events(
    sender: TelegramSender,
    events: list[AlertEvent],
    *,
    engine: AlertEngine,
    tracker: HealthTracker,
) -> None:
    for event in events:
        try:
            await sender.send(event)
        except Exception as e:
            engine.rollback(event)
            safe_error = safe_error_message(e)
            tracker.record_failure(f"alert:{event.metric_key or event.kind}", safe_error)
            print(
                f"Failed to send alert {event.metric_key or event.kind}: {safe_error}",
                flush=True,
            )


def _register_monitors(tracker: HealthTracker, settings: AppConfig) -> None:
    tracker.register("peg", 60)
    for token in settings.supply.tokens:
        tracker.register(f"supply:{token.name}", 60)
    tracker.register("strc", 300)
    tracker.register(f"total_assets:{settings.apyusd.token.name}", 60)
    tracker.register("apyusd_price_apxusd", 60)
    tracker.register(f"mint_backing:{settings.apyusd.token.name}", 60)
    tracker.register("security_events", 60)
    tracker.register("telegram_commands", 0)
    for market in settings.pendle.markets:
        tracker.register(f"pendle:{market.name}", 60)


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
        addresses=list(contract_names.keys()),
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
    state.mark_scanned(to_block)
    return events


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
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []
    previous_apyusd_supply = None
    current_apyusd_supply = None
    previous_apyusd_total_assets = None
    current_apyusd_total_assets = None

    try:
        peg_price = await fetch_peg_price(session, address=settings.peg.token.address)
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
        tracker.record_failure("peg", str(e))

    for token in settings.supply.tokens:
        key = f"supply:{token.name}"
        try:
            previous_sample = history.latest_sample(key)
            supply = await fetch_total_supply_async(web3, address=token.address)
            if token.name == settings.apyusd.token.name:
                previous_apyusd_supply = previous_sample.value if previous_sample else None
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
            tracker.record_failure(key, str(e))

    key = f"total_assets:{settings.apyusd.token.name}"
    try:
        previous_sample = history.latest_sample(key)
        total_assets = await fetch_total_assets_async(web3, address=settings.apyusd.token.address)
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
        tracker.record_failure(key, str(e))

    try:
        price_apxusd = await fetch_price_apxusd_async(
            web3, address=settings.apyusd.token.address
        )
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
        tracker.record_failure("apyusd_price_apxusd", str(e))
        tracker.record_failure(f"mint_backing:{settings.apyusd.token.name}", str(e))

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
        tracker.record_failure("security_events", str(e))

    for market in settings.pendle.markets:
        key = f"pendle:{market.name}"
        try:
            snapshot = await fetch_pendle_market(
                session, name=market.name, address=market.address
            )
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
            tracker.record_failure(key, str(e))

    await send_events(sender, events, engine=engine, tracker=tracker)


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
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []

    try:
        strc_price = await fetch_strc_price(
            session, api_key=env.finnhub_api_key, symbol=settings.finnhub.symbol
        )
        strc_event = evaluate_strc_price(
            price=strc_price,
            threshold=settings.finnhub.threshold_price,
            engine=engine,
            now=now,
        )
        if strc_event is not None:
            events.append(strc_event)
        tracker.record_success("strc")
    except Exception as e:
        tracker.record_failure("strc", str(e))

    await send_events(sender, events, engine=engine, tracker=tracker)


async def run_service(*, once: bool) -> None:
    settings = load_app_config()
    env = load_env_config()
    engine = AlertEngine(cooldown=timedelta(minutes=settings.alert.cooldown_minutes))
    history = RollingMetricHistory()
    tracker = HealthTracker()
    security_state = LogScanState(
        start_block_lookback=settings.security.start_block_lookback,
        max_blocks_per_scan=settings.security.max_blocks_per_scan,
    )
    recent_security_events = RecentSecurityEventCache(
        hold_duration=timedelta(minutes=settings.security.recent_event_hold_minutes)
    )
    token_decimals_by_address: dict[str, int] = {}
    _register_monitors(tracker, settings)
    sender = TelegramSender(env.telegram_bot_token, env.telegram_chat_id)
    web3 = Web3(
        Web3.HTTPProvider(
            env.eth_rpc_url,
            request_kwargs={"timeout": RPC_TIMEOUT_SECONDS},
        )
    )

    async with ClientSession() as session:
        if once:
            await run_one_minute_checks(
                session=session,
                web3=web3,
                settings=settings,
                history=history,
                engine=engine,
                sender=sender,
                tracker=tracker,
                security_state=security_state,
                recent_security_events=recent_security_events,
                token_decimals_by_address=token_decimals_by_address,
            )
            await run_five_minute_checks(
                session=session,
                web3=web3,
                settings=settings,
                env=env,
                history=history,
                engine=engine,
                sender=sender,
                tracker=tracker,
            )
            return

        scheduler = AsyncIOScheduler(timezone=timezone.utc)
        scheduler.add_job(
            run_one_minute_checks,
            "interval",
            minutes=1,
            kwargs={
                "session": session,
                "web3": web3,
                "settings": settings,
                "history": history,
                "engine": engine,
                "sender": sender,
                "tracker": tracker,
                "security_state": security_state,
                "recent_security_events": recent_security_events,
                "token_decimals_by_address": token_decimals_by_address,
            },
            max_instances=1,
            coalesce=True,
            misfire_grace_time=JOB_MISFIRE_GRACE_SECONDS,
        )
        scheduler.add_job(
            run_five_minute_checks,
            "interval",
            minutes=5,
            kwargs={
                "session": session,
                "web3": web3,
                "settings": settings,
                "env": env,
                "history": history,
                "engine": engine,
                "sender": sender,
                "tracker": tracker,
            },
            max_instances=1,
            coalesce=True,
            misfire_grace_time=JOB_MISFIRE_GRACE_SECONDS,
        )
        try:
            await sender.start_commands(
                status_fn=lambda: build_status_message(
                    session=session,
                    web3=web3,
                    settings=settings,
                    env=env,
                    history=history,
                    engine=engine,
                ),
                health_fn=lambda: build_health_message(
                    tracker=tracker,
                    engine=engine,
                ),
                strategy_fn=lambda: asyncio.to_thread(build_strategy_message),
                error_fn=lambda error: tracker.record_failure(
                    "telegram_commands", error
                ),
            )
            print("Telegram command listener started", flush=True)
        except Exception as e:
            print(f"Failed to start command listener: {safe_error_message(e)}", flush=True)
        scheduler.start()
        await asyncio.Event().wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APYX stablecoin and Pendle pool monitor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one 1-minute cycle and one 5-minute cycle, then exit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_service(once=args.once))
