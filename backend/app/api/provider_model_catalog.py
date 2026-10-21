"""Static types and owner-scoped cached models; only explicit POST can contact service."""

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request, Response

from app.api.provider_connections import ProviderRoute, identity, provider_store, request_registry
from app.api.provider_probe import ProviderProbeRequest
from app.core.auth import AuthenticatedSession, require_authenticated_session
from app.services.provider_connection_dispatch import ConnectionRoute
from app.services.provider_connections import PROVIDER_TYPES, ProviderConnectionStore
from app.services.provider_model_catalog import cached_models, refresh_models
from app.services.provider_probe import PROBE_NOTICE, ProbeBudget, UnavailableProbeBudget

router = APIRouter(prefix="/api/providers", tags=["Providers"], route_class=ProviderRoute)


def model_refresh_budget() -> ProbeBudget:
    return UnavailableProbeBudget()


def model_refresh_transport() -> httpx.AsyncBaseTransport | None:
    return None


@router.get("/catalog", operation_id="getProviderCatalog")
async def catalog(
    current: AuthenticatedSession = Depends(require_authenticated_session),
) -> dict[str, object]:
    return {"types": sorted(PROVIDER_TYPES)}


@router.get("/connections/{connection_id}/models", operation_id="getCachedProviderModels")
async def get_models(
    connection_id: UUID,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> dict[str, object]:
    return await cached_models(store, identity(current), connection_id)


@router.post(
    "/connections/{connection_id}/models/refresh",
    operation_id="refreshProviderModels",
    description=PROBE_NOTICE,
)
async def refresh(
    connection_id: UUID,
    payload: ProviderProbeRequest,
    request: Request,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
    budget: ProbeBudget = Depends(model_refresh_budget),
    transport: httpx.AsyncBaseTransport | None = Depends(model_refresh_transport),
) -> dict[str, object]:
    consent = payload.consent
    result = await refresh_models(
        store,
        identity(current),
        ConnectionRoute(
            connection_id,
            consent.config_version,
            consent.model_id,
            frozenset(consent.data_categories),
        ),
        accepted=consent.accepted,
        operation_id=payload.operation_id,
        temporary_handle=payload.temporary_handle,
        registry=request_registry(request) if payload.temporary_handle else None,
        budget=budget,
        transport=transport,
    )
    response.headers["X-Provider-Probe-Notice"] = PROBE_NOTICE
    return result
