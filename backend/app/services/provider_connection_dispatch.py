"""Owner/session/version-bound operations and transactional HTTP send authority."""

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx

from app.core.credential_crypto import CredentialFailure, decrypt_secret
from app.core.product_mode import catalog_only
from app.core.provider_target import ApprovedTarget, TargetValidationError, approve_target
from app.core.temporary_credentials import (
    OPERATION_SECONDS,
    MemoryOnly,
    TemporaryBinding,
    TemporaryCredentialRegistry,
    TemporaryLease,
)
from app.services.provider_connection_events import subscribe
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore
from app.services.provider_gateway import ProviderError, ProviderErrorCode

DATA_CATEGORIES = frozenset(
    {
        "probe",
        "learning_goal",
        "profile_evidence",
        "limited_history",
        "content_for_review",
    }
)
PURPOSES = frozenset({"generation", "connection_test", "model_refresh"})
HTTP_TIMEOUT = httpx.Timeout(connect=5, read=60, write=10, pool=5)


@dataclass(frozen=True, slots=True)
class ConnectionRoute:
    connection_id: UUID
    config_version: int
    model_id: str
    data_categories: frozenset[str]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.connection_id, UUID)
            or type(self.config_version) is not int
            or self.config_version < 1
            or not isinstance(self.model_id, str)
            or not 1 <= len(self.model_id) <= 160
            or not self.model_id.strip()
            or any(ord(c) < 32 or ord(c) == 127 for c in self.model_id)
            or type(self.data_categories) is not frozenset
            or not self.data_categories
            or not self.data_categories <= DATA_CATEGORIES
        ):
            raise CredentialFailure("VALIDATION_ERROR")


@dataclass(frozen=True, slots=True)
class ConnectionConsent:
    """Only server code resolves a consent record against the exact selected route."""

    route: ConnectionRoute
    accepted: bool = False


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """Bound declaration, not a real-model verification or an inferred model-name feature."""

    connection_id: UUID
    config_version: int
    model_id: str
    version: str
    streaming: bool | None = None
    structured_output: bool | None = None
    structured_transport: str = "json_schema"

    def __post_init__(self) -> None:
        if (
            not 1 <= len(self.version) <= 100
            or self.structured_transport not in {"json_schema", "json_object", "text_json"}
            or any(
                v is not None and type(v) is not bool
                for v in (self.streaming, self.structured_output)
            )
        ):
            raise CredentialFailure("VALIDATION_ERROR")


@dataclass(frozen=True, slots=True)
class DispatchRequest(MemoryOnly):
    identity: CredentialIdentity = field(repr=False)
    route: ConnectionRoute
    consent: ConnectionConsent
    capabilities: ModelCapabilities
    operation_id: UUID
    purpose: str = "generation"
    temporary_handle: str | None = field(default=None, repr=False)

    def validate(self) -> None:
        if self.purpose not in PURPOSES:
            raise CredentialFailure("VALIDATION_ERROR")
        if self.consent.accepted is not True or self.consent.route != self.route:
            raise CredentialFailure("CONSENT_REQUIRED")
        c, r = self.capabilities, self.route
        if (c.connection_id, c.config_version, c.model_id) != (
            r.connection_id,
            r.config_version,
            r.model_id,
        ):
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        if self.purpose != "generation" and r.data_categories != frozenset({"probe"}):
            raise CredentialFailure("CONSENT_REQUIRED")
        if self.purpose == "generation" and catalog_only():
            raise CredentialFailure("FEATURE_UNAVAILABLE")


AttemptAuthorizer = Callable[[DispatchRequest], Awaitable[None]]


