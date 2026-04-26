import asyncio

from commands.health import HealthTracker
from service import send_lifecycle_notification


class RecordingSender:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_text(self, text: str) -> None:
        self.messages.append(text)


class FailingTextSender:
    async def send_text(self, text: str) -> None:
        raise RuntimeError("send failed token=secret")


def test_send_lifecycle_notification_sends_plain_message() -> None:
    sender = RecordingSender()
    tracker = HealthTracker()

    asyncio.run(
        send_lifecycle_notification(
            sender,
            tracker=tracker,
            title="APYX Monitor Started",
            body="Docker container is running.",
        )
    )

    assert sender.messages == [
        "[APYX SYSTEM] APYX Monitor Started\nDocker container is running."
    ]


def test_send_lifecycle_notification_records_safe_failure() -> None:
    tracker = HealthTracker()

    asyncio.run(
        send_lifecycle_notification(
            FailingTextSender(),
            tracker=tracker,
            title="APYX Monitor Stopping",
            body="Docker container received shutdown signal.",
        )
    )

    errors = [m.last_error for m in tracker.snapshot().values() if m.last_error]
    assert errors
    assert "token=<redacted>" in errors[0]
    assert "secret" not in errors[0]
