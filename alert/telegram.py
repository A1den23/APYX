from __future__ import annotations

from telegram import Bot

from alert.engine import AlertEvent


class TelegramSender:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._bot = Bot(token=bot_token)
        self._chat_id = chat_id

    async def send(self, event: AlertEvent) -> None:
        await self._bot.send_message(chat_id=self._chat_id, text=event.telegram_text())
