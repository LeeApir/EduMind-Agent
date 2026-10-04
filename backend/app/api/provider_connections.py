"""Owner/session-scoped provider CRUD and memory-only uploads, no model invocation."""

from collections.abc import Callable, Coroutine
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.auth import AuthenticatedSession, AuthFailure, require_authenticated_session
from app.core.config import ConfigurationError
from app.core.credential_crypto import CredentialFailure, CredentialKeyring
from app.core.database import DatabaseRuntime, database_session_factory
from app.core.provider_target import (
    TargetValidationError,
    resolve_addresses,
    target_policy_from_environment,
)
from app.core.temporary_credentials import TemporaryCredentialRegistry
from app.services.provider_connection_dispatch import ConnectionRoute
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import ProviderError
from app.services.temporary_credentials import TemporaryCredentialService

CACHE_HEADERS = {"Cache-Control": "private, no-store"}
ProviderType = Literal["openai-compatible", "ollama", "anthropic", "gemini", "spark"]
CredentialMode = Literal["persistent", "temporary", "none"]
Category = Literal[
    "probe", "learning_goal", "profile_evidence", "limited_history", "content_for_review"
]

# All messages are fixed; none interpolate client input, secrets or SQL/library errors.
ERRORS = {
    "BUDGET_NOT_AUTHORIZED": (403, "Provider request budget is not authorized."),
    "UNAUTHORIZED": (401, "Session missing or expired."),
    "NOT_FOUND": (404, "Resource not found."),
    "VERSION_CONFLICT": (409, "Connection version no longer matches."),
    "FEATURE_UNAVAILABLE": (409, "Dynamic generation is not enabled."),
    "CONSENT_REQUIRED": (409, "Consent does not match the selected route."),
    "CREDENTIAL_EXPIRED": (409, "Provider credential expired."),
    "VALIDATION_ERROR": (422, "Request did not satisfy the schema."),
    "INVALID_TARGET": (422, "Provider target is not permitted."),
    "CAPABILITY_UNAVAILABLE": (422, "Selected provider capability is unavailable."),
    "RATE_LIMITED": (429, "Selected provider is rate limited."),
    "AUTHENTICATION_FAILED": (502, "Selected provider rejected authentication."),
    "INVALID_OUTPUT": (502, "Selected provider returned invalid output."),
    "TIMEOUT": (504, "Selected provider operation timed out."),
    "CONFIGURATION_MISSING": (503, "Provider credential configuration is unavailable."),
    "CREDENTIAL_MISSING": (503, "Provider credential is missing."),
    "CREDENTIAL_UNAVAILABLE": (503, "Provider credential is unavailable."),
    "TEMPORARILY_UNAVAILABLE": (503, "Provider service is temporarily unavailable."),
}


def safe_error(code: str) -> JSONResponse:
    if code not in ERRORS:
        code = "CREDENTIAL_UNAVAILABLE"
    status, message = ERRORS[code]
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message, "retryable": False},
        headers=CACHE_HEADERS,
    )


class ProviderRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
                response.headers.update(CACHE_HEADERS)
                return response
            except AuthFailure as error:
                return JSONResponse(
                    status_code=error.status_code,
                    content={
                        "code": error.code,
                        "message": error.message,
                        "retryable": False,
                    },
                    headers=CACHE_HEADERS,
                )
            except CredentialFailure as error:
                return safe_error(error.code)
            except ProviderError as error:
                return safe_error(error.code.value)
            except TargetValidationError:
                return safe_error("INVALID_TARGET")
            except RequestValidationError:
                return safe_error("VALIDATION_ERROR")
            except ConfigurationError:
                return safe_error("CONFIGURATION_MISSING")
            except SQLAlchemyError:
                return safe_error("TEMPORARILY_UNAVAILABLE")

        return handler


router = APIRouter(
    prefix="/api/providers/connections", tags=["Providers"], route_class=ProviderRoute
)


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)


class ProviderSecret(StrictInput):
    api_key: SecretStr = Field(min_length=1, max_length=4096, repr=False)
    api_secret: SecretStr | None = Field(default=None, min_length=1, max_length=4096, repr=False)
    app_id: SecretStr | None = Field(default=None, min_length=1, max_length=4096, repr=False)

    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "ProviderSecret":
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("Secret fields must be strings.")
        return self

    def values(self) -> dict[str, str]:
        return {
            name: value.get_secret_value()
            for name in ("api_key", "api_secret", "app_id")
            if (value := getattr(self, name)) is not None
        }


class ConnectionCreate(StrictInput):
    provider_type: ProviderType
    display_name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    enabled: bool = True
    credential_mode: CredentialMode
    secret: ProviderSecret | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def credential_consistency(self) -> "ConnectionCreate":
        if (self.credential_mode == "persistent") != (self.secret is not None) or (
            self.credential_mode != "persistent" and "secret" in self.model_fields_set
        ):
            raise ValueError("Credential mode and secret do not match.")
        return self


class ConnectionPatch(StrictInput):
    provider_type: ProviderType | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    base_url: str | None = Field(default=None, min_length=1, max_length=500)
    enabled: bool | None = None
    credential_mode: CredentialMode | None = None
    secret: ProviderSecret | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def nonempty_patch(self) -> "ConnectionPatch":
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set if name != "secret"
        ):
            raise ValueError("Patch must contain non-null metadata or a secret field.")
        return self


