from commands.strategy import build_strategy_message


def test_build_strategy_message_reads_strategy_document() -> None:
    message = build_strategy_message()

    assert "📋 监控策略说明" in message
    assert "APYX 稳定币与 Pendle 市场安全监控" in message
    assert "链上安全事件" in message
