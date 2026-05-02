from app.config import load_app_config
from commands.thresholds import build_thresholds_message


def test_build_thresholds_message_lists_status_thresholds() -> None:
    message = build_thresholds_message(load_app_config())

    assert "/status" not in message
    assert "频率: 每 5min" in message
    assert "频率: 每 1min | 窗口: 30min" in message
    assert "链上指标频率: 每 1min | 窗口: 30min" in message
    assert "security events: 每 1min 扫描区块日志" in message
    assert "STRC price < $95.00" in message
    assert "liquidity: 1m/30m ↓10%" in message
    assert "oracle price: 1m/30m ±2%" in message
    assert "apyUSD/apxUSD price: 相对 vault priceAPXUSD 偏离 > 1.50%" in message
    assert "ratio < 100.1% 预警" in message
    assert "updated > 30min 预警" in message
    assert "apxUSD totalSupply: 1m/30m ±10% 或 ±5.00M" in message
    assert "apyUSD totalSupply: 1m/30m ±10% 或 ±2.00M shares" in message
    assert "mint backing: share增量 > 0.10M 且背书 < 99%" in message
