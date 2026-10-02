"""Server-only composition root for configured Provider Gateway calls."""

from collections.abc import Callable
from os import getenv

from app.core.config import ConfigurationError, ProviderSettings, get_provider_settings
from app.core.product_mode import catalog_only
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
    if catalog_only():
        raise ProviderError(ProviderErrorCode.CONFIGURATION_MISSING)
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


def build_default_provider_gateway() -> ProviderGateway:
    """Compose the one configured P0 network adapter behind the neutral Gateway."""
    return build_server_provider_gateway(configured_provider_adapter)


def configured_provider_adapter(
    settings: ProviderSettings,
    guard: ProviderTargetGuard,
) -> ProviderAdapter:
    from app.services.deepseek_responses import DeepSeekResponsesAdapter

    mode = getenv("EDUMIND_PROVIDER_STRUCTURED_TRANSPORT", "responses_json_schema")
    if mode == "responses_json_schema":
        return DeepSeekResponsesAdapter(settings, guard)
    if mode == "beta_tools":
        from app.services.deepseek_beta_tools import DeepSeekBetaToolsAdapter

        return DeepSeekBetaToolsAdapter(settings, guard)
    raise ProviderError(ProviderErrorCode.CONFIGURATION_MISSING)
