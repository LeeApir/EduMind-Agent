"""Server-only composition root for configured Provider Gateway calls."""

from collections.abc import Callable

from app.core.config import ConfigurationError, ProviderSettings, get_provider_settings
from app.services.provider_gateway import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
)


def build_server_provider_gateway(
    adapter_factory: Callable[[ProviderSettings], ProviderAdapter],
) -> ProviderGateway:
    """Require complete server credentials before constructing a generation gateway."""
    try:
        settings = get_provider_settings()
    except ConfigurationError:
        raise ProviderError(ProviderErrorCode.CONFIGURATION_MISSING) from None
    return ProviderGateway(adapter_factory(settings))
