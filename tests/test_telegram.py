import asyncio

import pytest

from alert.telegram import TelegramSender


class FailingBot:
    async def get_updates(self, **kwargs):
        raise RuntimeError("poll failed token=secret")


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
