from app.config import EnvConfig, load_app_config
from app.rpc_status import RpcEndpointStatus
from app.service import FailoverHTTPProvider, _add_recurring_jobs, _build_web3
from app.jobs import run_five_minute_checks, run_one_minute_checks


def test_build_web3_uses_fallback_when_primary_rpc_is_unavailable(monkeypatch) -> None:
    created_urls: list[str] = []

    class FakeProvider:
        def __init__(self, url: str, *, request_kwargs: dict[str, int]) -> None:
            self.url = url
            self.request_kwargs = request_kwargs

    class FakeWeb3:
        HTTPProvider = FakeProvider

        def __init__(self, provider: FakeProvider) -> None:
            self.provider = provider
            created_urls.append(provider.url)

        def is_connected(self) -> bool:
            return self.provider.url != "https://primary-rpc.example"

    monkeypatch.setattr("app.service.Web3", FakeWeb3)
    env = EnvConfig(
        finnhub_api_key="finnhub-key",
        telegram_bot_token="telegram-token",
        telegram_chat_id="12345",
        eth_rpc_url="https://primary-rpc.example",
        eth_rpc_fallback_url="https://fallback-rpc.example",
    )

    web3 = _build_web3(env)

    assert web3.provider.url == "https://fallback-rpc.example"
    assert created_urls == ["https://primary-rpc.example"]


def test_add_recurring_jobs_uses_configured_runtime_intervals() -> None:
    settings = load_app_config()
    calls: list[tuple[object, str, dict[str, object]]] = []

    class FakeScheduler:
        def add_job(self, func: object, trigger: str, **kwargs: object) -> None:
            calls.append((func, trigger, kwargs))

    onchain_kwargs = {"kind": "onchain"}
    external_kwargs = {"kind": "external"}

    _add_recurring_jobs(
        FakeScheduler(),
        settings=settings,
        onchain_kwargs=onchain_kwargs,
        external_kwargs=external_kwargs,
    )

    assert calls[0][0] is run_one_minute_checks
    assert calls[0][1] == "interval"
    assert calls[0][2]["minutes"] == 3
    assert calls[0][2]["kwargs"] == onchain_kwargs
    assert calls[1][0] is run_five_minute_checks
    assert calls[1][1] == "interval"
    assert calls[1][2]["minutes"] == 5
    assert calls[1][2]["kwargs"] == external_kwargs


def test_build_web3_registers_multiple_fallback_rpc_urls(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self, url: str, *, request_kwargs: dict[str, int]) -> None:
            self.url = url
            self.request_kwargs = request_kwargs

    class FakeWeb3:
        HTTPProvider = FakeProvider

        def __init__(self, provider: FailoverHTTPProvider) -> None:
            self.provider = provider

        def is_connected(self) -> bool:
            return True

    monkeypatch.setattr("app.service.Web3", FakeWeb3)
    env = EnvConfig(
        finnhub_api_key="finnhub-key",
        telegram_bot_token="telegram-token",
        telegram_chat_id="12345",
        eth_rpc_url="https://primary-rpc.example",
        eth_rpc_fallback_urls=(
            "https://fallback-1-rpc.example",
            "https://fallback-2-rpc.example",
        ),
    )

    web3 = _build_web3(env)

    assert web3.provider._rpc_urls == [
        "https://primary-rpc.example",
        "https://fallback-1-rpc.example",
        "https://fallback-2-rpc.example",
    ]


def test_build_web3_keeps_primary_rpc_when_no_fallback_is_configured(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self, url: str, *, request_kwargs: dict[str, int]) -> None:
            self.url = url
            self.request_kwargs = request_kwargs

    class FakeWeb3:
        HTTPProvider = FakeProvider

        def __init__(self, provider: FakeProvider) -> None:
            self.provider = provider

        def is_connected(self) -> bool:
            raise AssertionError("primary RPC should not be probed without fallback")

    monkeypatch.setattr("app.service.Web3", FakeWeb3)
    env = EnvConfig(
        finnhub_api_key="finnhub-key",
        telegram_bot_token="telegram-token",
        telegram_chat_id="12345",
        eth_rpc_url="https://primary-rpc.example",
    )

    web3 = _build_web3(env)

    assert web3.provider.url == "https://primary-rpc.example"


def test_failover_provider_retries_429_on_fallback(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self, url: str, *, request_kwargs: dict[str, int]) -> None:
            self.url = url

        def make_request(self, method: str, params: object) -> dict[str, object]:
            if self.url == "https://primary-rpc.example":
                raise RuntimeError("429 Client Error: Too Many Requests")
            return {"jsonrpc": "2.0", "id": 1, "result": "0x1"}

        def is_connected(self, show_traceback: bool = False) -> bool:
            return True

    class FakeWeb3:
        HTTPProvider = FakeProvider

    monkeypatch.setattr("app.service.Web3", FakeWeb3)
    provider = FailoverHTTPProvider(
        ["https://primary-rpc.example", "https://fallback-rpc.example"],
        request_kwargs={"timeout": 20},
    )

    response = provider.make_request("eth_call", [])

    assert response == {"jsonrpc": "2.0", "id": 1, "result": "0x1"}
    assert provider.url == "https://fallback-rpc.example"


