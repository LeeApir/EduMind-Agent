"""Authenticate temporary credential uploads against durable connection metadata."""

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from app.core.credential_crypto import CredentialFailure
from app.core.temporary_credentials import TemporaryBinding, TemporaryCredentialRegistry
from app.services.provider_connections import CredentialIdentity, ProviderConnectionStore


class TemporaryCredentialService:
    def __init__(
        self, store: ProviderConnectionStore, registry: TemporaryCredentialRegistry
    ) -> None:
        self.store = store
        self.registry = registry
        if store.on_change is None:
            store.on_change = registry.revoke
        elif store.on_change != registry.revoke:
            raise CredentialFailure("CONFIGURATION_MISSING")

    async def register(
        self,
        identity: CredentialIdentity,
        connection_id: UUID,
        config_version: int,
        operation_id: UUID,
        purpose: str,
        model_id: str,
        secret: Mapping[str, str],
    ) -> tuple[str, TemporaryBinding]:
        view = await self.store.read(identity, connection_id)
        if view["config_version"] != config_version:
            raise CredentialFailure("VERSION_CONFLICT")
        if view["credential_mode"] != "temporary" or not view["enabled"]:
            raise CredentialFailure("CREDENTIAL_UNAVAILABLE")
        binding = TemporaryBinding(
            identity.user_id,
            identity.session_hash,
            connection_id,
            config_version,
            operation_id,
            purpose,
            model_id,
        )
        handle = await self.registry.register(
            binding,
            secret,
            session_expires_at=datetime.fromisoformat(str(view["credential_expires_at"])),
            validity=lambda: self.store.valid_version(identity, connection_id, config_version),
        )
        return handle, binding
