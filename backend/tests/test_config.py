import pytest

from app.core.config import ConfigurationError, get_provider_settings


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
