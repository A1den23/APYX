def test_runtime_boundaries_are_split_from_cli_entrypoint() -> None:
    import jobs
    import security_scan
    import service
    import main

    assert jobs.run_one_minute_checks is not None
    assert jobs.run_five_minute_checks is not None
    assert security_scan.run_security_event_checks is not None
    assert service.run_service is not None
    assert main.run_service is service.run_service
