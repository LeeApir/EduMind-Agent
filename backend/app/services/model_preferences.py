"""Explicit priority resolution and ordered non-streaming fallback, no secret persistence."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select

from app.core.credential_crypto import CredentialFailure
from app.core.product_mode import catalog_only
from app.core.provider_factory import build_connection_provider_gateway
from app.core.provider_target import ApprovedTarget
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.models.auth import User
from app.models.model_preferences import ModelPreference
from app.services.provider_connection_dispatch import (
    AttemptAuthorizer,
    ConnectionConsent,
    ConnectionRoute,
    DispatchRequest,
)
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import (
    ProviderError,
    ProviderErrorCode,
    ProviderGateway,
    StructuredRequest,
    StructuredResult,
    TaskProfile,
    TextRequest,
    TextResult,
)
from app.services.provider_model_catalog import resolve_capabilities

ALLOWED_ERRORS = frozenset(
    {
        ProviderErrorCode.RATE_LIMITED,
        ProviderErrorCode.TIMEOUT,
        ProviderErrorCode.TEMPORARILY_UNAVAILABLE,
    }
)


@dataclass(frozen=True)
class Fallback:
    route: ConnectionRoute
    on_errors: frozenset[ProviderErrorCode]


@dataclass(frozen=True)
class RouteChoice:
    route: ConnectionRoute
    fallbacks: tuple[Fallback, ...] = ()
    consent_accepted: bool = False

    def validate(self) -> None:
        if self.consent_accepted is not True:
            raise CredentialFailure("CONSENT_REQUIRED")
        if len(self.fallbacks) > 3:
            raise CredentialFailure("VALIDATION_ERROR")
        seen = {(self.route.connection_id, self.route.config_version, self.route.model_id)}
        for item in self.fallbacks:
            key = (item.route.connection_id, item.route.config_version, item.route.model_id)
            if key in seen or not item.on_errors or not item.on_errors <= ALLOWED_ERRORS:
                raise CredentialFailure("VALIDATION_ERROR")
            seen.add(key)


@dataclass(frozen=True)
class Selection:
    task_profile: TaskProfile
    source: str
    choice: RouteChoice | None


def route_json(route: ConnectionRoute) -> dict[str, object]:
    return {
        "connection_id": str(route.connection_id),
        "config_version": route.config_version,
        "model_id": route.model_id,
        "data_categories": sorted(route.data_categories),
    }


def parse_route(raw: Mapping[str, Any]) -> ConnectionRoute:
    return ConnectionRoute(
        UUID(raw["connection_id"]),
        raw["config_version"],
        raw["model_id"],
        frozenset(raw["data_categories"]),
    )


def fallback_json(item: Fallback) -> dict[str, object]:
    return {"route": route_json(item.route), "on_errors": sorted(e.value for e in item.on_errors)}


def row_choice(row: ModelPreference) -> RouteChoice:
    fallbacks = []
    for item in row.fallbacks:
        route, errors = item["route"], item["on_errors"]
        assert isinstance(route, dict) and isinstance(errors, list)
        fallbacks.append(
            Fallback(parse_route(route), frozenset(ProviderErrorCode(e) for e in errors))
        )
    return RouteChoice(parse_route(row.route), tuple(fallbacks), True)


async def validate_route(
    store: ProviderConnectionStore, identity: CredentialIdentity, route: ConnectionRoute
) -> None:
    view = await store.read(identity, route.connection_id)
    if not view["enabled"] or datetime.fromisoformat(
        str(view["credential_expires_at"])
    ) <= datetime.now(timezone.utc):
        raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
    if view["credential_mode"] == "persistent" and view["credential_state"] != "present":
        raise CredentialFailure("CREDENTIAL_MISSING")
    if view["config_version"] != route.config_version:
        raise CredentialFailure("VERSION_CONFLICT")


async def preference_state(
    store: ProviderConnectionStore, identity: CredentialIdentity, choice: RouteChoice
) -> str:
    for route in (choice.route, *(f.route for f in choice.fallbacks)):
        try:
            await validate_route(store, identity, route)
        except CredentialFailure as error:
            if error.code == "UNAUTHORIZED":
                raise
            return "consent_required" if error.code == "VERSION_CONFLICT" else "unavailable"
    return "available"


async def list_preferences(
    store: ProviderConnectionStore, identity: CredentialIdentity
) -> dict[str, object]:
    await store._prepare()
    async with store.factory() as db:
        await store._session(db, identity)
        rows = (
            await db.scalars(
                select(ModelPreference)
                .where(
                    ModelPreference.user_id == identity.user_id,
                    ModelPreference.originating_session_hash == identity.session_hash,
                )
                .order_by(ModelPreference.task_profile)
            )
        ).all()
    result = []
    for row in rows:
        result.append(
            {
                "task_profile": row.task_profile,
                "version": row.version,
                "route": row.route,
                "fallbacks": row.fallbacks,
                "state": await preference_state(store, identity, row_choice(row)),
            }
        )
    return {"preferences": result}


async def write_preference(
    store: ProviderConnectionStore,
    identity: CredentialIdentity,
    profile: TaskProfile,
    expected_version: int,
    choice: RouteChoice,
) -> dict[str, object]:
    choice.validate()
    if type(expected_version) is not int or expected_version < 0:
        raise CredentialFailure("VALIDATION_ERROR")
    await store._prepare()
    async with store.factory() as db, db.begin():
        await store._session(db, identity)
        # Lock owner for first-create races as well as updates; CRUD never takes this lock.
        await db.scalar(select(User).where(User.id == identity.user_id).with_for_update())
        await store._session(db, identity)
        row = await db.get(ModelPreference, (identity.user_id, profile.value), with_for_update=True)
        if row is not None and row.originating_session_hash != identity.session_hash:
            raise CredentialFailure("NOT_FOUND")
        if expected_version != (row.version if row is not None else 0):
            raise CredentialFailure("VERSION_CONFLICT")
        # Acquire connection locks in stable order, avoiding reverse-route write deadlocks.
        routes = sorted(
            (choice.route, *(f.route for f in choice.fallbacks)),
            key=lambda r: (str(r.connection_id), r.model_id),
        )
        for route in routes:
            connection = await store._row(db, identity, route.connection_id, route.config_version)
            if not connection.enabled or connection.credential_expires_at <= datetime.now(
                timezone.utc
            ):
                raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
            if connection.credential_mode == "persistent" and connection.encrypted_api_key is None:
                raise CredentialFailure("CREDENTIAL_MISSING")
        if row is None:
            row = ModelPreference(
                user_id=identity.user_id,
                task_profile=profile.value,
                originating_session_hash=identity.session_hash,
                version=1,
            )
            db.add(row)
        else:
            row.version += 1
        row.route = route_json(choice.route)
        row.fallbacks = [fallback_json(f) for f in choice.fallbacks]
        await store._session(db, identity)
        return {
            "task_profile": row.task_profile,
            "version": row.version,
            "route": row.route,
            "fallbacks": row.fallbacks,
            "state": "available",
        }


async def select_route(
    store: ProviderConnectionStore,
    identity: CredentialIdentity,
    profile: TaskProfile,
    *,
    override: RouteChoice | None = None,
) -> Selection:
    if override is not None:
        override.validate()
        return Selection(profile, "task_override", override)
    await store._prepare()
    async with store.factory() as db:
        await store._session(db, identity)
        for candidate, source in (
            (profile, "user_task_profile"),
            (TaskProfile.DEFAULT, "user_default"),
        ):
            row = await db.get(ModelPreference, (identity.user_id, candidate.value))
            if row is not None and row.originating_session_hash == identity.session_hash:
                return Selection(profile, source, row_choice(row))
    return Selection(profile, "system_default", None)


async def generate_selected(
    store: ProviderConnectionStore,
    identity: CredentialIdentity,
    selection: Selection,
    request: TextRequest | StructuredRequest,
    *,
    operation_id: UUID,
    consents: tuple[ConnectionConsent, ...],
    data_categories: frozenset[str],
    authorize_attempt: AttemptAuthorizer,
    registry: TemporaryCredentialRegistry | None = None,
    temporary_handles: Mapping[ConnectionRoute, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    system_gateway: Callable[[], ProviderGateway] | None = None,
    authorize_system: Callable[[], Awaitable[None]] | None = None,
    record: Callable[[dict[str, object]], None] | None = None,
) -> TextResult | StructuredResult:
    """Non-streaming only; a stream never switches targets after visible output."""
    if catalog_only():
        raise CredentialFailure("FEATURE_UNAVAILABLE")
    async with store.factory() as db:
        await store._session(db, identity)
    if selection.choice is None:
        if (
            selection.source != "system_default"
            or authorize_system is None
            or system_gateway is None
        ):
            raise CredentialFailure("BUDGET_NOT_AUTHORIZED")
        await authorize_system()
        gateway = system_gateway()
        return (
            await gateway.generate_structured(request)
            if isinstance(request, StructuredRequest)
            else await gateway.generate_text(request)
        )
    selection.choice.validate()
    previous: ProviderErrorCode | None = None
    candidates = [
        (selection.choice.route, None),
        *((f.route, f.on_errors) for f in selection.choice.fallbacks),
    ]
    for route, on_errors in candidates:
        if on_errors is not None and previous not in on_errors:
            continue
        consent = next((c for c in consents if c.route == route and c.accepted is True), None)
        if consent is None or not data_categories or not data_categories <= route.data_categories:
            raise CredentialFailure("CONSENT_REQUIRED")
        await validate_route(store, identity, route)
        capabilities = await resolve_capabilities(store, identity, route)
        dispatch = DispatchRequest(
            identity,
            route,
            consent,
            capabilities,
            operation_id,
            "generation",
            (temporary_handles or {}).get(route),
        )
        observed: list[ApprovedTarget] = []
        try:
            async with build_connection_provider_gateway(
                store,
                dispatch,
                authorize_attempt,
                registry=registry,
                transport=transport,
                target_observer=observed.append,
            ) as gateway:
                result = (
                    await gateway.generate_structured(request)
                    if isinstance(request, StructuredRequest)
                    else await gateway.generate_text(request)
                )
            if record:
                record(
                    {
                        "route": route_json(route),
                        "target": observed[0].url if observed else None,
                        "source": selection.source,
                        "fallback_reason": previous.value if previous else None,
                        "outcome": "success",
                    }
                )
            return result
        except ProviderError as error:
            if record:
                record(
                    {
                        "route": route_json(route),
                        "target": observed[0].url if observed else None,
                        "source": selection.source,
                        "fallback_reason": previous.value if previous else None,
                        "outcome": error.code.value,
                    }
                )
            if error.code not in ALLOWED_ERRORS:
                raise
            previous = error.code
            last_error = error
    assert previous is not None
    raise last_error
