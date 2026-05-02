from __future__ import annotations

import asyncio
import signal
from datetime import timedelta, timezone

from aiohttp import ClientSession, ClientTimeout
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from web3 import Web3

from alert.engine import AlertEngine
from alert.telegram import TelegramSender
from commands.health import HealthTracker
from commands.help import build_help_message
from commands.status import build_health_message, build_status_message
from commands.strategy import build_strategy_message
from commands.thresholds import build_thresholds_message
from app.config import AppConfig, load_app_config, load_env_config
from app.errors import safe_error_message
from app.history import RollingMetricHistory
from app.jobs import run_five_minute_checks, run_one_minute_checks
from monitors.security_events import LogScanState, RecentSecurityEventCache
from app.runtime_state import RuntimeState, RuntimeStateStore
from app.status_cache import StatusCache


RPC_TIMEOUT_SECONDS = 20
JOB_MISFIRE_GRACE_SECONDS = 30


async def send_lifecycle_notification(
    sender: TelegramSender,
    *,
    tracker: HealthTracker,
    title: str,
    body: str,
) -> None:
    try:
        await sender.send_text(f"[APYX SYSTEM] {title}\n{body}")
    except Exception as e:
        safe_error = safe_error_message(e)
        tracker.record_failure("lifecycle_notifications", safe_error)
        print(f"Failed to send lifecycle notification: {safe_error}", flush=True)


def _register_monitors(tracker: HealthTracker, settings: AppConfig) -> None:
    tracker.register("peg", 60)
    for token in settings.supply.tokens:
        tracker.register(f"supply:{token.name}", 60)
    tracker.register("strc", 300)
    for symbol in settings.finnhub.symbols:
        tracker.register(f"tradfi:{symbol.symbol}", 300)
    tracker.register(f"total_assets:{settings.apyusd.token.name}", 60)
    tracker.register("apyusd_price_apxusd", 60)
    tracker.register(f"mint_backing:{settings.apyusd.token.name}", 60)
    tracker.register("security_events", 60)
    tracker.register("solvency:accountable", 300)
    if settings.yield_distribution.rate_view is not None:
        tracker.register("yield_distribution", 60)
    tracker.register("lifecycle_notifications", 0)
    tracker.register("telegram_commands", 0)
    for market in settings.pendle.markets:
        tracker.register(f"pendle:{market.name}", 60)
    for market in settings.morpho.markets:
        tracker.register(f"morpho:{market.name}", 60)
    for pool in settings.curve.pools:
        tracker.register(f"curve:{pool.name}", 60)
    for token in settings.commit.tokens:
        tracker.register(f"commit:{token.name}", 60)


def _default_runtime_state(settings: AppConfig) -> RuntimeState:
    return RuntimeState(
        alert_engine=AlertEngine(
            cooldown=timedelta(minutes=settings.alert.cooldown_minutes)
        ),
        history=RollingMetricHistory(),
        security_state=LogScanState(
            start_block_lookback=settings.security.start_block_lookback,
            max_blocks_per_scan=settings.security.max_blocks_per_scan,
        ),
        recent_security_events=RecentSecurityEventCache(
            hold_duration=timedelta(minutes=settings.security.recent_event_hold_minutes)
        ),
    )


def _load_runtime_state(
    store: RuntimeStateStore,
    *,
    settings: AppConfig,
    tracker: HealthTracker,
) -> RuntimeState:
    if not store.exists():
        return _default_runtime_state(settings)
    try:
        return store.load()
    except Exception as e:
        tracker.record_failure("runtime_state", safe_error_message(e))
        return _default_runtime_state(settings)


async def run_service(*, once: bool) -> None:
    settings = load_app_config()
    env = load_env_config()
    tracker = HealthTracker()
    state_store = RuntimeStateStore(settings.runtime.state_path)
    runtime_state = _load_runtime_state(
        state_store,
        settings=settings,
        tracker=tracker,
    )
    engine = runtime_state.alert_engine
    history = runtime_state.history
    security_state = runtime_state.security_state
    recent_security_events = runtime_state.recent_security_events
    token_decimals_by_address: dict[str, int] = {}
    status_cache = StatusCache()
    _register_monitors(tracker, settings)
    tracker.register("runtime_state", 0)
    sender = TelegramSender(env.telegram_bot_token, env.telegram_chat_id)
    web3 = Web3(
        Web3.HTTPProvider(
            env.eth_rpc_url,
            request_kwargs={"timeout": RPC_TIMEOUT_SECONDS},
        )
    )

    timeout = ClientTimeout(total=settings.runtime.http_timeout_seconds)
    async with ClientSession(timeout=timeout) as session:
        common_kwargs = {
            "session": session,
            "web3": web3,
            "settings": settings,
            "history": history,
            "engine": engine,
            "sender": sender,
            "tracker": tracker,
            "security_state": security_state,
            "recent_security_events": recent_security_events,
            "status_cache": status_cache,
            "state_store": state_store,
        }
        common_one_minute_kwargs = {
            **common_kwargs,
            "token_decimals_by_address": token_decimals_by_address,
        }
        common_five_minute_kwargs = {
            **common_kwargs,
            "env": env,
        }
        if once:
            await run_one_minute_checks(**common_one_minute_kwargs)
            await run_five_minute_checks(**common_five_minute_kwargs)
            return

        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass

        scheduler = AsyncIOScheduler(timezone=timezone.utc)
        scheduler.add_job(
            run_one_minute_checks,
            "interval",
            minutes=1,
            kwargs=common_one_minute_kwargs,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=JOB_MISFIRE_GRACE_SECONDS,
        )
        scheduler.add_job(
            run_five_minute_checks,
            "interval",
            minutes=5,
            kwargs=common_five_minute_kwargs,
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
                    status_cache=status_cache,
                ),
                health_fn=lambda: build_health_message(
                    tracker=tracker,
                    engine=engine,
                ),
                strategy_fn=lambda: asyncio.to_thread(build_strategy_message),
                thresholds_fn=lambda: asyncio.to_thread(
                    build_thresholds_message, settings
                ),
                help_fn=lambda: asyncio.to_thread(build_help_message),
                error_fn=lambda error: tracker.record_failure(
                    "telegram_commands", error
                ),
            )
            print("Telegram command listener started", flush=True)
        except Exception as e:
            print(f"Failed to start command listener: {safe_error_message(e)}", flush=True)
        scheduler.start()
        await send_lifecycle_notification(
            sender,
            tracker=tracker,
            title="APYX Monitor Started",
            body="Docker container is running and monitors are scheduled.",
        )
        await stop_event.wait()
        await send_lifecycle_notification(
            sender,
            tracker=tracker,
            title="APYX Monitor Stopping",
            body="Docker container received shutdown signal.",
        )
        scheduler.shutdown(wait=False)
        await sender.stop_commands()
