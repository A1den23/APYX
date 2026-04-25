from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

from telegram import Bot, Update

from alert.engine import AlertEvent
from errors import safe_error_message

POLL_INTERVAL = 2
POLL_TIMEOUT = 10


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id
        self._bot_token = bot_token
        self._offset = 0
        self._poll_task: asyncio.Task | None = None
        self._status_fn: Callable[[], Coroutine] | None = None
        self._health_fn: Callable[[], Coroutine] | None = None
        self._error_fn: Callable[[str], None] | None = None

    async def send(self, event: AlertEvent) -> None:
        await self._bot.send_message(chat_id=self._chat_id, text=event.telegram_text())

    async def start_commands(
        self,
        status_fn: Callable[[], Coroutine],
        health_fn: Callable[[], Coroutine],
        error_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._status_fn = status_fn
        self._health_fn = health_fn
        self._error_fn = error_fn
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
        text = update.message.text.strip()
        if text == "/status" and self._status_fn:
            result = await self._status_fn()
            if isinstance(result, tuple):
                msg, parse_mode = result
            else:
                msg, parse_mode = result, None
            await update.message.reply_text(msg, parse_mode=parse_mode)
        elif text == "/health" and self._health_fn:
            msg = await self._health_fn()
            await update.message.reply_text(msg)

    async def stop_commands(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
