from datetime import datetime, timedelta, timezone

import pytest

from alert.engine import AlertEngine
from monitors.solvency import (
    AccountableSolvencySnapshot,
    evaluate_solvency,
    parse_accountable_dashboard,
)


def test_parse_accountable_dashboard_extracts_solvency_fields() -> None:
    payload = {
        "res": "ok",
        "data": {
            "collateralization": 1.007765,
            "net": 1551932.13,
            "ts": "1777195208494",
            "reserves": {
                "total_reserves": {"value": 201414546.13},
                "total_supply": {"value": 199862614.0},
                "verifiability": "100",
                "interval": "live",
            },
        },
    }

    snapshot = parse_accountable_dashboard(payload)

    assert snapshot.collateralization == 1.007765
    assert snapshot.total_reserves == 201414546.13
    assert snapshot.total_supply == 199862614.0
    assert snapshot.net == 1551932.13
    assert snapshot.timestamp == datetime(2026, 4, 26, 9, 20, 8, 494000, tzinfo=timezone.utc)
    assert snapshot.verifiability == "100"
    assert snapshot.interval == "live"


def test_evaluate_solvency_alerts_below_warning_threshold() -> None:
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    snapshot = AccountableSolvencySnapshot(
        collateralization=1.0005,
        total_reserves=201_000_000.0,
        total_supply=200_200_000.0,
        net=800_000.0,
        timestamp=now,
        verifiability="100",
        interval="live",
    )

    event = evaluate_solvency(
        snapshot=snapshot,
        warning_collateralization=1.001,
        critical_collateralization=1.0,
        max_data_age=timedelta(hours=2),
        engine=AlertEngine(cooldown=timedelta(minutes=5)),
        now=now,
    )

    assert event is not None
    assert event.metric_key == "solvency:accountable"
    assert event.title == "APYX 偿付率预警"
    assert "偿付率: 100.05%" in event.body
    assert "预警阈值: 100.10%" in event.body


def test_evaluate_solvency_alerts_when_reserves_below_supply() -> None:
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    snapshot = AccountableSolvencySnapshot(
        collateralization=0.998,
        total_reserves=197_000_000.0,
        total_supply=198_000_000.0,
        net=-1_000_000.0,
        timestamp=now,
        verifiability="100",
        interval="live",
    )

    event = evaluate_solvency(
        snapshot=snapshot,
        warning_collateralization=1.001,
        critical_collateralization=1.0,
        max_data_age=timedelta(hours=2),
        engine=AlertEngine(cooldown=timedelta(minutes=5)),
        now=now,
    )

    assert event is not None
    assert event.title == "APYX 偿付率紧急告警"
    assert "总储备低于总供应" in event.body


def test_evaluate_solvency_alerts_on_stale_data() -> None:
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    snapshot = AccountableSolvencySnapshot(
        collateralization=1.05,
        total_reserves=210_000_000.0,
        total_supply=200_000_000.0,
        net=10_000_000.0,
        timestamp=now - timedelta(hours=3),
        verifiability="100",
        interval="live",
    )

    event = evaluate_solvency(
        snapshot=snapshot,
        warning_collateralization=1.001,
        critical_collateralization=1.0,
        max_data_age=timedelta(hours=2),
        engine=AlertEngine(cooldown=timedelta(minutes=5)),
        now=now,
    )

    assert event is not None
    assert event.title == "APYX 偿付数据过旧"
    assert "数据时延: 180.0 分钟" in event.body


def test_evaluate_solvency_recovers_after_alert() -> None:
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    bad = AccountableSolvencySnapshot(
        collateralization=0.99,
        total_reserves=197_000_000.0,
        total_supply=199_000_000.0,
        net=-2_000_000.0,
        timestamp=now,
        verifiability="100",
        interval="live",
    )
    good = AccountableSolvencySnapshot(
        collateralization=1.03,
        total_reserves=205_000_000.0,
        total_supply=199_000_000.0,
        net=6_000_000.0,
        timestamp=now + timedelta(minutes=1),
        verifiability="100",
        interval="live",
    )

    evaluate_solvency(
        snapshot=bad,
        warning_collateralization=1.001,
        critical_collateralization=1.0,
        max_data_age=timedelta(hours=2),
        engine=engine,
        now=now,
    )
    event = evaluate_solvency(
        snapshot=good,
        warning_collateralization=1.001,
        critical_collateralization=1.0,
        max_data_age=timedelta(hours=2),
        engine=engine,
        now=now + timedelta(minutes=1),
    )

    assert event is not None
    assert event.title == "APYX 偿付率恢复正常"


def test_parse_accountable_dashboard_raises_on_error_response() -> None:
    payload = {"res": "error", "data": {}}
    with pytest.raises(ValueError):
        parse_accountable_dashboard(payload)
