"""Explicit single text probe: fixed prompt, hard deadline, separate budget admission."""

import asyncio
import ipaddress
from dataclasses import replace
from typing import Protocol
from uuid import UUID

import httpx

from app.core.credential_crypto import CredentialFailure
from app.core.provider_factory import build_connection_provider_gateway
from app.core.provider_target import ApprovedTarget, is_public_address
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.services.provider_connection_dispatch import (
    ConnectionConsent,
    ConnectionRoute,
    DispatchRequest,
    ModelCapabilities,
)
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import ChatMessage, ProviderError, ProviderErrorCode, TextRequest

PROBE_TIMEOUT_SECONDS = 10.0
PROBE_RULE_VERSION = "connection-text-probe-v1"
PROBE_PROMPT = TextRequest(
    (ChatMessage("user", "Reply only with OK."),), max_output_tokens=8, temperature=0
)
PROBE_NOTICE = "Explicit test may contact the selected service; no automatic retry or fallback."


class ProbeBudget(Protocol):
    async def preflight(self, request: DispatchRequest) -> None:
        """Non-consuming admission check before any temporary handle is claimed."""
        ...

    async def authorize_attempt(self, request: DispatchRequest) -> None:
        """Fresh reservation/authorization under the actual send lock; exactly once here."""
        ...


class UnavailableProbeBudget:
    """No budget grant from installed adapters, Key configuration, or historical quota."""

    async def preflight(self, request: DispatchRequest) -> None:
        raise CredentialFailure("BUDGET_NOT_AUTHORIZED")

    async def authorize_attempt(self, request: DispatchRequest) -> None:
        raise CredentialFailure("BUDGET_NOT_AUTHORIZED")


async def probe_connection(
    store: ProviderConnectionStore,
    identity: CredentialIdentity,
    route: ConnectionRoute,
    *,
    accepted: bool,
    operation_id: UUID,
    temporary_handle: str | None,
    registry: TemporaryCredentialRegistry | None,
    budget: ProbeBudget,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            view = await store.read(identity, route.connection_id)
            if view["config_version"] != route.config_version:
                raise CredentialFailure("VERSION_CONFLICT")
            if route.data_categories != frozenset({"probe"}) or accepted is not True:
                raise CredentialFailure("CONSENT_REQUIRED")
            if not view["enabled"]:
                raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
            if view["credential_state"] == "expired":
                raise CredentialFailure("CREDENTIAL_EXPIRED")
            if view["provider_type"] not in {"openai-compatible", "ollama", "anthropic", "gemini"}:
                raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
            if view["credential_mode"] == "persistent" and view["credential_state"] != "present":
                raise CredentialFailure("CREDENTIAL_MISSING")
            capabilities = ModelCapabilities(
                route.connection_id, route.config_version, route.model_id, PROBE_RULE_VERSION
            )
            dispatch = DispatchRequest(
                identity,
                route,
                ConnectionConsent(route, accepted),
                capabilities,
                operation_id,
                "connection_test",
                temporary_handle,
            )
            dispatch.validate()
            await budget.preflight(dispatch)
            observed: list[ApprovedTarget] = []
            async with build_connection_provider_gateway(
                store,
                dispatch,
                budget.authorize_attempt,
                registry=registry,
                transport=transport,
                target_observer=observed.append,
            ) as gateway:
                # Native sampling is deprecated on newer models. Probe policy needs
                # bounded output, not deterministic sampling; no user setting is dropped.
                prompt = (
                    replace(PROBE_PROMPT, temperature=None)
                    if view["provider_type"] == "anthropic"
                    else PROBE_PROMPT
                )
                result = await gateway.generate_text(prompt)  # retry_safe remains False.
            assert len(observed) == 1
            target = observed[0]
            # Text success cannot establish streaming/structured/multimodal model capabilities.
            return {
                "connection_id": str(route.connection_id),
                "config_version": route.config_version,
                "model_id": route.model_id,
                "target": target.url,
                "is_local": all(
                    not is_public_address(ipaddress.ip_address(ip)) for ip in target.addresses
                ),
                "capabilities": {
                    "streaming": None,
                    "structured_output": None,
                    "tool_calling": None,
                    "vision": None,
                    "embedding": None,
                    "tts": None,
                    "asr": None,
                    "source": "unknown",
                    "version": PROBE_RULE_VERSION,
                },
                "requests": 1,
                "usage": (
                    {
                        "input_tokens": result.usage.input_tokens,
                        "output_tokens": result.usage.output_tokens,
                    }
                    if result.usage
                    else None
                ),
            }
    except TimeoutError:
        raise ProviderError(ProviderErrorCode.TIMEOUT) from None
