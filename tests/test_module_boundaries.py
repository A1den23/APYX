def test_runtime_boundaries_are_split_from_cli_entrypoint() -> None:
    from app import jobs
    from app import security_scan
    from app import service
    import main

    assert jobs.run_one_minute_checks is not None
    assert jobs.run_five_minute_checks is not None
    assert security_scan.run_security_event_checks is not None
    assert service.run_service is not None
    assert main.run_service is service.run_service


def test_support_modules_live_under_app_package() -> None:
    from app import config
    from app import errors
    from app import history
    from app import runtime_state
    from app import status_cache

    assert config.load_app_config is not None
    assert errors.safe_error_message is not None
    assert history.RollingMetricHistory is not None
    assert runtime_state.RuntimeStateStore is not None
    assert status_cache.StatusCache is not None
