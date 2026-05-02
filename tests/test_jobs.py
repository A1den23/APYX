import inspect
import re

import app.jobs as jobs_mod


def test_all_record_failure_calls_use_safe_error_message() -> None:
    source = inspect.getsource(jobs_mod)
    calls = re.findall(r'tracker\.record_failure\([^)]+\)', source)
    for call in calls:
        assert "str(e)" not in call, f"Raw str(e) in record_failure: {call}"
