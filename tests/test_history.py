from datetime import datetime, timedelta, timezone

import pytest

from app.history import RollingMetricHistory, percent_change


def test_percent_change_returns_relative_delta() -> None:
    assert percent_change(current=90.0, baseline=100.0) == pytest.approx(-0.10)
    assert percent_change(current=110.0, baseline=100.0) == pytest.approx(0.10)


def test_window_change_uses_sample_at_or_before_cutoff() -> None:
    history = RollingMetricHistory()
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history.record("metric:sample", 100.0, now - timedelta(minutes=65))
    history.record("metric:sample", 98.0, now - timedelta(minutes=55))

    change = history.window_change("metric:sample", current=85.0, now=now, window_minutes=60)

    assert change is not None
    assert change.baseline == 100.0
    assert change.current == 85.0
    assert change.percent == pytest.approx(-0.15)


def test_window_change_uses_closest_sample_before_cutoff_when_out_of_order() -> None:
    history = RollingMetricHistory()
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history.record("metric:sample", 99.0, now - timedelta(minutes=59))
    history.record("metric:sample", 100.0, now - timedelta(minutes=65))
    history.record("metric:sample", 90.0, now - timedelta(minutes=61))

    change = history.window_change(
        "metric:sample", current=81.0, now=now, window_minutes=60
    )

    assert change is not None
    assert change.baseline == 90.0
    assert change.current == 81.0
    assert change.percent == pytest.approx(-0.10)


def test_record_prunes_stale_out_of_order_samples_using_latest_timestamp() -> None:
    history = RollingMetricHistory(retention_minutes=60)
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history.record("metric:sample", 110.0, now)
    history.record("metric:sample", 50.0, now - timedelta(minutes=120))

    change = history.window_change(
        "metric:sample", current=75.0, now=now, window_minutes=90
    )

    assert change is None


def test_latest_change_uses_previous_sample() -> None:
    history = RollingMetricHistory()
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history.record("supply:apxUSD", 1000.0, now - timedelta(minutes=1))

    change = history.latest_change("supply:apxUSD", current=1125.0)

    assert change is not None
    assert change.percent == pytest.approx(0.125)


def test_latest_change_returns_none_for_zero_baseline() -> None:
    history = RollingMetricHistory()
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history.record("supply:apxUSD", 0.0, now - timedelta(minutes=1))

    assert history.latest_change("supply:apxUSD", current=1125.0) is None


def test_window_change_returns_none_for_zero_baseline() -> None:
    history = RollingMetricHistory()
    now = datetime(2026, 4, 24, 15, 0, tzinfo=timezone.utc)
    history.record("metric:sample", 0.0, now - timedelta(minutes=65))

    assert (
        history.window_change("metric:sample", current=85.0, now=now, window_minutes=60)
        is None
    )


def test_rolling_metric_history_round_trips_samples() -> None:
    history = RollingMetricHistory(retention_minutes=180)
    now = datetime(2026, 4, 24, 15, 30, tzinfo=timezone.utc)
    history.record("supply:apxUSD", 100.0, now - timedelta(minutes=30))
    history.record("supply:apxUSD", 110.0, now)

    restored = RollingMetricHistory.from_dict(history.to_dict())

    assert restored.latest_sample("supply:apxUSD").value == 110.0
    change = restored.window_change(
        "supply:apxUSD",
        current=120.0,
        now=now,
        window_minutes=30,
    )
    assert change is not None
    assert change.baseline == 100.0
