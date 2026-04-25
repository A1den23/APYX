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
from monitors.apyusd import (
    evaluate_price_apxusd,
    evaluate_total_assets,
    fetch_price_apxusd_async,
    fetch_total_assets_async,
)
from monitors.peg import evaluate_peg_price, fetch_peg_price
from monitors.pendle import evaluate_pendle_market, fetch_pendle_market
from monitors.strc_price import evaluate_strc_price, fetch_strc_price
from monitors.supply import evaluate_supply, fetch_total_supply_async
from monitors.tvl import evaluate_tvl, fetch_tvl_for_token


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
    tracker.register(f"total_assets:{settings.apyusd.token.name}", 300)
    tracker.register("apyusd_price_apxusd", 300)
    tracker.register("telegram_commands", 0)
    for market in settings.pendle.markets:
        tracker.register(f"pendle:{market.name}", 300)
    for token in settings.tvl.tokens:
        tracker.register(f"tvl:{token.name}", 300)


async def run_one_minute_checks(
    *,
    session: ClientSession,
    web3: Web3,
    settings: AppConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
    sender: TelegramSender,
    tracker: HealthTracker,
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []

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
            supply = await fetch_total_supply_async(web3, address=token.address)
            supply_event = evaluate_supply(
                token_name=token.name,
                supply=supply,
                threshold_pct=settings.supply.threshold_pct,
                history=history,
                engine=engine,
                now=now,
            )
            if supply_event is not None:
                events.append(supply_event)
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

    for token in settings.tvl.tokens:
        key = f"tvl:{token.name}"
        try:
            tvl = await fetch_tvl_for_token(session, web3, token)
            tvl_event = evaluate_tvl(
                token_name=token.name,
                tvl=tvl,
                threshold_pct=settings.tvl.threshold_pct,
                window_minutes=settings.tvl.window_minutes,
                history=history,
                engine=engine,
                now=now,
            )
            if tvl_event is not None:
                events.append(tvl_event)
            tracker.record_success(key)
        except Exception as e:
            tracker.record_failure(key, str(e))

    key = f"total_assets:{settings.apyusd.token.name}"
    try:
        total_assets = await fetch_total_assets_async(web3, address=settings.apyusd.token.address)
        total_assets_event = evaluate_total_assets(
            token_name=settings.apyusd.token.name,
            total_assets=total_assets,
            threshold_pct=settings.apyusd.total_assets_change_pct,
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
        tracker.record_success("apyusd_price_apxusd")
    except Exception as e:
        tracker.record_failure("apyusd_price_apxusd", str(e))

    await send_events(sender, events, engine=engine, tracker=tracker)


async def run_service(*, once: bool) -> None:
    settings = load_app_config()
    env = load_env_config()
    engine = AlertEngine(cooldown=timedelta(minutes=settings.alert.cooldown_minutes))
    history = RollingMetricHistory()
    tracker = HealthTracker()
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
