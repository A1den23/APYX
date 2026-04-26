import asyncio

import pytest

from alert.telegram import TelegramSender


class FailingBot:
    async def get_updates(self, **kwargs):
        raise RuntimeError("poll failed token=secret")


class FakeChat:
    id = 123


class FakeMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies: list[tuple[str, str | None]] = []

    async def reply_text(self, text: str, parse_mode: str | None = None) -> None:
        self.replies.append((text, parse_mode))


class FakeUpdate:
    def __init__(self, text: str) -> None:
        self.message = FakeMessage(text)
        self.effective_chat = FakeChat()


def test_poll_loop_records_sanitized_errors(monkeypatch) -> None:
    sender = TelegramSender("token", "123")
    sender._bot = FailingBot()
    errors: list[str] = []
    sender._error_fn = errors.append

    async def stop_after_error(interval):
        raise asyncio.CancelledError

    monkeypatch.setattr("alert.telegram.asyncio.sleep", stop_after_error)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sender._poll_loop())

    assert errors
    assert "token=<redacted>" in errors[0]
    assert "secret" not in errors[0]


def test_dispatch_strategy_command_replies_with_strategy_text() -> None:
    sender = TelegramSender("token", "123")
    update = FakeUpdate("/strategy")

    async def strategy_fn() -> str:
        return "APYX strategy"

    sender._strategy_fn = strategy_fn

    asyncio.run(sender._dispatch(update))

    assert update.message.replies == [("APYX strategy", None)]


def test_dispatch_strategy_command_splits_long_strategy_text() -> None:
    sender = TelegramSender("token", "123")
    update = FakeUpdate("/strategy")

    async def strategy_fn() -> str:
        return "A" * 4100

    sender._strategy_fn = strategy_fn

    asyncio.run(sender._dispatch(update))

    assert len(update.message.replies) == 2
    assert "".join(reply for reply, _parse_mode in update.message.replies) == "A" * 4100
    assert all(len(reply) <= 3900 for reply, _parse_mode in update.message.replies)


def test_dispatch_status_keeps_parse_mode_when_splitting_long_text() -> None:
    sender = TelegramSender("token", "123")
    update = FakeUpdate("/status")

    async def status_fn() -> tuple[str, str]:
        return "B" * 4100, "HTML"

    sender._status_fn = status_fn

    asyncio.run(sender._dispatch(update))

    assert len(update.message.replies) == 2
    assert update.message.replies[0][1] == "HTML"
    assert update.message.replies[1][1] == "HTML"


def test_dispatch_help_command_replies_with_help_text() -> None:
    sender = TelegramSender("token", "123")
    update = FakeUpdate("/help")

    async def help_fn() -> str:
        return "APYX help"

    sender._help_fn = help_fn

    asyncio.run(sender._dispatch(update))

    assert update.message.replies == [("APYX help", None)]
