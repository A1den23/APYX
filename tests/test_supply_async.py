import asyncio
import threading

from monitors import supply as supply_module
from monitors.supply import fetch_total_supply_async


def test_fetch_total_supply_async_runs_sync_web3_call_off_event_loop(monkeypatch) -> None:
    main_thread = threading.get_ident()
    call_thread = None

    def fake_fetch_total_supply(web3, *, address: str) -> float:
        nonlocal call_thread
        call_thread = threading.get_ident()
        return 42.0

    monkeypatch.setattr(supply_module, "fetch_total_supply", fake_fetch_total_supply)

    result = asyncio.run(fetch_total_supply_async(object(), address="0xabc"))

    assert result == 42.0
    assert call_thread is not None
    assert call_thread != main_thread
