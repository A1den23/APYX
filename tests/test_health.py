from commands.health import HealthTracker


def test_total_runs_acquires_lock() -> None:
    tracker = HealthTracker()
    tracker.register("test", 60)
    tracker.record_success("test")
    total, ok, fail = tracker.total_runs()
    assert total == 1
    assert ok == 1
    assert fail == 0


def test_snapshot_returns_deep_copy() -> None:
    tracker = HealthTracker()
    tracker.register("test", 60)
    tracker.record_success("test")
    snap = tracker.snapshot()
    tracker.record_failure("test", "oops")
    assert snap["test"].success_count == 1
    assert snap["test"].fail_count == 0
    assert snap["test"].last_error is None


def test_success_clears_previous_error() -> None:
    tracker = HealthTracker()
    tracker.register("test", 60)
    tracker.record_failure("test", "transient timeout")

    tracker.record_success("test")

    snap = tracker.snapshot()
    assert snap["test"].last_error is None
    assert snap["test"].success_count == 1
    assert snap["test"].fail_count == 1


def test_clear_error_does_not_increment_counts() -> None:
    tracker = HealthTracker()
    tracker.register("test", 0)
    tracker.record_failure("test", "transient timeout")

    tracker.clear_error("test")

    snap = tracker.snapshot()
    assert snap["test"].last_error is None
    assert snap["test"].success_count == 0
    assert snap["test"].fail_count == 1
