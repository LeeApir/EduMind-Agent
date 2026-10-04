"""Owner/CSRF versioned four-profile metadata API, never contacts Provider."""

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field, model_validator

from app.api.provider_connections import (
    Category,
    ProviderRoute,
    StrictInput,
    identity,
    provider_store,
)
from app.core.auth import AuthenticatedSession, require_authenticated_session
from app.services.model_preferences import Fallback, RouteChoice, list_preferences, write_preference
from app.services.provider_connection_dispatch import ConnectionRoute
from app.services.provider_connections import ProviderConnectionStore
from app.services.provider_gateway import ProviderErrorCode, TaskProfile

router = APIRouter(prefix="/api/model-preferences", tags=["Providers"], route_class=ProviderRoute)


class RouteInput(StrictInput):
    connection_id: UUID = Field(strict=False)
    config_version: int = Field(ge=1)
    model_id: str = Field(min_length=1, max_length=160)
    data_categories: list[Category] = Field(min_length=1, max_length=5)

    def route(self) -> ConnectionRoute:
        return ConnectionRoute(
            self.connection_id, self.config_version, self.model_id, frozenset(self.data_categories)
        )

    @model_validator(mode="after")
    def validate_binding(self) -> "RouteInput":
        if len(set(self.data_categories)) != len(self.data_categories):
            raise ValueError("Duplicate data categories.")
        self.route()
        return self


class FallbackInput(StrictInput):
    route: RouteInput
    on_errors: list[str] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_errors(self) -> "FallbackInput":
        if len(set(self.on_errors)) != len(self.on_errors) or not set(self.on_errors) <= {
            "RATE_LIMITED",
            "TIMEOUT",
            "TEMPORARILY_UNAVAILABLE",
        }:
            raise ValueError("Invalid fallback errors.")
        return self


class PreferenceWrite(StrictInput):
    expected_version: int = Field(ge=0)
    route: RouteInput
    fallbacks: list[FallbackInput] = Field(max_length=3)
    consent_accepted: bool


@router.get("", operation_id="getModelPreferences")
async def get_preferences(
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> dict[str, object]:
    return await list_preferences(store, identity(current))


@router.put("/{task_profile}", operation_id="setModelPreference")
async def set_preference(
    task_profile: TaskProfile,
    payload: PreferenceWrite,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> dict[str, object]:
    return await write_preference(
        store,
        identity(current),
        task_profile,
        payload.expected_version,
        RouteChoice(
            payload.route.route(),
            tuple(
                Fallback(f.route.route(), frozenset(ProviderErrorCode(e) for e in f.on_errors))
                for f in payload.fallbacks
            ),
            payload.consent_accepted,
        ),
    )
