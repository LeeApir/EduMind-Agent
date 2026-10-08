"""Bind independent DSL review to a server-selected, authorized Provider route."""

import hashlib
from pathlib import Path

import httpx

from app.agents.animation_dsl_review import ModelSource, ReviewCall, digest
from app.core.credential_crypto import CredentialFailure
from app.core.provider_factory import build_connection_provider_gateway
from app.core.provider_target import ApprovedTarget
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.services.model_preferences import select_route
from app.services.provider_connection_dispatch import AttemptAuthorizer, DispatchRequest
from app.services.provider_connections import ProviderConnectionStore
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    StructuredRequest,
    TaskProfile,
)

_ADAPTERS = {
    "openai-compatible": "openai_compatible.py",
    "ollama": "ollama.py",
    "anthropic": "anthropic.py",
    "gemini": "gemini.py",
    "spark": "spark.py",
}


class SelectedDSLReviewGateway:
    """T012 resolves the review tier before construction; no implicit route or fallback."""

    def __init__(
        self,
        store: ProviderConnectionStore,
        dispatch: DispatchRequest,
        authorize: AttemptAuthorizer,
        *,
        registry: TemporaryCredentialRegistry | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.store, self.dispatch, self.authorize = store, dispatch, authorize
        self.registry, self.transport = registry, transport

    async def review_structured(self, request: StructuredRequest) -> ReviewCall:
        if request.prompt.task_profile is not TaskProfile.REVIEW:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        selection = await select_route(self.store, self.dispatch.identity, TaskProfile.REVIEW)
        if selection.choice is None or selection.choice.route != self.dispatch.route:
            raise CredentialFailure("CONSENT_REQUIRED")
        await self.store._prepare()
        async with self.store.factory() as db:
            connection = await self.store._row(
                db,
                self.dispatch.identity,
                self.dispatch.route.connection_id,
                self.dispatch.route.config_version,
            )
            provider_type = connection.provider_type
        if provider_type not in _ADAPTERS:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        adapter_file = Path(__file__).parent / _ADAPTERS[provider_type]
        adapter_hash = hashlib.sha256(adapter_file.read_bytes()).hexdigest()
        targets: list[ApprovedTarget] = []
        async with build_connection_provider_gateway(
            self.store,
            self.dispatch,
            self.authorize,
            registry=self.registry,
            transport=self.transport,
            target_observer=targets.append,
        ) as gateway:
            result = await gateway.generate_structured(request, retry_safe=False)
        if (
            len(targets) != 1
            or hashlib.sha256(adapter_file.read_bytes()).hexdigest() != adapter_hash
        ):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
        try:
            source = ModelSource(
                provider_type=provider_type,
                model_id=result.model_id,
                adapter_version="sha256:" + adapter_hash,
                capability_version=self.dispatch.capabilities.version,
                target_sha256=digest(
                    {
                        "provider_type": provider_type,
                        "target": targets[0].url,
                        "selected_model": self.dispatch.route.model_id,
                    }
                ),
            )
        except ValueError:
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
        return ReviewCall(result, source)
