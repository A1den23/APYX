from config import load_app_config
from commands.health import HealthTracker
from main import _register_monitors, _security_contract_names


def test_register_monitors_includes_security_checks_and_one_minute_pendle() -> None:
    settings = load_app_config()
    tracker = HealthTracker()

    _register_monitors(tracker, settings)

    snapshot = tracker.snapshot()
    assert snapshot["security_events"].interval_seconds == 60
    assert snapshot["mint_backing:apyUSD"].interval_seconds == 60
    assert snapshot["pendle:apxUSD"].interval_seconds == 60


def test_security_contract_names_include_tokens_and_pendle_markets() -> None:
    settings = load_app_config()

    names = _security_contract_names(settings)

    assert names["0x98a878b1cd98131b271883b390f68d2c90674665"] == "apxUSD"
    assert names["0x38eeb52f0771140d10c4e9a9a72349a329fe8a6a"] == "apyUSD"
    assert names["0x50dce085af29caba28f7308bea57c4043757b491"] == "Pendle apxUSD"