class ConnectionOperation(MemoryOnly):
    """Use within one task/context; no reusable decrypted credentials or send permit."""

    def __init__(
        self,
        store: ProviderConnectionStore,
        request: DispatchRequest,
        authorize_attempt: AttemptAuthorizer,
        *,
        transport: httpx.AsyncBaseTransport | None,
    ) -> None:
        self.store, self.request = store, request
        self.authorize_attempt, self.transport = authorize_attempt, transport
        self._task = asyncio.current_task()
        self._lease: TemporaryLease | None = None
        self._active = False
        self._expires_at: datetime | None = None
        self._deadline = 0.0
        self._reason: str | None = None
        self._busy = False
        self._response: httpx.Response | None = None
        self._client: httpx.AsyncClient | None = None

    def __repr__(self) -> str:
        return "ConnectionOperation(<redacted>)"

    def _check(self) -> None:
        if not self._active or asyncio.current_task() is not self._task:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        self.request.validate()
        if self._expires_at is None or datetime.now(timezone.utc) >= self._expires_at:
            raise CredentialFailure("CREDENTIAL_EXPIRED")
        if asyncio.get_running_loop().time() >= self._deadline:
            raise ProviderError(ProviderErrorCode.TIMEOUT)

    def _cancel(self, reason: str) -> None:
        if self._active:
            self._reason = reason
            assert self._task is not None
            self._task.cancel()

    async def _observe(self) -> None:
        while self._active:
            # Leave scheduling headroom within the ADR's 1s poll + 1s check bound.
            await asyncio.sleep(0.9)
            r = self.request
            valid = await TemporaryCredentialRegistry._valid(
                lambda: self.store.valid_version(
                    r.identity, r.route.connection_id, r.route.config_version
                )
            )
            if not valid:
                self._cancel("CREDENTIAL_UNAVAILABLE")
                return

    @asynccontextmanager
    async def activate(self, registry: TemporaryCredentialRegistry | None) -> AsyncIterator[None]:
        r = self.request
        r.validate()
        view = await self.store.read(r.identity, r.route.connection_id)
        if view["config_version"] != r.route.config_version:
            raise CredentialFailure("VERSION_CONFLICT")
        if view["provider_type"] != "openai-compatible":
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
        if not view["enabled"]:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        expiry = datetime.fromisoformat(str(view["credential_expires_at"]))
        self._expires_at = expiry
        remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            raise CredentialFailure("CREDENTIAL_EXPIRED")
        mode = view["credential_mode"]
        if (mode == "temporary") != (r.temporary_handle is not None):
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        if mode == "temporary" and registry is None:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        self._active = True
        loop = asyncio.get_running_loop()
        self._deadline = loop.time() + min(OPERATION_SECONDS, remaining)
        timer = loop.call_at(
            self._deadline,
            self._cancel,
            ("CREDENTIAL_EXPIRED" if remaining <= OPERATION_SECONDS else "TIMEOUT"),
        )

        def changed(cid: UUID) -> None:
            if cid == r.route.connection_id:
                if registry is not None:
                    registry.revoke(cid)
                self._cancel("CREDENTIAL_UNAVAILABLE")

        unsubscribe = subscribe(changed)
        observer = asyncio.create_task(self._observe())
        try:
            if mode == "temporary":
                assert registry is not None and r.temporary_handle is not None
                binding = TemporaryBinding(
                    r.identity.user_id,
                    r.identity.session_hash,
                    r.route.connection_id,
                    r.route.config_version,
                    r.operation_id,
                    r.purpose,
                    r.route.model_id,
                )
                async with registry.lease(r.temporary_handle, binding) as lease:
                    self._lease = lease
                    yield
            else:
                yield
        except asyncio.CancelledError:
            if self._reason == "TIMEOUT":
                raise ProviderError(ProviderErrorCode.TIMEOUT) from None
            if self._reason is not None:
                raise CredentialFailure(self._reason) from None
            raise
        finally:
            self._active = False
            self._lease = None
            timer.cancel()
            unsubscribe()
            observer.cancel()
            with suppress(asyncio.CancelledError):
                await observer
            if self._response is not None:
                await self._response.aclose()
            if self._client is not None:
                await self._client.aclose()

    @asynccontextmanager
    async def send(
        self,
        body: dict[str, object],
        *,
        stream: bool = False,
    ) -> AsyncIterator[httpx.Response]:
        self._check()
        if self._busy:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        self._busy = True
        response: httpx.Response | None = None
        wire: httpx.Request | None = None
        secret: dict[str, str] = {}
        try:
            r = self.request
            await self.store._prepare()
            async with self.store.factory() as db, db.begin():
                row = await self.store._row(
                    db, r.identity, r.route.connection_id, r.route.config_version
                )
                self._check()
                if not row.enabled or row.provider_type != "openai-compatible":
                    raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
                if row.credential_expires_at <= datetime.now(timezone.utc):
                    raise CredentialFailure("CREDENTIAL_EXPIRED")
                try:
                    target = await asyncio.to_thread(
                        approve_target,
                        row.base_url,
                        policy=self.store.policy,
                        resolver=self.store.resolver,
                    )
                except TargetValidationError:
                    raise ProviderError(ProviderErrorCode.INVALID_TARGET) from None
                await self.store._session(db, r.identity)
                self._check()
                # Mandatory injected budget/operation authorization, no default grant.
                await self.authorize_attempt(r)
                self._check()
                if row.credential_mode == "temporary":
                    if self._lease is None:
                        raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
                    secret = self._lease.read_secret()
                elif row.credential_mode == "persistent":
                    if row.encrypted_api_key is None:
                        raise CredentialFailure("CREDENTIAL_MISSING")
                    from app.services.provider_connections import credential_context

                    secret = decrypt_secret(
                        row.encrypted_api_key, credential_context(row), self.store._keys()
                    )
                elif row.credential_mode != "none":
                    raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
                # Only explicitly keyless connections omit auth. Never use system Key.
                if row.credential_mode != "none" and (
                    set(secret) != {"api_key"}
                    or not secret.get("api_key")
                    or any(ord(c) < 33 or ord(c) > 126 for c in secret["api_key"])
                ):
                    raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
                endpoint, host = wire_target(target)
                headers = {
                    "Host": host,
                    "Accept": ("text/event-stream" if stream else "application/json"),
                }
                if secret:
                    headers["Authorization"] = "Bearer " + secret["api_key"]
                sent = False

                async def trace(event: str, info: dict[str, Any]) -> None:
                    nonlocal sent
                    if event.endswith(
                        ("send_request_headers.started", "send_request_body.started")
                    ):
                        self._check()
                        await self.store._session(db, r.identity)
                        self._check()
                    elif event.endswith("send_request_body.complete") and not sent:
                        # Actual network send is complete. Keep row lock through auth AND data.
                        sent = True
                        await db.commit()

                async with httpx.AsyncClient(
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=HTTP_TIMEOUT,
                    http2=False,
                ) as client:
                    self._client = client
                    wire = client.build_request("POST", endpoint, headers=headers, json=body)
                    wire.extensions.update(sni_hostname=target.hostname, trace=trace)
                    secret.clear()
                    headers.clear()
                    response = await client.send(wire, stream=True, follow_redirects=False)
                    # Mock/custom transports may not implement trace: never release early.
                    if not sent:
                        await db.commit()
                    self._response = response
                    self._check()
                    yield response
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCode.TIMEOUT) from None
        except httpx.RequestError:
            raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE) from None
        finally:
            secret.clear()
            if wire is not None:
                wire.headers.pop("Authorization", None)
            if response is not None:
                await response.aclose()
            self._response = None
            self._client = None
            self._busy = False


def wire_target(target: ApprovedTarget) -> tuple[str, str]:
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(target.url)
    ip = target.connect_ip
    netloc = f"[{ip}]" if ":" in ip else ip
    endpoint = urlunsplit(
        (
            parsed.scheme,
            f"{netloc}:{target.port}",
            parsed.path.rstrip("/") + "/chat/completions",
            "",
            "",
        )
    )
    hostname = f"[{target.hostname}]" if ":" in target.hostname else target.hostname
    host = (
        hostname
        if target.port == (443 if parsed.scheme == "https" else 80)
        else (f"{hostname}:{target.port}")
    )
    return endpoint, host
