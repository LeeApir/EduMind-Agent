"""Read-only owner cache and explicit single bounded list fetch through send authority."""

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import httpx
from sqlalchemy.dialects.postgresql import insert

from app.core.credential_crypto import CredentialFailure
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.models.provider_model_snapshots import ProviderModelSnapshot
from app.services.openai_compatible import _check_status
from app.services.provider_connection_dispatch import (
    ConnectionConsent,
    ConnectionOperation,
    ConnectionRoute,
    DispatchRequest,
    ModelCapabilities,
)
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import ProviderError, ProviderErrorCode
from app.services.provider_probe import ProbeBudget
from app.services.provider_protocol import invalid_output, strict_json, validated_model

REFRESH_TIMEOUT_SECONDS = 10.0
MAX_LIST_BYTES = 2 * 1024 * 1024
MAX_MODELS = 1000
CAPABILITY_VERSION = "model-list-declarations-v1"
FLAGS = ("streaming", "structured_output", "tool_calling", "vision", "embedding", "tts", "asr")


def model_metadata(raw: object, provider_type: str) -> list[dict[str, object]]:
    if not isinstance(raw, dict):
        raise invalid_output()
    items = raw.get("models" if provider_type == "ollama" else "data")
    if not isinstance(items, list) or len(items) > MAX_MODELS:
        raise invalid_output()
    models: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in items:
        if not isinstance(entry, dict):
            raise invalid_output()
        model = validated_model(entry.get("name" if provider_type == "ollama" else "id"))
        if model in seen:
            raise invalid_output()
        seen.add(model)
        # Optional metadata extension: explicit booleans only, never model-name inference.
        declaration = entry.get("edumind_capabilities")
        if declaration is not None and (
            not isinstance(declaration, dict)
            or set(declaration) - set(FLAGS)
            or any(v is not None and type(v) is not bool for v in declaration.values())
        ):
            raise invalid_output()
        flags = {flag: (declaration or {}).get(flag) for flag in FLAGS}
        models.append(
            {
                "id": model,
                "capabilities": {
                    **flags,
                    "source": "declared"
                    if any(v is not None for v in flags.values())
                    else "unknown",
                    "version": CAPABILITY_VERSION,
                },
            }
        )
    return models


async def cached_models(
    store: ProviderConnectionStore, identity: CredentialIdentity, cid: UUID
) -> dict[str, object]:
    await store._prepare()
    async with store.factory() as db, db.begin():
        connection = await store._row(db, identity, cid)
        snapshot = await db.get(ProviderModelSnapshot, cid)
        current = snapshot is not None and snapshot.config_version == connection.config_version
        return {
            "connection_id": str(cid),
            "config_version": connection.config_version,
            "models": snapshot.models if current and snapshot is not None else [],
            "refreshed_at": snapshot.refreshed_at.isoformat()
            if current and snapshot is not None
            else None,
        }


async def resolve_capabilities(
    store: ProviderConnectionStore, identity: CredentialIdentity, route: ConnectionRoute
) -> ModelCapabilities:
    await store._prepare()
    # Resolve the owned typed row rather than a caller-supplied model declaration.
    async with store.factory() as db, db.begin():
        await store._row(db, identity, route.connection_id, route.config_version)
        snapshot = await db.get(ProviderModelSnapshot, route.connection_id)
        if snapshot is None or snapshot.config_version != route.config_version:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        for model in snapshot.models:
            if model["id"] == route.model_id:
                caps = model["capabilities"]
                assert isinstance(caps, dict)
                return ModelCapabilities(
                    route.connection_id,
                    route.config_version,
                    route.model_id,
                    str(caps["version"]),
                    caps["streaming"],
                    caps["structured_output"],
                )
    raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)


async def refresh_models(
    store: ProviderConnectionStore,
    identity: CredentialIdentity,
    route: ConnectionRoute,
    *,
    accepted: bool,
    operation_id: UUID,
    temporary_handle: str | None,
    registry: TemporaryCredentialRegistry | None,
    budget: ProbeBudget,
    transport: httpx.AsyncBaseTransport | None,
) -> dict[str, object]:
    try:
        async with asyncio.timeout(REFRESH_TIMEOUT_SECONDS):
            view = await store.read(identity, route.connection_id)
            if view["config_version"] != route.config_version:
                raise CredentialFailure("VERSION_CONFLICT")
            if accepted is not True or route.data_categories != frozenset({"probe"}):
                raise CredentialFailure("CONSENT_REQUIRED")
            if view["provider_type"] not in {"openai-compatible", "ollama"}:
                raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
            if not view["enabled"]:
                raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
            if view["credential_mode"] == "persistent" and view["credential_state"] != "present":
                raise CredentialFailure("CREDENTIAL_MISSING")
            dispatch = DispatchRequest(
                identity,
                route,
                ConnectionConsent(route, accepted),
                ModelCapabilities(
                    route.connection_id, route.config_version, route.model_id, CAPABILITY_VERSION
                ),
                operation_id,
                "model_refresh",
                temporary_handle,
            )
            dispatch.validate()
            await budget.preflight(dispatch)
            operation = ConnectionOperation(
                store, dispatch, budget.authorize_attempt, transport=transport
            )
            async with operation.activate(registry):
                async with operation.send(None) as response:
                    _check_status(response)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        operation._check()
                        if len(data) + len(chunk) > MAX_LIST_BYTES:
                            raise invalid_output()
                        data.extend(chunk)
                    models = model_metadata(strict_json(bytes(data)), str(view["provider_type"]))
                    for model in models:
                        operation.check_public_metadata(str(model["id"]))
                operation._check()
                # Same row lock as CRUD prevents publication after a target/version change.
                async with store.factory() as db, db.begin():
                    await store._row(db, identity, route.connection_id, route.config_version)
                    operation._check()
                    now = datetime.now(timezone.utc)
                    statement = insert(ProviderModelSnapshot).values(
                        connection_id=route.connection_id,
                        config_version=route.config_version,
                        models=models,
                        refreshed_at=now,
                    )
                    await db.execute(
                        statement.on_conflict_do_update(
                            index_elements=[ProviderModelSnapshot.connection_id],
                            set_={
                                "config_version": route.config_version,
                                "models": models,
                                "refreshed_at": now,
                            },
                        )
                    )
                    await store._session(db, identity)
                    operation._check()
            return {
                "connection_id": str(route.connection_id),
                "config_version": route.config_version,
                "models": models,
                "refreshed_at": now.isoformat(),
            }
    except TimeoutError:
        raise ProviderError(ProviderErrorCode.TIMEOUT) from None
