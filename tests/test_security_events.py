from datetime import datetime, timedelta, timezone

from alert.engine import AlertEngine, AlertEvent
from app.config import SupplyToken
from monitors.security_events import (
    PRIVILEGED_EVENT_TOPICS,
    TRANSFER_TOPIC,
    LogScanState,
    RecentSecurityEventCache,
    evaluate_privileged_logs,
    evaluate_token_movements,
    parse_token_movements,
)


def _topic_address(address: str) -> str:
    return "0x" + "0" * 24 + address.lower().removeprefix("0x")


def test_parse_token_movements_extracts_mint_and_burn_logs() -> None:
    token = SupplyToken(
        name="apxUSD",
        address="0x98A878b1Cd98131B271883B390f68D2c90674665",
        absolute_change_threshold=5_000_000,
    )
    logs = [
        {
            "address": token.address,
            "topics": [
                TRANSFER_TOPIC,
                _topic_address("0x0000000000000000000000000000000000000000"),
                _topic_address("0x1111111111111111111111111111111111111111"),
            ],
            "data": hex(6_000_000 * 10**18),
            "transactionHash": "0xabc",
            "blockNumber": 123,
            "logIndex": 7,
        },
        {
            "address": token.address,
            "topics": [
                TRANSFER_TOPIC,
                _topic_address("0x2222222222222222222222222222222222222222"),
                _topic_address("0x0000000000000000000000000000000000000000"),
            ],
            "data": hex(2_500_000 * 10**18),
            "transactionHash": "0xdef",
            "blockNumber": 124,
            "logIndex": 1,
        },
    ]

    movements = parse_token_movements(
        logs,
        tokens=(token,),
        decimals_by_address={token.address.lower(): 18},
    )

    assert [m.kind for m in movements] == ["mint", "burn"]
    assert movements[0].amount == 6_000_000
    assert movements[0].counterparty == "0x1111111111111111111111111111111111111111"
    assert movements[1].amount == 2_500_000


def test_evaluate_token_movements_alerts_only_when_large_enough() -> None:
    token = SupplyToken(
        name="apxUSD",
        address="0x98A878b1Cd98131B271883B390f68D2c90674665",
        absolute_change_threshold=5_000_000,
    )
    logs = [
        {
            "address": token.address,
            "topics": [
                TRANSFER_TOPIC,
                _topic_address("0x0000000000000000000000000000000000000000"),
                _topic_address("0x1111111111111111111111111111111111111111"),
            ],
            "data": hex(5_500_000 * 10**18),
            "transactionHash": "0xabc",
            "blockNumber": 123,
            "logIndex": 7,
        },
        {
            "address": token.address,
            "topics": [
                TRANSFER_TOPIC,
                _topic_address("0x0000000000000000000000000000000000000000"),
                _topic_address("0x2222222222222222222222222222222222222222"),
            ],
            "data": hex(4_900_000 * 10**18),
            "transactionHash": "0xdef",
            "blockNumber": 124,
            "logIndex": 1,
        },
    ]
    movements = parse_token_movements(
        logs,
        tokens=(token,),
        decimals_by_address={token.address.lower(): 18},
    )

    events = evaluate_token_movements(
        movements,
        tokens=(token,),
        now=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )

    assert len(events) == 1
    assert isinstance(events[0], AlertEvent)
    assert events[0].title == "apxUSD 大额铸造"
    assert "金额: 5,500,000.00 apxUSD" in events[0].body
    assert "交易: 0xabc" in events[0].body


def test_evaluate_privileged_logs_alerts_on_role_and_upgrade_events() -> None:
    role_granted_topic = PRIVILEGED_EVENT_TOPICS["RoleGranted(uint64,address,uint32,uint48,bool)"]
    upgraded_topic = PRIVILEGED_EVENT_TOPICS["Upgraded(address)"]
    logs = [
        {
            "address": "0x98A878b1Cd98131B271883B390f68D2c90674665",
            "topics": [role_granted_topic],
            "transactionHash": "0xrole",
            "blockNumber": 123,
            "logIndex": 0,
        },
        {
            "address": "0x38EEb52F0771140d10c4E9A9a72349A329Fe8a6A",
            "topics": [upgraded_topic],
            "transactionHash": "0xupgrade",
            "blockNumber": 124,
            "logIndex": 1,
        },
    ]

    events = evaluate_privileged_logs(
        logs,
        contract_names={
            "0x98a878b1cd98131b271883b390f68d2c90674665": "apxUSD",
            "0x38eeb52f0771140d10c4e9a9a72349a329fe8a6a": "apyUSD",
        },
        now=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )

    assert [event.title for event in events] == [
        "apxUSD 权限事件",
        "apyUSD 权限事件",
    ]
    assert "事件: 角色授予 (RoleGranted)" in events[0].body
    assert "事件: 实现升级 (Upgraded)" in events[1].body


