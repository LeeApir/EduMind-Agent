"""Server-only configuration helpers."""

from dataclasses import dataclass
from os import getenv


class ConfigurationError(RuntimeError):
    """Raised when a required server configuration value is unavailable."""


@dataclass(frozen=True, slots=True)
class ProviderSettings:
    """The minimum P0 OpenAI-compatible provider configuration."""

    base_url: str
    api_key: str
    model: str


def get_provider_settings() -> ProviderSettings:
    """Load provider settings, failing safely without exposing secret values."""
    required_values = {
        "EDUMIND_PROVIDER_BASE_URL": getenv("EDUMIND_PROVIDER_BASE_URL"),
        "EDUMIND_PROVIDER_API_KEY": getenv("EDUMIND_PROVIDER_API_KEY"),
        "EDUMIND_PROVIDER_MODEL": getenv("EDUMIND_PROVIDER_MODEL"),
    }
    missing = [name for name, value in required_values.items() if not value]
    if missing:
        raise ConfigurationError(
            "Missing required provider configuration: " + ", ".join(missing) + ". "
            "Set these server environment variables before starting model generation."
        )

    return ProviderSettings(
        base_url=required_values["EDUMIND_PROVIDER_BASE_URL"] or "",
        api_key=required_values["EDUMIND_PROVIDER_API_KEY"] or "",
        model=required_values["EDUMIND_PROVIDER_MODEL"] or "",
    )
