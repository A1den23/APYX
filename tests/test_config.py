from pathlib import Path

import pytest

from app.config import load_app_config, load_env_config


def write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
finnhub:
  symbol: "STRC"
  threshold_price: 95.0
  symbols:
    - symbol: "STRC"
      threshold_price: 95.0
    - symbol: "SATA"
      threshold_price: 95.0
peg:
  token:
    name: "apxUSD"
    address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
  threshold_pct: 0.003
pendle:
  markets:
    - name: "apxUSD"
      address: "0x50dce085af29caba28f7308bea57c4043757b491"
  liquidity_drop_pct: 0.10
  apy_change_pct: 0.10
  pt_price_change_pct: 0.10
  window_minutes: 30
curve:
  pools:
    - name: "apxUSD-USDC"
      address: "0xE1B96555BbecA40E583BbB41a11C68Ca4706A414"
      coins:
        - name: "apxUSD"
          address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
        - name: "USDC"
          address: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    - name: "apyUSD-apxUSD"
      address: "0xe41be7b340f7c2eda4da1e99b42ee1b228b526b7"
      metrics:
        - "total_value"
        - "apyusd_apxusd_price"
        - "value_adjusted_imbalance"
        - "virtual_price"
      price_deviation_pct: 0.01
      coins:
        - name: "apyUSD"
          address: "0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A"
        - name: "apxUSD"
          address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
  balance_drop_pct: 0.10
  imbalance_pct: 0.20
  virtual_price_change_pct: 0.01
  price_deviation_pct: 0.003
  window_minutes: 30
commit:
  tokens:
    - name: "apxUSD Commit"
      address: "0x17122d869d981d184118B301313BCD157c79871e"
      asset: "apxUSD"
      absolute_change_threshold: 5000000
  cap_usage_warning_pct: 0.90
  assets_change_pct: 0.10
  assets_absolute_change_threshold: 5000000
  window_minutes: 30
yield_distribution:
  rate_view:
    name: "ApyUSDRateView"
    address: "0xCABa36EDE2C08e16F3602e8688a8bE94c1B4e484"
  apy_change_pct: 0.10
  annualized_yield_change_pct: 0.10
  unvested_change_pct: 0.20
  window_minutes: 30
supply:
  tokens:
    - name: "apxUSD"
      address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
      absolute_change_threshold: 5000000
  threshold_pct: 0.10
  window_minutes: 30
apyusd:
  token:
    name: "apyUSD"
    address: "0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A"
  total_assets_change_pct: 0.10
  total_assets_absolute_change_threshold: 5000000
  price_apxusd_change_pct: 0.05
  window_minutes: 30
security:
  start_block_lookback: 25
  max_blocks_per_scan: 100
  recent_event_hold_minutes: 60
  apyusd_min_supply_increase: 100000
  apyusd_min_backing_ratio: 0.99
  contracts:
    - name: "UnlockToken"
      address: "0x93775E2dFa4e716c361A1f53F212c7AE031BF4e6"
solvency:
  accountable_url: "https://api.accountable.apyx.fi/dashboard"
  warning_collateralization: 1.001
  critical_collateralization: 1.0
  max_data_age_minutes: 30
alert:
  cooldown_minutes: 1
runtime:
  state_path: "/tmp/apyx-state.json"
  http_timeout_seconds: 12
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_load_app_config_parses_thresholds_and_addresses(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)

    settings = load_app_config(config_path)

    assert settings.finnhub.symbol == "STRC"
    assert settings.finnhub.threshold_price == 95.0
    assert [symbol.symbol for symbol in settings.finnhub.symbols] == ["STRC", "SATA"]
    assert settings.peg.token.name == "apxUSD"
    assert settings.peg.threshold_pct == 0.003
    assert settings.pendle.markets[0].address == "0x50dce085af29caba28f7308bea57c4043757b491"
    assert settings.pendle.window_minutes == 30
    assert settings.curve.pools[0].name == "apxUSD-USDC"
    assert settings.curve.pools[0].coins[1].name == "USDC"
    assert settings.curve.pools[1].name == "apyUSD-apxUSD"
    assert settings.curve.pools[1].metrics == (
        "total_value",
        "apyusd_apxusd_price",
        "value_adjusted_imbalance",
        "virtual_price",
    )
    assert settings.curve.pools[1].price_deviation_pct == 0.01
    assert settings.curve.balance_drop_pct == 0.10
    assert settings.commit.tokens[0].name == "apxUSD Commit"
    assert settings.commit.cap_usage_warning_pct == 0.90
    assert settings.yield_distribution.rate_view.name == "ApyUSDRateView"
    assert settings.yield_distribution.apy_change_pct == 0.10
    assert settings.yield_distribution.annualized_yield_change_pct == 0.10
    assert settings.supply.tokens[0].absolute_change_threshold == 5000000
    assert settings.supply.window_minutes == 30
    assert settings.apyusd.total_assets_absolute_change_threshold == 5000000
    assert settings.apyusd.token.address == "0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A"
    assert settings.apyusd.total_assets_change_pct == 0.10
    assert settings.apyusd.price_apxusd_change_pct == 0.05
    assert settings.apyusd.window_minutes == 30
    assert settings.security.start_block_lookback == 25
    assert settings.security.max_blocks_per_scan == 100
    assert settings.security.recent_event_hold_minutes == 60
    assert settings.security.apyusd_min_supply_increase == 100000
    assert settings.security.apyusd_min_backing_ratio == 0.99
    assert settings.security.contracts[0].name == "UnlockToken"
    assert settings.solvency.accountable_url == "https://api.accountable.apyx.fi/dashboard"
    assert settings.solvency.warning_collateralization == 1.001
    assert settings.solvency.critical_collateralization == 1.0
    assert settings.solvency.max_data_age_minutes == 30
    assert settings.alert.cooldown_minutes == 1
    assert settings.runtime.state_path == "/tmp/apyx-state.json"
    assert settings.runtime.http_timeout_seconds == 12


def test_load_app_config_uses_immutable_collections(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)

    settings = load_app_config(config_path)

    assert isinstance(settings.pendle.markets, tuple)
    assert isinstance(settings.supply.tokens, tuple)
    assert isinstance(settings.curve.pools, tuple)
    assert isinstance(settings.curve.pools[0].coins, tuple)
    assert isinstance(settings.commit.tokens, tuple)
    assert isinstance(settings.security.contracts, tuple)

    with pytest.raises(AttributeError):
        settings.pendle.markets.append(settings.pendle.markets[0])
    with pytest.raises(AttributeError):
        settings.supply.tokens.append(settings.supply.tokens[0])
    with pytest.raises(AttributeError):
        settings.security.contracts.append(settings.security.contracts[0])


def test_load_env_config_reads_required_values(monkeypatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "finnhub-key")
    monkeypatch.setenv("TG_BOT_TOKEN", "telegram-token")
    monkeypatch.setenv("TG_CHAT_ID", "12345")
    monkeypatch.setenv("ETH_RPC_URL", "https://rpc.example")

    env = load_env_config()

    assert env.finnhub_api_key == "finnhub-key"
    assert env.telegram_bot_token == "telegram-token"
    assert env.telegram_chat_id == "12345"
    assert env.eth_rpc_url == "https://rpc.example"
