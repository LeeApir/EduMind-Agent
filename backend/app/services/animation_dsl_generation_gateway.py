"""Use one immutable selected quality route; all sends retain the existing authorization chain."""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from app.agents.animation_dsl_generation import GenerationCall
from app.agents.animation_dsl_review import ModelSource, canonical, digest
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
    ProviderGateway,
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


class SelectedDSLGenerationGateway:
    def __init__(
        self,
        store: ProviderConnectionStore,
        dispatch: DispatchRequest,
        authorize: AttemptAuthorizer,
        *,
        registry: TemporaryCredentialRegistry | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        shared_gateway: ProviderGateway | None = None,
        target_log: list[ApprovedTarget] | None = None,
    ) -> None:
        self.store, self.dispatch, self.authorize = store, dispatch, authorize
        self.registry, self.transport = registry, transport
        self.shared_gateway = shared_gateway
        self.target_log = target_log if target_log is not None else []

    async def generate_candidate(self, request: StructuredRequest) -> GenerationCall:
        if request.prompt.task_profile is not TaskProfile.QUALITY:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        if not {"learning_goal", "content_for_review"} <= self.dispatch.route.data_categories:
            raise CredentialFailure("CONSENT_REQUIRED")
        selection = await select_route(self.store, self.dispatch.identity, TaskProfile.QUALITY)
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
        targets = self.target_log if self.shared_gateway is not None else []
        offset = len(targets)
        async with self._gateway(targets) as gateway:
            if self.dispatch.capabilities.structured_output is True:
                structured = await gateway.generate_structured(request, retry_safe=False)
                raw, model_id = canonical(dict(structured.value)), structured.model_id
            else:
                # Single bounded JSON text call, not a retry after structured failure.
                text = await gateway.generate_text(request.prompt, retry_safe=False)
                raw, model_id = text.text, text.model_id
        observed = targets[offset:]
        if (
            len(observed) != 1
            or model_id != self.dispatch.route.model_id
            or len(raw) > 65536
            or hashlib.sha256(adapter_file.read_bytes()).hexdigest() != adapter_hash
        ):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT)
        try:
            encoded = raw.encode("utf-8")
            if len(encoded) > 65536:
                raise ValueError()
            source = ModelSource(
                provider_type,
                model_id,
                "sha256:" + adapter_hash,
                self.dispatch.capabilities.version,
                digest(
                    {
                        "provider_type": provider_type,
                        "target": observed[0].url,
                        "selected_model": self.dispatch.route.model_id,
                    }
                ),
            )
        except (ValueError, UnicodeError):
            raise ProviderError(ProviderErrorCode.INVALID_OUTPUT) from None
        return GenerationCall(encoded, source)

    @asynccontextmanager
    async def _gateway(self, targets: list[ApprovedTarget]) -> AsyncIterator[ProviderGateway]:
        # One API operation task can own a single temporary lease across bounded corrections/review.
        if self.shared_gateway is not None:
            yield self.shared_gateway
        else:
            async with build_connection_provider_gateway(
                self.store,
                self.dispatch,
                self.authorize,
                registry=self.registry,
                transport=self.transport,
                target_observer=targets.append,
            ) as gateway:
                yield gateway