def test_failover_provider_retries_json_rpc_rate_limit_response(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self, url: str, *, request_kwargs: dict[str, int]) -> None:
            self.url = url

        def make_request(self, method: str, params: object) -> dict[str, object]:
            if self.url == "https://primary-rpc.example":
                return {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": 429, "message": "Too Many Requests"},
                }
            return {"jsonrpc": "2.0", "id": 1, "result": "0x2"}

        def is_connected(self, show_traceback: bool = False) -> bool:
            return True

    class FakeWeb3:
        HTTPProvider = FakeProvider

    monkeypatch.setattr("app.service.Web3", FakeWeb3)
    provider = FailoverHTTPProvider(
        ["https://primary-rpc.example", "https://fallback-rpc.example"],
        request_kwargs={"timeout": 20},
    )

    response = provider.make_request("eth_blockNumber", [])

    assert response == {"jsonrpc": "2.0", "id": 1, "result": "0x2"}
    assert provider.url == "https://fallback-rpc.example"


def test_failover_provider_can_skip_multiple_retryable_rpc_failures(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self, url: str, *, request_kwargs: dict[str, int]) -> None:
            self.url = url

        def make_request(self, method: str, params: object) -> dict[str, object]:
            if self.url in {
                "https://primary-rpc.example",
                "https://fallback-1-rpc.example",
            }:
                raise RuntimeError("504 Gateway Timeout")
            return {"jsonrpc": "2.0", "id": 1, "result": "0x3"}

        def is_connected(self, show_traceback: bool = False) -> bool:
            return True

    class FakeWeb3:
        HTTPProvider = FakeProvider

    monkeypatch.setattr("app.service.Web3", FakeWeb3)
    provider = FailoverHTTPProvider(
        [
            "https://primary-rpc.example",
            "https://fallback-1-rpc.example",
            "https://fallback-2-rpc.example",
        ],
        request_kwargs={"timeout": 20},
    )

    response = provider.make_request("eth_call", [])

    assert response == {"jsonrpc": "2.0", "id": 1, "result": "0x3"}
    assert provider.url == "https://fallback-2-rpc.example"


def test_failover_provider_skips_unsupported_method_rpc_responses(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self, url: str, *, request_kwargs: dict[str, int]) -> None:
            self.url = url

        def make_request(self, method: str, params: object) -> dict[str, object]:
            if self.url == "https://primary-rpc.example":
                return {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": 429, "message": "Too Many Requests"},
                }
            if self.url == "https://unsupported-rpc.example":
                return {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": -32601,
                        "message": "the method eth_chainId does not exist/is not available",
                    },
                }
            if self.url == "https://cannot-fulfill-rpc.example":
                return {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32046, "message": "Cannot fulfill request"},
                }
            return {"jsonrpc": "2.0", "id": 1, "result": "0x1"}

        def is_connected(self, show_traceback: bool = False) -> bool:
            return True

    class FakeWeb3:
        HTTPProvider = FakeProvider

    monkeypatch.setattr("app.service.Web3", FakeWeb3)
    provider = FailoverHTTPProvider(
        [
            "https://primary-rpc.example",
            "https://unsupported-rpc.example",
            "https://cannot-fulfill-rpc.example",
            "https://working-rpc.example",
        ],
        request_kwargs={"timeout": 20},
    )

    response = provider.make_request("eth_chainId", [])

    assert response == {"jsonrpc": "2.0", "id": 1, "result": "0x1"}
    assert provider.url == "https://working-rpc.example"


def test_failover_provider_reports_endpoint_statuses_without_switching_active(monkeypatch) -> None:
    class FakeProvider:
        def __init__(self, url: str, *, request_kwargs: dict[str, int]) -> None:
            self.url = url

        def make_request(self, method: str, params: object) -> dict[str, object]:
            if self.url == "https://primary-rpc.example/secret-token":
                return {"jsonrpc": "2.0", "id": 1, "result": "0x10"}
            if self.url == "https://fallback-1-rpc.example/key":
                return {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {"code": -32000, "message": "Unauthorized"},
                }
            raise RuntimeError("504 Gateway Timeout for https://fallback-2-rpc.example/key")

        def is_connected(self, show_traceback: bool = False) -> bool:
            return True

    class FakeWeb3:
        HTTPProvider = FakeProvider

    monkeypatch.setattr("app.service.Web3", FakeWeb3)
    provider = FailoverHTTPProvider(
        [
            "https://primary-rpc.example/secret-token",
            "https://fallback-1-rpc.example/key",
            "https://fallback-2-rpc.example/key",
        ],
        request_kwargs={"timeout": 20},
    )

    statuses = provider.endpoint_statuses()

    assert statuses == (
        RpcEndpointStatus(
            role="primary",
            label="primary-rpc.example",
            active=True,
            connected=True,
            block_number=16,
        ),
        RpcEndpointStatus(
            role="fallback 1",
            label="fallback-1-rpc.example",
            active=False,
            connected=False,
            error="Unauthorized",
        ),
        RpcEndpointStatus(
            role="fallback 2",
            label="fallback-2-rpc.example",
            active=False,
            connected=False,
            error="504 Gateway Timeout for fallback-2-rpc.example",
        ),
    )
    assert provider.url == "https://primary-rpc.example/secret-token"
