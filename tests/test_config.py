from pathlib import Path

import pytest

from config import load_app_config


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
      url: "https://api.llama.fi/tvl/apxUSD"
  threshold_pct: 0.10
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
    assert settings.tvl.tokens[0].url == "https://api.llama.fi/tvl/apxUSD"
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
