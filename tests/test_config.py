from pathlib import Path

import pytest

from config import load_app_config, load_env_config


def write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
finnhub:
  symbol: "STRC"
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
  window_minutes: 60
supply:
  tokens:
    - name: "apxUSD"
      address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
  threshold_pct: 0.10
tvl:
  tokens:
    - name: "apxUSD"
      address: "0x98A878b1Cd98131B271883B390f68D2c90674665"
  threshold_pct: 0.10
  window_minutes: 60
apyusd:
  token:
    name: "apyUSD"
    address: "0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A"
  total_assets_change_pct: 0.10
  price_apxusd_change_pct: 0.10
  window_minutes: 60
alert:
  cooldown_minutes: 5
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_load_app_config_parses_thresholds_and_addresses(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)

    settings = load_app_config(config_path)

    assert settings.finnhub.symbol == "STRC"
    assert settings.finnhub.threshold_price == 95.0
    assert settings.peg.token.name == "apxUSD"
    assert settings.peg.threshold_pct == 0.003
    assert settings.pendle.markets[0].address == "0x50dce085af29caba28f7308bea57c4043757b491"
    assert settings.tvl.tokens[0].address == "0x98A878b1Cd98131B271883B390f68D2c90674665"
    assert settings.apyusd.token.address == "0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A"
    assert settings.apyusd.total_assets_change_pct == 0.10
    assert settings.apyusd.price_apxusd_change_pct == 0.10
    assert settings.apyusd.window_minutes == 60
    assert settings.alert.cooldown_minutes == 5


def test_load_app_config_uses_immutable_collections(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)

    settings = load_app_config(config_path)

    assert isinstance(settings.pendle.markets, tuple)
    assert isinstance(settings.supply.tokens, tuple)
    assert isinstance(settings.tvl.tokens, tuple)

    with pytest.raises(AttributeError):
        settings.pendle.markets.append(settings.pendle.markets[0])
    with pytest.raises(AttributeError):
        settings.supply.tokens.append(settings.supply.tokens[0])
    with pytest.raises(AttributeError):
        settings.tvl.tokens.append(settings.tvl.tokens[0])


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
