from errors import safe_error_message


def test_safe_error_message_redacts_query_tokens() -> None:
    message = (
        "401, message='Unauthorized', url="
        "URL('https://finnhub.io/api/v1/quote?symbol=STRC&token=secret-token')"
    )

    safe = safe_error_message(message)

    assert "secret-token" not in safe
    assert "token=<redacted>" in safe


def test_safe_error_message_redacts_telegram_bot_tokens() -> None:
    safe = safe_error_message("failed for 123456789:ABCdef_1234567890-abcdefghi")

    assert "123456789:ABCdef" not in safe
    assert "<redacted-telegram-token>" in safe
