"""Transactional credential storage; network invocation remains a later task."""

import ipaddress
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID, uuid4

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.credential_crypto import (
    CredentialFailure,
    CredentialKeyring,
    decrypt_secret,
    encrypt_secret,
    envelope_key_id,
    rewrap_secret,
)
from app.core.provider_target import Resolver, TargetPolicy, approve_target, resolve_addresses
from app.models.auth import GuestSessionRecord
from app.models.provider_connections import ProviderConnection

PROVIDER_TYPES = {"openai-compatible", "ollama", "anthropic", "gemini", "spark"}


@dataclass(frozen=True)
class CredentialIdentity:
    user_id: UUID
    session_hash: str = field(repr=False)


def credential_context(row: ProviderConnection) -> bytes:
    return json.dumps(
        {
            "owner": str(row.user_id),
            "connection": str(row.id),
            "session": row.originating_session_hash,
            "provider_type": row.provider_type,
            "target": row.base_url,
            "credential_version": row.credential_version,
            "expires_at": row.credential_expires_at.astimezone(timezone.utc).isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def connection_view(row: ProviderConnection) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    state = "present" if row.encrypted_api_key is not None else "missing"
    if row.credential_expires_at <= now:
        state = "expired"
    elif not row.enabled or row.deleted:
        state = "revoked"
    return {
        "id": str(row.id),
        "provider_type": row.provider_type,
        "display_name": row.display_name,
        "base_url": row.base_url,
        "is_local": row.is_local,
        "enabled": row.enabled,
        "config_version": row.config_version,
        "credential_mode": row.credential_mode,
        "credential_state": state,
        "credential_expires_at": row.credential_expires_at.isoformat(),
    }


async def clean_expired_credentials(
    factory: async_sessionmaker[AsyncSession],
    *,
    batch_size: int = 100,
) -> int:
    """Clear envelopes without any KEK; absent/revoked auth parent fails closed."""
    now = datetime.now(timezone.utc)
    async with factory() as db, db.begin():
        parent = exists(
            select(GuestSessionRecord.token_hash).where(
                GuestSessionRecord.token_hash == ProviderConnection.originating_session_hash,
                GuestSessionRecord.user_id == ProviderConnection.user_id,
                GuestSessionRecord.expires_at > now,
            )
        )
        rows = (
            await db.scalars(
                select(ProviderConnection)
                .where(
                    ProviderConnection.encrypted_api_key.is_not(None),
                    or_(ProviderConnection.credential_expires_at <= now, ~parent),
                )
                .order_by(ProviderConnection.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        for row in rows:
            row.encrypted_api_key = None
            row.credential_key_id = None
            row.enabled = False
            row.config_version += 1
            row.credential_version += 1
            row.updated_at = now
        return len(rows)


class ProviderConnectionStore:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        keyring: CredentialKeyring | None,
        *,
        policy: TargetPolicy | None = None,
        resolver: Resolver = resolve_addresses,
    ) -> None:
        self.factory = factory
        self.keyring = keyring
        self.policy = policy or TargetPolicy()
        self.resolver = resolver

    def _keys(self) -> CredentialKeyring:
        if self.keyring is None:
            raise CredentialFailure("CONFIGURATION_MISSING")
        return self.keyring

    async def _prepare(self) -> None:
        # Also handles restart/cleanup outages before the next credential operation.
        while await clean_expired_credentials(self.factory) == 100:
            pass

    async def _session(self, db: AsyncSession, identity: CredentialIdentity) -> GuestSessionRecord:
        auth = await db.scalar(
            select(GuestSessionRecord).where(
                GuestSessionRecord.token_hash == identity.session_hash,
                GuestSessionRecord.user_id == identity.user_id,
            )
        )
        if auth is None or auth.expires_at <= datetime.now(timezone.utc):
            raise CredentialFailure("UNAUTHORIZED")
        return auth

    async def _row(
        self,
        db: AsyncSession,
        identity: CredentialIdentity,
        connection_id: UUID,
        expected_version: int | None = None,
        *,
        include_deleted: bool = False,
    ) -> ProviderConnection:
        await self._session(db, identity)
        row = await db.scalar(
            select(ProviderConnection)
            .where(
                ProviderConnection.id == connection_id,
                ProviderConnection.user_id == identity.user_id,
                ProviderConnection.originating_session_hash == identity.session_hash,
            )
            .with_for_update()
        )
        await self._session(db, identity)
        if row is None or (row.deleted and not include_deleted):
            raise CredentialFailure("NOT_FOUND")
        if expected_version is not None and row.config_version != expected_version:
            raise CredentialFailure("VERSION_CONFLICT")
        return row

    def _target(self, url: str) -> tuple[str, bool]:
        if not 1 <= len(url) <= 500:
            raise CredentialFailure("VALIDATION_ERROR")
        approved = approve_target(url, policy=self.policy, resolver=self.resolver)
        parsed = urlsplit(url)
        host = approved.hostname
        if ":" in host:
            host = "[" + host + "]"
        default_port = 443 if parsed.scheme == "https" else 80
        netloc = host if approved.port == default_port else f"{host}:{approved.port}"
        normalized = urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))
        return normalized, all(not ipaddress.ip_address(ip).is_global for ip in approved.addresses)

    @staticmethod
    def _validate(provider_type: str, display_name: str, mode: str) -> None:
        if (
            provider_type not in PROVIDER_TYPES
            or not 1 <= len(display_name) <= 80
            or mode not in {"persistent", "temporary", "none"}
        ):
            raise CredentialFailure("VALIDATION_ERROR")

    async def create(
        self,
        identity: CredentialIdentity,
        *,
        provider_type: str,
        display_name: str,
        base_url: str,
        mode: str,
        secret: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        await self._prepare()
        keys = self._keys()
        self._validate(provider_type, display_name, mode)
        if (mode == "persistent") != (secret is not None):
            raise CredentialFailure("VALIDATION_ERROR")
        async with self.factory() as db, db.begin():
            auth = await self._session(db, identity)
            target, local = self._target(base_url)
            await self._session(db, identity)
            now = datetime.now(timezone.utc)
            row = ProviderConnection(
                id=uuid4(),
                user_id=identity.user_id,
                originating_session_hash=identity.session_hash,
                provider_type=provider_type,
                display_name=display_name,
                base_url=target,
                is_local=local,
                enabled=True,
                deleted=False,
                config_version=1,
                credential_version=1,
                credential_mode=mode,
                credential_expires_at=auth.expires_at,
                created_at=now,
                updated_at=now,
            )
            if secret is not None:
                row.encrypted_api_key = encrypt_secret(secret, credential_context(row), keys)
                row.credential_key_id = keys.active_id
            db.add(row)
            await db.flush()
            return connection_view(row)

    async def read(self, identity: CredentialIdentity, connection_id: UUID) -> dict[str, object]:
        await self._prepare()
        async with self.factory() as db, db.begin():
            return connection_view(await self._row(db, identity, connection_id))

    async def replace(
        self,
        identity: CredentialIdentity,
        connection_id: UUID,
        expected_version: int,
        *,
        secret: Mapping[str, str] | None = None,
        clear_secret: bool = False,
        display_name: str | None = None,
        base_url: str | None = None,
        provider_type: str | None = None,
        enabled: bool | None = None,
        mode: str | None = None,
    ) -> dict[str, object]:
        await self._prepare()
        keys = self._keys()
        async with self.factory() as db, db.begin():
            row = await self._row(db, identity, connection_id, expected_version)
            if row.credential_expires_at <= datetime.now(timezone.utc):
                raise CredentialFailure("CREDENTIAL_EXPIRED")
            kind, name, new_mode = (
                provider_type or row.provider_type,
                display_name if display_name is not None else row.display_name,
                mode or row.credential_mode,
            )
            self._validate(kind, name, new_mode)
            target, local = self._target(base_url or row.base_url)
            changed = (
                kind != row.provider_type
                or target != row.base_url
                or new_mode != row.credential_mode
            )
            if changed or clear_secret or secret is not None:
                row.encrypted_api_key = None
                row.credential_key_id = None
                row.credential_version += 1
            row.provider_type, row.display_name, row.base_url = kind, name, target
            row.is_local, row.credential_mode = local, new_mode
            if enabled is not None:
                row.enabled = enabled
            if secret is not None:
                if new_mode != "persistent":
                    raise CredentialFailure("VALIDATION_ERROR")
                row.encrypted_api_key = encrypt_secret(secret, credential_context(row), keys)
                row.credential_key_id = keys.active_id
            row.config_version += 1
            row.updated_at = datetime.now(timezone.utc)
            await db.flush()
            return connection_view(row)

    async def delete(
        self, identity: CredentialIdentity, connection_id: UUID, expected_version: int
    ) -> None:
        await self._prepare()
        async with self.factory() as db, db.begin():
            row = await self._row(db, identity, connection_id, include_deleted=True)
            if row.deleted and row.config_version == expected_version + 1:
                return
            if row.config_version != expected_version:
                raise CredentialFailure("VERSION_CONFLICT")
            row.encrypted_api_key = None
            row.credential_key_id = None
            row.enabled, row.deleted = False, True
            row.config_version += 1
            row.credential_version += 1
            row.updated_at = datetime.now(timezone.utc)

    async def decrypt(
        self,
        identity: CredentialIdentity,
        connection_id: UUID,
        expected_version: int,
    ) -> dict[str, str]:
        """Internal only; callers must apply T007 dispatch lock, consent and deadline."""
        await self._prepare()
        async with self.factory() as db, db.begin():
            row = await self._row(db, identity, connection_id, expected_version)
            if row.credential_expires_at <= datetime.now(timezone.utc):
                raise CredentialFailure("CREDENTIAL_EXPIRED")
            if not row.enabled or row.encrypted_api_key is None:
                raise CredentialFailure("CREDENTIAL_MISSING")
            return decrypt_secret(row.encrypted_api_key, credential_context(row), self._keys())

    async def valid_version(
        self, identity: CredentialIdentity, connection_id: UUID, version: int
    ) -> bool:
        """Revocation observer for local operations, not a network send permission."""
        try:
            async with self.factory() as db, db.begin():
                row = await self._row(db, identity, connection_id, version)
                return row.enabled and row.credential_expires_at > datetime.now(timezone.utc)
        except CredentialFailure:
            return False

    async def rotate_batch(self, *, limit: int = 100) -> tuple[int, int]:
        await self._prepare()
        keys = self._keys()
        rotated, failed = 0, 0
        async with self.factory() as db, db.begin():
            rows = (
                await db.scalars(
                    select(ProviderConnection)
                    .where(
                        ProviderConnection.encrypted_api_key.is_not(None),
                        ProviderConnection.deleted.is_(False),
                        ProviderConnection.credential_key_id != keys.active_id,
                        ProviderConnection.credential_expires_at > datetime.now(timezone.utc),
                    )
                    .order_by(ProviderConnection.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for row in rows:
                if rotated + failed >= limit:
                    break
                assert row.encrypted_api_key is not None
                if row.credential_expires_at <= datetime.now(timezone.utc):
                    continue
                try:
                    if envelope_key_id(row.encrypted_api_key) != row.credential_key_id:
                        raise CredentialFailure()
                    row.encrypted_api_key = rewrap_secret(
                        row.encrypted_api_key, credential_context(row), keys
                    )
                    row.credential_key_id = keys.active_id
                    row.updated_at = datetime.now(timezone.utc)
                    rotated += 1
                except CredentialFailure:
                    failed += 1
            return rotated, failed
