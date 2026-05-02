from app.config import load_app_config
from commands.health import HealthTracker
from app.security_scan import _security_contract_names
from app.service import _register_monitors


def test_register_monitors_includes_security_checks_and_one_minute_pendle() -> None:
    settings = load_app_config()
    tracker = HealthTracker()

    _register_monitors(tracker, settings)

    snapshot = tracker.snapshot()
    assert snapshot["security_events"].interval_seconds == 60
    assert snapshot["mint_backing:apyUSD"].interval_seconds == 60
    assert snapshot["pendle:apxUSD"].interval_seconds == 60
    assert snapshot["morpho:PT-apyUSD-18JUN2026-USDC"].interval_seconds == 60
    assert snapshot["curve:apxUSD-USDC"].interval_seconds == 60
    assert snapshot["curve:apyUSD-apxUSD"].interval_seconds == 60
    assert snapshot["commit:apxUSD Commit"].interval_seconds == 60
    assert snapshot["yield_distribution"].interval_seconds == 60
    assert snapshot["tradfi:SATA"].interval_seconds == 300


def test_security_contract_names_include_tokens_and_pendle_markets() -> None:
    settings = load_app_config()

    names = _security_contract_names(settings)

    assert names["0x98a878b1cd98131b271883b390f68d2c90674665"] == "apxUSD"
    assert names["0x38eeb52f0771140d10c4e9a9a72349a329fe8a6a"] == "apyUSD"
    assert names["0x50dce085af29caba28f7308bea57c4043757b491"] == "Pendle apxUSD"
    assert names["0xe1b96555bbeca40e583bbb41a11c68ca4706a414"] == "Curve apxUSD-USDC"
    assert names["0xe41be7b340f7c2eda4da1e99b42ee1b228b526b7"] == "Curve apyUSD-apxUSD"
    assert names["0x93775e2dfa4e716c361a1f53f212c7ae031bf4e6"] == "UnlockToken"
    assert names["0x17122d869d981d184118b301313bcd157c79871e"] == "CommitToken apxUSD"
