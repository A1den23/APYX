from help import build_help_message


def test_build_help_message_lists_supported_commands() -> None:
    message = build_help_message()

    assert "/status" in message
    assert "/health" in message
    assert "/strategy" in message
    assert "/thresholds" in message
    assert "/help" in message
