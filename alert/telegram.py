from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

from telegram import Bot, BotCommand, Update

from alert.engine import AlertEvent
from app.errors import safe_error_message

POLL_INTERVAL = 2
POLL_TIMEOUT = 10
MAX_REPLY_CHARS = 3900

TELEGRAM_COMMANDS = [
    BotCommand("status", "查看所有监控指标当前值"),
    BotCommand("thresholds", "查看所有预警阈值"),
    BotCommand("health", "服务自检"),
    BotCommand("strategy", "查看当前监控策略说明"),
    BotCommand("help", "查看命令帮助"),
]


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id
        self._bot_token = bot_token
        self._offset = 0
        self._poll_task: asyncio.Task | None = None
        self._status_fn: Callable[[], Coroutine] | None = None
        self._health_fn: Callable[[], Coroutine] | None = None
        self._strategy_fn: Callable[[], Coroutine] | None = None
        self._thresholds_fn: Callable[[], Coroutine] | None = None
        self._help_fn: Callable[[], Coroutine] | None = None
        self._error_fn: Callable[[str], None] | None = None

    async def send(self, event: AlertEvent) -> None:
        await self._bot.send_message(chat_id=self._chat_id, text=event.telegram_text())

    async def send_text(self, text: str) -> None:
        await self._bot.send_message(chat_id=self._chat_id, text=text)

    async def start_commands(
        self,
        status_fn: Callable[[], Coroutine],
        health_fn: Callable[[], Coroutine],
        strategy_fn: Callable[[], Coroutine],
        thresholds_fn: Callable[[], Coroutine],
        help_fn: Callable[[], Coroutine],
        error_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._status_fn = status_fn
        self._health_fn = health_fn
        self._strategy_fn = strategy_fn
        self._thresholds_fn = thresholds_fn
        self._help_fn = help_fn
        self._error_fn = error_fn
        await self._bot.set_my_commands(TELEGRAM_COMMANDS)
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _poll_loop(self) -> None:
        while True:
            try:
                updates = await self._bot.get_updates(
                    offset=self._offset,
                    timeout=POLL_TIMEOUT,
                    read_timeout=POLL_TIMEOUT + 5,
                    write_timeout=10,
                    connect_timeout=10,
                )
                for update in updates:
                    self._offset = update.update_id + 1
                    await self._dispatch(update)
            except Exception as e:
                safe_error = safe_error_message(e)
                if self._error_fn is not None:
                    self._error_fn(safe_error)
                print(f"Telegram command polling failed: {safe_error}", flush=True)
            await asyncio.sleep(POLL_INTERVAL)

    async def _dispatch(self, update: Update) -> None:
        if update.message is None or update.message.text is None:
            return
        if str(update.effective_chat.id) != self._chat_id:
            return
        command = _command_name(update.message.text)
        if command == "/status" and self._status_fn:
            result = await self._status_fn()
            if isinstance(result, tuple):
                msg, parse_mode = result
            else:
                msg, parse_mode = result, None
            await self._reply_text(update, msg, parse_mode=parse_mode)
        elif command == "/health" and self._health_fn:
            msg = await self._health_fn()
            await self._reply_text(update, msg)
        elif command == "/strategy" and self._strategy_fn:
            msg = await self._strategy_fn()
            await self._reply_text(update, msg)
        elif command == "/thresholds" and self._thresholds_fn:
            msg = await self._thresholds_fn()
            await self._reply_text(update, msg)
        elif command == "/help" and self._help_fn:
            msg = await self._help_fn()
            await self._reply_text(update, msg)

    async def _reply_text(
        self,
        update: Update,
        text: str,
        *,
        parse_mode: str | None = None,
    ) -> None:
        for chunk in _split_reply_text(text):
            await update.message.reply_text(chunk, parse_mode=parse_mode)

    async def stop_commands(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass


def _split_reply_text(text: str) -> list[str]:
    if len(text) <= MAX_REPLY_CHARS:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > MAX_REPLY_CHARS:
        split_at = remaining.rfind("\n", 0, MAX_REPLY_CHARS)
        if split_at <= 0:
            split_at = MAX_REPLY_CHARS
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


def _command_name(text: str) -> str:
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return ""
    command = parts[0].lower()
    if "@" in command:
        command = command.split("@", 1)[0]
    return command
