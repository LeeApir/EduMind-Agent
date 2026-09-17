"""Server-only composition root for configured Provider Gateway calls."""

from collections.abc import Callable

from app.core.config import ConfigurationError, ProviderSettings, get_provider_settings
from app.core.provider_target import (
    ProviderTargetGuard,
    TargetValidationError,
    target_policy_from_environment,
)
from app.services.provider_gateway import (
    ProviderAdapter,
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
)


def build_server_provider_gateway(
    adapter_factory: Callable[[ProviderSettings, ProviderTargetGuard], ProviderAdapter],
) -> ProviderGateway:
    """Reject unsafe targets before handing credentials to a network adapter."""
    try:
        settings = get_provider_settings()
    except ConfigurationError:
        raise ProviderError(ProviderErrorCode.CONFIGURATION_MISSING) from None
    try:
        guard = ProviderTargetGuard(settings.base_url, target_policy_from_environment())
        guard.approve_base()
    except TargetValidationError:
        raise ProviderError(ProviderErrorCode.INVALID_TARGET) from None
    return ProviderGateway(adapter_factory(settings, guard))
