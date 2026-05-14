from app.config import EnvConfig
from app.service import _build_web3


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
    assert created_urls == [
        "https://primary-rpc.example",
        "https://fallback-rpc.example",
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
