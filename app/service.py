from __future__ import annotations

import asyncio
import signal
from datetime import timedelta, timezone
from urllib.parse import urlsplit

from aiohttp import ClientSession, ClientTimeout
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from web3 import Web3
from web3.providers.base import BaseProvider

from alert.engine import AlertEngine
from alert.telegram import TelegramSender
from commands.health import HealthTracker
from commands.help import build_help_message
from commands.status import build_health_message, build_status_message
from commands.strategy import build_strategy_message
from commands.thresholds import build_thresholds_message
from app.config import AppConfig, EnvConfig, load_app_config, load_env_config
from app.errors import safe_error_message
from app.history import RollingMetricHistory
from app.jobs import run_five_minute_checks, run_one_minute_checks
from monitors.security_events import LogScanState, RecentSecurityEventCache
from app.runtime_state import RuntimeState, RuntimeStateStore
from app.status_cache import StatusCache


RPC_TIMEOUT_SECONDS = 20
JOB_MISFIRE_GRACE_SECONDS = 30
RETRYABLE_RPC_STATUS_CODES = (429, 502, 503, 504)


def _rpc_url_label(rpc_url: str) -> str:
    parsed = urlsplit(rpc_url)
    return parsed.netloc or "<rpc-endpoint>"


def _is_retryable_rpc_error(error: BaseException | str) -> bool:
    message = str(error)
    retryable_markers = (
        "Too Many Requests",
        "rate limit",
        "rate-limit",
        "timeout",
        "timed out",
        "ConnectionError",
        "ConnectTimeout",
        "ReadTimeout",
    )
    return any(str(status) in message for status in RETRYABLE_RPC_STATUS_CODES) or any(
        marker.lower() in message.lower() for marker in retryable_markers
    )


def _is_retryable_rpc_response(response: object) -> bool:
    if not isinstance(response, dict):
        return False
    error = response.get("error")
    if not isinstance(error, dict):
        return False
    code = error.get("code")
    message = str(error.get("message", ""))
    return code in RETRYABLE_RPC_STATUS_CODES or _is_retryable_rpc_error(message)


class FailoverHTTPProvider(BaseProvider):
    def __init__(self, rpc_urls: list[str], *, request_kwargs: dict[str, int]) -> None:
        if not rpc_urls:
            raise ValueError("At least one Ethereum RPC URL is required")
        self._providers = [
            Web3.HTTPProvider(rpc_url, request_kwargs=request_kwargs)
            for rpc_url in rpc_urls
        ]
        self._rpc_urls = rpc_urls
        self._active_index = 0

    @property
    def url(self) -> str:
        return self._rpc_urls[self._active_index]

    @property
    def endpoint_uri(self) -> str:
        return self.url

    def _activate(self, index: int, *, reason: str | None = None) -> None:
        if index == self._active_index:
            return
        previous_url = self.url
        self._active_index = index
        message = (
            f"ETH RPC switched from {_rpc_url_label(previous_url)} "
            f"to {_rpc_url_label(self.url)}"
        )
        if reason:
            message = f"{message}: {reason}"
        print(message, flush=True)

    def activate_next_endpoint(self, *, reason: str | None = None) -> None:
        if len(self._providers) == 1:
            return
        self._activate((self._active_index + 1) % len(self._providers), reason=reason)

    def is_connected(self, show_traceback: bool = False) -> bool:
        for offset in range(len(self._providers)):
            index = (self._active_index + offset) % len(self._providers)
            provider = self._providers[index]
            try:
                is_connected = provider.is_connected(show_traceback=show_traceback)
            except TypeError:
                is_connected = provider.is_connected()
            except Exception:
                is_connected = False
            if is_connected:
                self._activate(index)
                return True
        return False

    def make_request(self, method: str, params: object) -> object:
        last_error: BaseException | None = None
        start_index = self._active_index
        for offset in range(len(self._providers)):
            index = (start_index + offset) % len(self._providers)
            provider = self._providers[index]
            try:
                response = provider.make_request(method, params)
            except Exception as e:
                if len(self._providers) > 1 and _is_retryable_rpc_error(e):
                    last_error = e
                    self._activate(
                        (index + 1) % len(self._providers),
                        reason=f"{method} failed with retryable RPC error",
                    )
                    continue
                raise

            if len(self._providers) > 1 and _is_retryable_rpc_response(response):
                last_error = RuntimeError(str(response.get("error")))
                self._activate(
                    (index + 1) % len(self._providers),
                    reason=f"{method} returned retryable RPC error",
                )
                continue

            self._activate(index)
            return response

        if last_error is not None:
            raise last_error
        raise RuntimeError("No Ethereum RPC endpoint returned a response")


def _is_web3_connected(web3: Web3) -> bool:
    try:
        return bool(web3.is_connected())
    except Exception:
        return False


def _build_web3(env: EnvConfig) -> Web3:
    rpc_urls = [env.eth_rpc_url]
    if env.eth_rpc_fallback_url:
        rpc_urls.append(env.eth_rpc_fallback_url)

    provider = FailoverHTTPProvider(
        rpc_urls,
        request_kwargs={"timeout": RPC_TIMEOUT_SECONDS},
    )
    web3 = Web3(provider)
    if env.eth_rpc_fallback_url and not _is_web3_connected(web3):
        provider.activate_next_endpoint(reason="primary RPC unavailable at startup")
    return web3


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
    web3 = _build_web3(env)

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
