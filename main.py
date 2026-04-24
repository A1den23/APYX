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
from history import RollingMetricHistory
from monitors.peg import evaluate_peg_price, fetch_peg_price
from monitors.pendle import evaluate_pendle_market, fetch_pendle_market
from monitors.strc_price import evaluate_strc_price, fetch_strc_price
from monitors.supply import evaluate_supply, fetch_total_supply
from monitors.tvl import evaluate_tvl, fetch_tvl


async def send_events(sender: TelegramSender, events: list[AlertEvent]) -> None:
    for event in events:
        await sender.send(event)


async def run_one_minute_checks(
    *,
    session: ClientSession,
    web3: Web3,
    settings: AppConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
    sender: TelegramSender,
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []

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

    for token in settings.supply.tokens:
        supply = fetch_total_supply(web3, address=token.address)
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

    await send_events(sender, events)


async def run_five_minute_checks(
    *,
    session: ClientSession,
    settings: AppConfig,
    env: EnvConfig,
    history: RollingMetricHistory,
    engine: AlertEngine,
    sender: TelegramSender,
) -> None:
    now = datetime.now(timezone.utc)
    events: list[AlertEvent] = []

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

    for market in settings.pendle.markets:
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

    for token in settings.tvl.tokens:
        tvl = await fetch_tvl(session, url=token.url)
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

    await send_events(sender, events)


async def run_service(*, once: bool) -> None:
    settings = load_app_config()
    env = load_env_config()
    engine = AlertEngine(cooldown=timedelta(minutes=settings.alert.cooldown_minutes))
    history = RollingMetricHistory()
    sender = TelegramSender(env.telegram_bot_token, env.telegram_chat_id)
    web3 = Web3(Web3.HTTPProvider(env.eth_rpc_url))

    async with ClientSession() as session:
        if once:
            await run_one_minute_checks(
                session=session,
                web3=web3,
                settings=settings,
                history=history,
                engine=engine,
                sender=sender,
            )
            await run_five_minute_checks(
                session=session,
                settings=settings,
                env=env,
                history=history,
                engine=engine,
                sender=sender,
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
            },
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            run_five_minute_checks,
            "interval",
            minutes=5,
            kwargs={
                "session": session,
                "settings": settings,
                "env": env,
                "history": history,
                "engine": engine,
                "sender": sender,
            },
            max_instances=1,
            coalesce=True,
        )
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
