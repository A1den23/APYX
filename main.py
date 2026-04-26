from __future__ import annotations

import argparse
import asyncio

from jobs import run_five_minute_checks, run_one_minute_checks, send_events
from security_scan import _security_contract_names, run_security_event_checks
from service import _register_monitors, run_service, send_lifecycle_notification


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="APYX stablecoin and Pendle pool monitor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one 1-minute cycle and one 5-minute cycle, then exit",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_service(once=args.once))
