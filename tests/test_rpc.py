from app.rpc_status import RpcEndpointStatus
from commands.rpc import build_rpc_message


def test_build_rpc_message_lists_statuses_without_exposing_rpc_tokens() -> None:
    message = build_rpc_message(
        (
            RpcEndpointStatus(
                role="primary",
                label="primary-rpc.example",
                active=True,
                connected=True,
                block_number=123,
            ),
            RpcEndpointStatus(
                role="fallback 1",
                label="rpc.ankr.com",
                active=False,
                connected=False,
                error="Unauthorized: token rejected",
            ),
        )
    )

    assert "ETH RPC status:" in message
    assert "[OK] primary primary-rpc.example (active) - block=123" in message
    assert "[FAIL] fallback 1 rpc.ankr.com - Unauthorized: token rejected" in message
    assert "secret" not in message
    assert "/eth/" not in message