class DataConsent(StrictInput):
    accepted: bool
    config_version: int = Field(ge=1)
    model_id: str = Field(min_length=1, max_length=160)
    data_categories: list[Category] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def unique_categories(self) -> "DataConsent":
        if len(set(self.data_categories)) != len(self.data_categories):
            raise ValueError("Duplicate data categories.")
        return self


class TemporaryUpload(StrictInput):
    secret: ProviderSecret = Field(repr=False)
    consent: DataConsent
    operation_id: UUID = Field(strict=False)
    purpose: Literal["connection_test", "model_refresh", "generation"]


def identity(current: AuthenticatedSession) -> CredentialIdentity:
    return CredentialIdentity(current.user.id, current.record.token_hash)


def request_registry(request: Request) -> TemporaryCredentialRegistry:
    runtime = getattr(request.state, "database_runtime", None)
    if not isinstance(runtime, DatabaseRuntime) or runtime.temporary_credentials is None:
        raise CredentialFailure("CONFIGURATION_MISSING")
    return runtime.temporary_credentials


def provider_store(
    request: Request,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    factory: async_sessionmaker[AsyncSession] = Depends(database_session_factory),
) -> ProviderConnectionStore:
    # Authentication and CSRF are dependencies of store construction, before any KEK/DNS access.
    try:
        policy = target_policy_from_environment()
    except TargetValidationError:
        raise CredentialFailure("CONFIGURATION_MISSING") from None
    runtime = getattr(request.state, "database_runtime", None)
    registry = runtime.temporary_credentials if isinstance(runtime, DatabaseRuntime) else None
    return ProviderConnectionStore(
        factory,
        None,
        policy=policy,
        resolver=resolve_addresses,
        on_change=registry.revoke if registry is not None else None,
        keyring_loader=CredentialKeyring.from_environment,
    )


@router.get("", operation_id="listProviderConnections")
async def list_connections(
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> dict[str, object]:
    return {"items": await store.list(identity(current))}


@router.post("", status_code=201, operation_id="createProviderConnection")
async def create_connection(
    payload: ConnectionCreate,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> dict[str, object]:
    values = payload.secret.values() if payload.secret is not None else None
    try:
        return await store.create(
            identity(current),
            provider_type=payload.provider_type,
            display_name=payload.display_name,
            base_url=payload.base_url,
            mode=payload.credential_mode,
            enabled=payload.enabled,
            secret=values,
        )
    finally:
        if values is not None:
            values.clear()


@router.get("/{connection_id}", operation_id="getProviderConnection")
async def read_connection(
    connection_id: UUID,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> dict[str, object]:
    return await store.read(identity(current), connection_id)


@router.patch("/{connection_id}", operation_id="updateProviderConnection")
async def patch_connection(
    connection_id: UUID,
    payload: ConnectionPatch,
    if_match: str = Header(alias="If-Match", pattern="^[1-9][0-9]*$", max_length=20),
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> dict[str, object]:
    # Check owner and mode before extracting replacement plaintext.
    view = await store.read(identity(current), connection_id)
    if view["config_version"] != int(if_match):
        raise CredentialFailure("VERSION_CONFLICT")
    if (
        payload.secret is not None
        and (payload.credential_mode or view["credential_mode"]) != "persistent"
    ):
        raise CredentialFailure("VALIDATION_ERROR")
    values = payload.secret.values() if payload.secret is not None else None
    try:
        return await store.replace(
            identity(current),
            connection_id,
            int(if_match),
            secret=values,
            clear_secret="secret" in payload.model_fields_set and payload.secret is None,
            display_name=payload.display_name,
            base_url=payload.base_url,
            provider_type=payload.provider_type,
            enabled=payload.enabled,
            mode=payload.credential_mode,
        )
    finally:
        if values is not None:
            values.clear()


@router.delete("/{connection_id}", status_code=204, operation_id="deleteProviderConnection")
async def delete_connection(
    connection_id: UUID,
    if_match: str = Header(alias="If-Match", pattern="^[1-9][0-9]*$", max_length=20),
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> Response:
    await store.delete(identity(current), connection_id, int(if_match))
    return Response(status_code=204, headers=CACHE_HEADERS)


@router.post(
    "/{connection_id}/temporary-credentials",
    status_code=201,
    operation_id="provideTemporaryCredential",
)
async def upload_temporary_credential(
    connection_id: UUID,
    payload: TemporaryUpload,
    request: Request,
    current: AuthenticatedSession = Depends(require_authenticated_session),
    store: ProviderConnectionStore = Depends(provider_store),
) -> dict[str, object]:
    who = identity(current)
    # Foreign IDs fail before consent-dependent errors or secret extraction/registry access.
    view = await store.read(who, connection_id)
    consent = payload.consent
    if view["config_version"] != consent.config_version:
        raise CredentialFailure("VERSION_CONFLICT")
    if not consent.accepted or (
        payload.purpose != "generation" and consent.data_categories != ["probe"]
    ):
        raise CredentialFailure("CONSENT_REQUIRED")
    ConnectionRoute(
        connection_id, consent.config_version, consent.model_id, frozenset(consent.data_categories)
    )
    registry = request_registry(request)
    values = payload.secret.values()
    try:
        service = TemporaryCredentialService(store, registry)
        handle, binding = await service.register(
            who,
            connection_id,
            consent.config_version,
            payload.operation_id,
            payload.purpose,
            consent.model_id,
            values,
        )
        return {
            "handle": handle,
            "expires_at": registry.pending_expires_at(handle, binding).isoformat(),
            "operation_id": str(payload.operation_id),
            "config_version": consent.config_version,
        }
    finally:
        values.clear()
