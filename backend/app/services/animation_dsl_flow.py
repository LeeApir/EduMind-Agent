"""One API task owns bounded selected-model calls and exact temporary leases; never a Worker."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.animation_dsl_generation import AnimationDSLGenerator, GenerationCall
from app.agents.animation_dsl_review import AnimationDSLReviewAgent, ModelSource, ReviewCall, digest
from app.core.credential_crypto import CredentialFailure
from app.core.provider_factory import build_connection_provider_gateway
from app.core.provider_target import ApprovedTarget
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.models.animation_generation import AnimationPreparation
from app.models.auth import GuestSessionRecord, User
from app.models.model_preferences import ModelPreference
from app.models.provider_connections import ProviderConnection
from app.models.provider_model_snapshots import ProviderModelSnapshot
from app.services.animation_dsl_generation_gateway import SelectedDSLGenerationGateway
from app.services.animation_dsl_review_gateway import SelectedDSLReviewGateway
from app.services.animation_preparation import advance_preparation
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.model_preferences import row_choice, select_route
from app.services.provider_connection_dispatch import (
    ConnectionConsent,
    DispatchRequest,
    ModelCapabilities,
)
from app.services.provider_connections import (
    CredentialIdentity,
    ProviderConnectionStore,
    connection_view,
)
from app.services.provider_gateway import ProviderGateway, StructuredRequest, TaskProfile
from app.services.provider_model_catalog import resolve_capabilities

_ADAPTERS = {
    "openai-compatible": "openai_compatible.py",
    "ollama": "ollama.py",
    "anthropic": "anthropic.py",
    "gemini": "gemini.py",
    "spark": "spark.py",
}


class DSLCallBudget(Protocol):
    async def authorize(self, request: DispatchRequest, profile: TaskProfile) -> None: ...


class UnavailableDSLCallBudget:
    async def authorize(self, request: DispatchRequest, profile: TaskProfile) -> None:
        raise CredentialFailure("BUDGET_NOT_AUTHORIZED")


@dataclass(frozen=True)
class DSLSelectedSource:
    dispatch: DispatchRequest = field(repr=False)
    source: ModelSource


async def selected_dsl_source(
    store: ProviderConnectionStore,
    identity: CredentialIdentity,
    profile: TaskProfile,
    operation_id: UUID,
    handle: str | None,
    *,
    lock: bool = True,
) -> DSLSelectedSource:
    selection = await select_route(store, identity, profile)
    if selection.choice is None:
        raise CredentialFailure("CONSENT_REQUIRED")
    selection.choice.validate()
    route = selection.choice.route
    categories = (
        {"learning_goal", "content_for_review"}
        if profile is TaskProfile.QUALITY
        else {
            "content_for_review",
        }
    )
    if not categories <= route.data_categories:
        raise CredentialFailure("CONSENT_REQUIRED")
    if lock:
        capabilities = await resolve_capabilities(store, identity, route)
        view = await store.read(identity, route.connection_id)
    else:
        # Send already holds its connection row. A second FOR UPDATE would self-deadlock.
        async with store.factory() as db:
            await store._session(db, identity)
            row = await db.scalar(
                select(ProviderConnection).where(
                    ProviderConnection.id == route.connection_id,
                    ProviderConnection.user_id == identity.user_id,
                    ProviderConnection.originating_session_hash == identity.session_hash,
                    ProviderConnection.config_version == route.config_version,
                    ProviderConnection.deleted.is_(False),
                    ProviderConnection.enabled.is_(True),
                )
            )
            snapshot = await db.get(ProviderModelSnapshot, route.connection_id)
            if row is None or snapshot is None or snapshot.config_version != route.config_version:
                raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
            view = connection_view(row)
            model = next((m for m in snapshot.models if m["id"] == route.model_id), None)
            if model is None:
                raise CredentialFailure("CAPABILITY_UNAVAILABLE")
            caps = model["capabilities"]
            if not isinstance(caps, dict):
                raise CredentialFailure("CAPABILITY_UNAVAILABLE")
            capabilities = ModelCapabilities(
                route.connection_id,
                route.config_version,
                route.model_id,
                caps["version"],
                caps["streaming"],
                caps["structured_output"],
                tool_calling=caps.get("tool_calling"),
                vision=caps.get("vision"),
            )
    if profile is TaskProfile.REVIEW and capabilities.structured_output is not True:
        raise CredentialFailure("CAPABILITY_UNAVAILABLE")
    kind = str(view["provider_type"])
    if kind not in _ADAPTERS:
        raise CredentialFailure("CAPABILITY_UNAVAILABLE")
    adapter = Path(__file__).parent / _ADAPTERS[kind]
    source = ModelSource(
        kind,
        route.model_id,
        "sha256:" + hashlib.sha256(adapter.read_bytes()).hexdigest(),
        capabilities.version,
        digest(
            {"provider_type": kind, "target": view["base_url"], "selected_model": route.model_id}
        ),
    )
    dispatch = DispatchRequest(
        identity,
        route,
        ConnectionConsent(route, True),
        capabilities,
        operation_id,
        temporary_handle=handle,
    )
    return DSLSelectedSource(dispatch, source)


class SelectedDSLFlow:
    def __init__(
        self,
        store: ProviderConnectionStore,
        graph: KnowledgeGraphRepository,
        operation: AnimationPreparation,
        identity: CredentialIdentity,
        budget: DSLCallBudget,
        *,
        quality_handle: str | None = None,
        review_handle: str | None = None,
        registry: TemporaryCredentialRegistry | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        stage_changed: Callable[[str], Awaitable[None]] | None = None,
    ):
        self.store, self.graph, self.operation, self.identity, self.budget = (
            store,
            graph,
            operation,
            identity,
            budget,
        )
        self.quality_handle, self.review_handle = quality_handle, review_handle
        self.registry, self.transport, self.stage_changed = registry, transport, stage_changed
        self.frozen: dict[TaskProfile, DSLSelectedSource] = {}
        self.stack = AsyncExitStack()
        self.current_profile = TaskProfile.QUALITY
        self.active: dict[TaskProfile, ProviderGateway] = {}
        self.logs: dict[TaskProfile, list[ApprovedTarget]] = {}

    async def validate_handoff_sources(self, db: AsyncSession) -> None:
        """Freeze route and connection mutations through the no-model handoff commit."""
        await db.scalar(select(User).where(User.id == self.identity.user_id).with_for_update())
        await self.store._session(db, self.identity)
        if set(self.frozen) != {TaskProfile.QUALITY, TaskProfile.REVIEW}:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        preferences = {}
        for profile in (TaskProfile.QUALITY, TaskProfile.REVIEW, TaskProfile.DEFAULT):
            preferences[profile] = await db.get(
                ModelPreference, (self.identity.user_id, profile.value)
            )
        for profile, frozen in self.frozen.items():
            row = preferences[profile] or preferences[TaskProfile.DEFAULT]
            if row is None or row.originating_session_hash != self.identity.session_hash:
                raise CredentialFailure("CONSENT_REQUIRED")
            choice = row_choice(row)
            choice.validate()
            if choice.route != frozen.dispatch.route:
                raise CredentialFailure("VERSION_CONFLICT")
        for cid in sorted({s.dispatch.route.connection_id for s in self.frozen.values()}, key=str):
            rows = [s for s in self.frozen.values() if s.dispatch.route.connection_id == cid]
            connection = await self.store._row(
                db, self.identity, cid, rows[0].dispatch.route.config_version
            )
            snapshot = await db.get(ProviderModelSnapshot, cid, with_for_update=True)
            if (
                not connection.enabled
                or snapshot is None
                or snapshot.config_version != connection.config_version
            ):
                raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
            for frozen in rows:
                route = frozen.dispatch.route
                model = next((m for m in snapshot.models if m["id"] == route.model_id), None)
                if model is None:
                    raise CredentialFailure("CAPABILITY_UNAVAILABLE")
                caps = model["capabilities"]
                if not isinstance(caps, dict):
                    raise CredentialFailure("CAPABILITY_UNAVAILABLE")
                capabilities = ModelCapabilities(
                    cid,
                    route.config_version,
                    route.model_id,
                    caps["version"],
                    caps["streaming"],
                    caps["structured_output"],
                    tool_calling=caps.get("tool_calling"),
                    vision=caps.get("vision"),
                )
                if capabilities != frozen.dispatch.capabilities:
                    raise CredentialFailure("CAPABILITY_UNAVAILABLE")
                current = ModelSource(
                    connection.provider_type,
                    route.model_id,
                    "sha256:"
                    + hashlib.sha256(
                        (Path(__file__).parent / _ADAPTERS[connection.provider_type]).read_bytes()
                    ).hexdigest(),
                    caps["version"],
                    digest(
                        {
                            "provider_type": connection.provider_type,
                            "target": connection.base_url,
                            "selected_model": route.model_id,
                        }
                    ),
                )
                if current != frozen.source:
                    raise CredentialFailure("VERSION_CONFLICT")

    async def freeze_sources(self) -> tuple[ModelSource, ModelSource]:
        frozen: dict[TaskProfile, DSLSelectedSource] = {}
        for profile, handle in (
            (TaskProfile.QUALITY, self.quality_handle),
            (TaskProfile.REVIEW, self.review_handle),
        ):
            frozen[profile] = await selected_dsl_source(
                self.store,
                self.identity,
                profile,
                self.operation.id,
                handle,
            )
        self.frozen = frozen
        return self.frozen[TaskProfile.QUALITY].source, self.frozen[TaskProfile.REVIEW].source

    async def validate_sources(self, *, lock: bool = True) -> None:
        if not self.frozen:
            raise CredentialFailure("CONSENT_REQUIRED")
        for profile, original in self.frozen.items():
            current = await selected_dsl_source(
                self.store,
                self.identity,
                profile,
                self.operation.id,
                original.dispatch.temporary_handle,
                lock=lock,
            )
            if current != original:
                raise CredentialFailure("CONSENT_REQUIRED")

    async def _authorize(self, request: DispatchRequest) -> None:
        profile = self.current_profile
        original = self.frozen[profile]
        # Shared review uses exactly the same authorized connection, model and purpose.
        permitted = original.dispatch
        if request != permitted:
            quality = self.frozen[TaskProfile.QUALITY].dispatch
            if (
                request != quality
                or profile is not TaskProfile.REVIEW
                or not self._shareable(quality, permitted)
            ):
                raise CredentialFailure("CONSENT_REQUIRED")
        await self.validate_sources(lock=False)
        await self.budget.authorize(request, profile)
        async with self.store.factory() as db:
            valid = await advance_preparation(
                db,
                self.graph,
                owner=self.identity.user_id,
                session_hash=self.identity.session_hash,
                operation_id=self.operation.id,
                execution_token=self.operation.execution_token,
                stage="generating" if profile is TaskProfile.QUALITY else "reviewing",
            )
        if not valid:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        if self.stage_changed is not None:
            await self.stage_changed(
                "generating" if profile is TaskProfile.QUALITY else "reviewing"
            )

    @staticmethod
    def _shareable(quality: DispatchRequest, review: DispatchRequest) -> bool:
        a, b = quality.route, review.route
        return (
            quality.identity == review.identity
            and quality.operation_id == review.operation_id
            and quality.purpose == review.purpose
            and (a.connection_id, a.config_version, a.model_id)
            == (b.connection_id, b.config_version, b.model_id)
            and a.data_categories >= b.data_categories
            and quality.capabilities == review.capabilities
        )

    async def _activate(self) -> None:
        if self.active:
            return
        if not self.frozen:
            await self.freeze_sources()
        await self.validate_sources()
        quality, review = (
            self.frozen[TaskProfile.QUALITY].dispatch,
            self.frozen[TaskProfile.REVIEW].dispatch,
        )
        for profile, dispatch in ((TaskProfile.QUALITY, quality), (TaskProfile.REVIEW, review)):
            if profile is TaskProfile.REVIEW and self._shareable(quality, review):
                if review.temporary_handle not in (None, quality.temporary_handle):
                    raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
                self.active[profile] = self.active[TaskProfile.QUALITY]
                self.logs[profile] = self.logs[TaskProfile.QUALITY]
                continue
            log: list[ApprovedTarget] = []
            self.logs[profile] = log
            self.active[profile] = await self.stack.enter_async_context(
                build_connection_provider_gateway(
                    self.store,
                    dispatch,
                    self._authorize,
                    registry=self.registry,
                    transport=self.transport,
                    target_observer=log.append,
                )
            )

    async def generate_candidate(self, request: StructuredRequest) -> GenerationCall:
        self.current_profile = TaskProfile.QUALITY
        await self._activate()
        original = self.frozen[self.current_profile]
        gateway = SelectedDSLGenerationGateway(
            self.store,
            original.dispatch,
            self._authorize,
            shared_gateway=self.active[self.current_profile],
            target_log=self.logs[self.current_profile],
        )
        result = await gateway.generate_candidate(request)
        if result.source != original.source:
            raise CredentialFailure("CONSENT_REQUIRED")
        return result

    async def review_structured(self, request: StructuredRequest) -> ReviewCall:
        self.current_profile = TaskProfile.REVIEW
        await self._activate()
        original = self.frozen[self.current_profile]
        gateway = SelectedDSLReviewGateway(
            self.store,
            original.dispatch,
            self._authorize,
            shared_gateway=self.active[self.current_profile],
            target_log=self.logs[self.current_profile],
        )
        result = await gateway.review_structured(request)
        if result.source != original.source:
            raise CredentialFailure("CONSENT_REQUIRED")
        return result

    def generator(self) -> AnimationDSLGenerator:
        return AnimationDSLGenerator(self, AnimationDSLReviewAgent(self))

    async def close(self) -> None:
        await self.stack.aclose()
        if self.registry is not None:
            self.registry.retire_operation(
                self.identity.user_id, self.identity.session_hash, self.operation.id
            )

    async def live(self) -> bool:
        async with self.store.factory() as db:
            now = await db.scalar(select(func.clock_timestamp()))
            operation = await db.get(
                AnimationPreparation, self.operation.id, populate_existing=True
            )
            session = await db.get(GuestSessionRecord, self.identity.session_hash)
            return (
                isinstance(now, datetime)
                and operation is not None
                and session is not None
                and operation.user_id == self.identity.user_id
                and operation.originating_session_hash == self.identity.session_hash
                and operation.execution_token == self.operation.execution_token
                and operation.stage in {"reserved", "generating", "reviewing", "compiled"}
                and operation.deadline > now
                and session.expires_at > now
            )