def test_evaluate_privileged_logs_alerts_on_access_manager_and_protocol_events() -> None:
    scheduled_topic = PRIVILEGED_EVENT_TOPICS[
        "OperationScheduled(bytes32,uint32,uint48,address,address,bytes)"
    ]
    cap_topic = PRIVILEGED_EVENT_TOPICS["SupplyCapUpdated(uint256,uint256)"]
    vesting_topic = PRIVILEGED_EVENT_TOPICS["VestingPeriodUpdated(uint256,uint256)"]
    logs = [
        {
            "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "topics": [scheduled_topic],
            "transactionHash": "0xschedule",
            "blockNumber": 125,
            "logIndex": 0,
        },
        {
            "address": "0x98A878b1Cd98131B271883B390f68D2c90674665",
            "topics": [cap_topic],
            "transactionHash": "0xcap",
            "blockNumber": 126,
            "logIndex": 1,
        },
        {
            "address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            "topics": [vesting_topic],
            "transactionHash": "0xvesting",
            "blockNumber": 127,
            "logIndex": 2,
        },
    ]

    events = evaluate_privileged_logs(
        logs,
        contract_names={
            "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa": "AccessManager",
            "0x98a878b1cd98131b271883b390f68d2c90674665": "apxUSD",
            "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb": "LinearVestV0",
        },
        now=datetime(2026, 4, 26, tzinfo=timezone.utc),
    )

    assert [event.title for event in events] == [
        "AccessManager 权限事件",
        "apxUSD 权限事件",
        "LinearVestV0 权限事件",
    ]
    assert "事件: 操作排队 (OperationScheduled)" in events[0].body
    assert "事件: 供应上限更新 (SupplyCapUpdated)" in events[1].body
    assert "事件: 归属周期更新 (VestingPeriodUpdated)" in events[2].body


def test_log_scan_state_starts_from_recent_blocks_and_advances() -> None:
    state = LogScanState(start_block_lookback=25, max_blocks_per_scan=100)

    assert state.next_range(latest_block=1_000) == (976, 1_000)
    state.mark_scanned(1_000)
    assert state.next_range(latest_block=1_005) == (1_001, 1_005)


def test_log_scan_state_round_trips_checkpoint() -> None:
    state = LogScanState(start_block_lookback=25, max_blocks_per_scan=100)
    state.mark_scanned(1_000)

    restored = LogScanState.from_dict(state.to_dict())

    assert restored.start_block_lookback == 25
    assert restored.max_blocks_per_scan == 100
    assert restored.last_scanned_block == 1_000
    assert restored.next_range(latest_block=1_005) == (1_001, 1_005)


def test_recent_security_event_cache_keeps_status_active_for_one_hour() -> None:
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    engine = AlertEngine(cooldown=timedelta(minutes=5))
    cache = RecentSecurityEventCache(hold_duration=timedelta(hours=1))
    event = AlertEvent("ALERT", "apxUSD 权限事件", "事件: 角色授予 (RoleGranted)", now)

    assert cache.evaluate(events=[event], engine=engine, now=now) is None
    assert "security_events" in engine.active_alerts()

    assert cache.evaluate(events=[], engine=engine, now=now + timedelta(minutes=59)) is None
    assert "security_events" in engine.active_alerts()

    recovery = cache.evaluate(events=[], engine=engine, now=now + timedelta(hours=1, seconds=1))

    assert recovery is not None
    assert recovery.kind == "RECOVERY"
    assert recovery.title == "安全事件恢复正常"
    assert "security_events" not in engine.active_alerts()


def test_recent_security_event_cache_round_trips_last_event() -> None:
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)
    cache = RecentSecurityEventCache(hold_duration=timedelta(hours=1))
    cache.last_event_at = now
    cache.last_event_title = "apxUSD 权限事件"
    cache.last_event_body = "事件: 角色授予 (RoleGranted)"

    restored = RecentSecurityEventCache.from_dict(cache.to_dict())

    assert restored.hold_duration == timedelta(hours=1)
    assert restored.last_event_at == now
    assert restored.last_event_title == "apxUSD 权限事件"
    assert restored.last_event_body == "事件: 角色授予 (RoleGranted)"
