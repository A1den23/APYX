from app.config import EnvConfig
from app.service import FailoverHTTPProvider, _build_web3


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
