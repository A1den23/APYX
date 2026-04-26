from config import load_app_config
from thresholds import build_thresholds_message


def test_build_thresholds_message_lists_status_thresholds() -> None:
    message = build_thresholds_message(load_app_config())

    assert "/status" not in message
    assert "STRC price < $95.00" in message
    assert "liquidity: 30m ↓10%" in message
    assert "ratio < 100.5% 预警" in message
    assert "apxUSD totalSupply: 1m/30m ±10% 或 ±5.00M" in message
    assert "apyUSD totalSupply: 1m/30m ±10% 或 ±2.00M shares" in message
    assert "mint backing: share增量 > 0.10M 且背书 < 99%" in message
