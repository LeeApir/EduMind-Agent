"""Versioned AES-GCM envelopes; never expose secret material in errors/repr."""

import base64
import json
import re
from dataclasses import dataclass, field
from os import getenv, urandom
from types import MappingProxyType
from typing import Mapping

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialFailure(Exception):
    def __init__(self, code: str = "CREDENTIAL_UNAVAILABLE") -> None:
        self.code = code
        super().__init__("Provider credential is unavailable.")


def encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def decode(value: object, length: int | None = None) -> bytes:
    if not isinstance(value, str):
        raise CredentialFailure()
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError):
        raise CredentialFailure() from None
    if length is not None and len(raw) != length:
        raise CredentialFailure()
    return raw


@dataclass(frozen=True)
class CredentialKeyring:
    active_id: str
    keys: Mapping[str, bytes] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "keys", MappingProxyType(dict(self.keys)))
        if (
            self.active_id not in self.keys
            or not 1 <= len(self.keys) <= 16
            or any(
                not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", k) or len(v) != 32
                for k, v in self.keys.items()
            )
        ):
            raise CredentialFailure("CONFIGURATION_MISSING")

    @classmethod
    def from_environment(cls) -> "CredentialKeyring":
        try:
            values = json.loads(getenv("EDUMIND_CREDENTIAL_KEYRING_JSON", ""))
            if not isinstance(values, dict):
                raise ValueError
            keys = {k: decode(v, 32) for k, v in values.items()}
            return cls(getenv("EDUMIND_CREDENTIAL_ACTIVE_KEY_ID", ""), keys)
        except (ValueError, TypeError, CredentialFailure):
            raise CredentialFailure("CONFIGURATION_MISSING") from None


def _aad(context: bytes, purpose: str) -> bytes:
    return b"edumind-provider-envelope-v1:" + purpose.encode() + b":" + context


def _read(envelope: bytes) -> dict[str, object]:
    try:
        if len(envelope) > 16384:
            raise ValueError
        obj = json.loads(envelope)
        if not isinstance(obj, dict) or set(obj) != {
            "v",
            "alg",
            "kid",
            "nonce",
            "ciphertext",
            "wrap_nonce",
            "wrapped_key",
        }:
            raise ValueError
        if obj["v"] != 1 or isinstance(obj["v"], bool) or obj["alg"] != "AES-256-GCM":
            raise ValueError
        return obj
    except (ValueError, TypeError, UnicodeError):
        raise CredentialFailure() from None


def envelope_key_id(envelope: bytes) -> str:
    key_id = _read(envelope)["kid"]
    if not isinstance(key_id, str):
        raise CredentialFailure()
    return key_id


def serialize_secret(secret: Mapping[str, str]) -> bytes:
    """Strict internal encoding shared by persistent and memory-only credentials."""
    if not secret or set(secret) - {"api_key", "api_secret", "app_id"} or "api_key" not in secret:
        raise CredentialFailure("VALIDATION_ERROR")
    if any(not isinstance(v, str) or not 1 <= len(v) <= 4096 for v in secret.values()):
        raise CredentialFailure("VALIDATION_ERROR")
    raw = json.dumps(dict(secret), separators=(",", ":"), sort_keys=True).encode()
    if len(raw) > 8192:
        raise CredentialFailure("VALIDATION_ERROR")
    return raw


def encrypt_secret(secret: Mapping[str, str], context: bytes, keyring: CredentialKeyring) -> bytes:
    raw = serialize_secret(secret)
    dek = AESGCM.generate_key(bit_length=256)
    nonce, wrap_nonce = urandom(12), urandom(12)
    return json.dumps(
        {
            "v": 1,
            "alg": "AES-256-GCM",
            "kid": keyring.active_id,
            "nonce": encode(nonce),
            "ciphertext": encode(AESGCM(dek).encrypt(nonce, raw, _aad(context, "payload"))),
            "wrap_nonce": encode(wrap_nonce),
            "wrapped_key": encode(
                AESGCM(keyring.keys[keyring.active_id]).encrypt(
                    wrap_nonce, dek, _aad(context, "dek")
                )
            ),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _unwrap(obj: dict[str, object], context: bytes, keyring: CredentialKeyring) -> bytes:
    try:
        kid = obj["kid"]
        if not isinstance(kid, str) or kid not in keyring.keys:
            raise CredentialFailure()
        return AESGCM(keyring.keys[kid]).decrypt(
            decode(obj["wrap_nonce"], 12), decode(obj["wrapped_key"], 48), _aad(context, "dek")
        )
    except (InvalidTag, ValueError):
        raise CredentialFailure() from None


def decrypt_secret(envelope: bytes, context: bytes, keyring: CredentialKeyring) -> dict[str, str]:
    obj = _read(envelope)
    try:
        dek = _unwrap(obj, context, keyring)
        raw = AESGCM(dek).decrypt(
            decode(obj["nonce"], 12), decode(obj["ciphertext"]), _aad(context, "payload")
        )
        secret = json.loads(raw)
        if (
            not isinstance(secret, dict)
            or not secret
            or set(secret) - {"api_key", "api_secret", "app_id"}
        ):
            raise ValueError
        if "api_key" not in secret or any(
            not isinstance(v, str) or not 1 <= len(v) <= 4096 for v in secret.values()
        ):
            raise ValueError
        return secret
    except (InvalidTag, ValueError, TypeError, UnicodeError):
        raise CredentialFailure() from None


def rewrap_secret(envelope: bytes, context: bytes, keyring: CredentialKeyring) -> bytes:
    obj = _read(envelope)
    # Authenticate payload too; do not preserve corrupt envelopes as successfully rotated.
    decrypt_secret(envelope, context, keyring)
    dek = _unwrap(obj, context, keyring)
    nonce = urandom(12)
    obj.update(
        kid=keyring.active_id,
        wrap_nonce=encode(nonce),
        wrapped_key=encode(
            AESGCM(keyring.keys[keyring.active_id]).encrypt(nonce, dek, _aad(context, "dek"))
        ),
    )
    return json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
