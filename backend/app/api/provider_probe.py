"""Explicit owner/CSRF-bound connection test; budget denied unless separately provided."""

from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Request, Response
from pydantic import Field, model_validator

from app.api.provider_connections import (
    DataConsent,
    ProviderRoute,
    StrictInput,
    identity,
    provider_store,
    request_registry,
)
from app.core.auth import AuthenticatedSession, require_authenticated_session
from app.services.provider_connection_dispatch import ConnectionRoute
from app.services.provider_connections import ProviderConnectionStore
from app.services.provider_probe import (
    PROBE_NOTICE,
    ProbeBudget,
    UnavailableProbeBudget,
    probe_connection,
)

router = APIRouter(
    prefix="/api/providers/connections", tags=["Providers"], route_class=ProviderRoute
)


class ProviderProbeRequest(StrictInput):
    operation_id: UUID = Field(strict=False)
    consent: DataConsent
    temporary_handle: str | None = Field(default=None, min_length=32, max_length=200, repr=False)

    @model_validator(mode="after")
    def no_explicit_null_handle(self) -> "ProviderProbeRequest":
        if "temporary_handle" in self.model_fields_set and self.temporary_handle is None:
            raise ValueError("Temporary handle must be a string.")
        return self


def probe_budget() -> ProbeBudget:
    return UnavailableProbeBudget()


def probe_transport() -> httpx.AsyncBaseTransport | None:
    """Only server/test dependency injection supplies a transport; never client input."""
    return None


@router.post(
    "/{connection_id}/test", operation_id="testProviderConnection", description=PROBE_NOTICE
)
async def test_connection(
    connection_id: UUID,
    payload: ProviderProbeRequest,
    request: Request,
    response: Response,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
    budget: ProbeBudget = Depends(probe_budget),
    transport: httpx.AsyncBaseTransport | None = Depends(probe_transport),
) -> dict[str, object]:
    consent = payload.consent
    route = ConnectionRoute(
        connection_id, consent.config_version, consent.model_id, frozenset(consent.data_categories)
    )
    registry = request_registry(request) if payload.temporary_handle is not None else None
    result = await probe_connection(
        store,
        identity(current),
        route,
        accepted=consent.accepted,
        operation_id=payload.operation_id,
        temporary_handle=payload.temporary_handle,
        registry=registry,
        budget=budget,
        transport=transport,
    )
    response.headers["X-Provider-Probe-Notice"] = PROBE_NOTICE
    return result
