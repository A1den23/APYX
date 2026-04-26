from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine
from history import RollingMetricHistory
from monitors.security_events import LogScanState, RecentSecurityEventCache
from runtime_state import RuntimeStateStore, RuntimeState


def test_runtime_state_store_round_trips_monitor_state(tmp_path) -> None:
    path = tmp_path / "runtime-state.json"
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    now = datetime(2026, 4, 24, 14, 30, tzinfo=timezone.utc)
    engine.evaluate(
        metric_key="peg:apxUSD",
        breached=True,
        alert_title="apxUSD Peg Deviation",
        alert_body="Price: $0.9960",
        recovery_title="apxUSD Peg Normal",
        recovery_body="Price: $1.0001",
        now=now,
    )
    history = RollingMetricHistory()
    history.record("supply:apxUSD", 100.0, now - timedelta(minutes=30))
    scan_state = LogScanState(start_block_lookback=25, max_blocks_per_scan=100)
    scan_state.mark_scanned(1_000)
    recent = RecentSecurityEventCache(hold_duration=timedelta(hours=1))
    recent.last_event_at = now
    recent.last_event_title = "apxUSD Privileged Event"
    recent.last_event_body = "Event: RoleGranted"

    RuntimeStateStore(path).save(
        RuntimeState(
            alert_engine=engine,
            history=history,
            security_state=scan_state,
            recent_security_events=recent,
        )
    )

    restored = RuntimeStateStore(path).load()

    assert restored.alert_engine.active_alerts() == ["peg:apxUSD"]
    assert restored.history.latest_sample("supply:apxUSD").value == 100.0
    assert restored.security_state.last_scanned_block == 1_000
    assert restored.recent_security_events.last_event_title == "apxUSD Privileged Event"
