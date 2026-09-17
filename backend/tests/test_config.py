import asyncio
from collections.abc import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import ConfigurationError, ProviderSettings, get_provider_settings
from app.core.provider_factory import build_server_provider_gateway
from app.main import app
from app.services.provider_gateway import (
    ChatMessage,
    ProviderAdapter,
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    StructuredResult,
    TextDelta,
    TextRequest,
    TextResult,
)


def test_missing_provider_configuration_has_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "EDUMIND_PROVIDER_BASE_URL",
        "EDUMIND_PROVIDER_API_KEY",
        "EDUMIND_PROVIDER_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigurationError, match="EDUMIND_PROVIDER_API_KEY"):
        get_provider_settings()


def test_provider_configuration_is_loaded_from_server_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EDUMIND_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", "test-key")
    monkeypatch.setenv("EDUMIND_PROVIDER_MODEL", "test-model")

    settings = get_provider_settings()

    assert settings.base_url == "https://provider.example/v1"
    assert settings.api_key == "test-key"
    assert settings.model == "test-model"


def test_server_gateway_refuses_missing_key_before_adapter_is_built(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("EDUMIND_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("EDUMIND_PROVIDER_MODEL", "server-model")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", " ")
    built = 0

    def forbidden_factory(_settings: ProviderSettings) -> ProviderAdapter:
        nonlocal built
        built += 1
        raise AssertionError("adapter must not be built")

    async def attempt_generation() -> TextResult:
        gateway = build_server_provider_gateway(forbidden_factory)
        return await gateway.generate_text(
            TextRequest(messages=(ChatMessage(role="user", content="hello"),))
        )

    with pytest.raises(ProviderError) as raised:
        asyncio.run(attempt_generation())

    assert raised.value.code == ProviderErrorCode.CONFIGURATION_MISSING
    assert raised.value.retryable is False
    assert built == 0
    assert "EDUMIND_PROVIDER_API_KEY" not in str(raised.value)
    assert "provider.example" not in str(raised.value)
    assert "server-model" not in caplog.text


def test_server_only_key_is_not_exposed_by_repr_error_log_or_client_response(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret = "test-secret-that-must-stay-server-side"
    monkeypatch.setenv("EDUMIND_PROVIDER_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("EDUMIND_PROVIDER_MODEL", "server-model")
    monkeypatch.setenv("EDUMIND_PROVIDER_API_KEY", secret)
    settings = get_provider_settings()
    assert secret not in repr(settings)
    assert secret not in str(settings)

    class ConfiguredFakeAdapter:
        async def generate_text(self, request: TextRequest) -> TextResult:
            assert request.messages[-1].content == "hello"
            return TextResult(text="safe-answer", model_id=settings.model)

        async def generate_structured(self, request: StructuredRequest) -> StructuredResult:
            return StructuredResult(value={"ok": True}, model_id=settings.model)

        async def stream_text(self, request: TextRequest) -> AsyncIterator[TextDelta]:
            yield TextDelta(text="safe-answer")

    def adapter_factory(configured_settings: ProviderSettings) -> ConfiguredFakeAdapter:
        assert configured_settings.api_key == secret
        return ConfiguredFakeAdapter()

    gateway = build_server_provider_gateway(adapter_factory)
    result = asyncio.run(
        gateway.generate_text(TextRequest(messages=(ChatMessage(role="user", content="hello"),)))
    )
    assert result.text == "safe-answer"
    with TestClient(app) as client:
        health = client.get("/health")
        openapi = client.get("/openapi.json")
    assert health.status_code == openapi.status_code == 200
    assert secret not in health.text
    assert secret not in openapi.text
    assert secret not in caplog.text
