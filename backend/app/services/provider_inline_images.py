"""Bounded memory image inputs and content-bound consent; never reads files/URLs."""

import hashlib
import json
from collections.abc import Mapping

from app.core.credential_crypto import CredentialFailure
from app.services.provider_connection_dispatch import ConnectionOperation
from app.services.provider_gateway import InlineImage, ProviderError, ProviderErrorCode, TextRequest

MAX_IMAGE_BYTES = 512 * 1024
MAX_IMAGES = 4


def image_manifest(request: TextRequest, schema: Mapping[str, object] | None = None) -> str:
    """Fingerprint of the exact prompt/parameters/schema and ordered image bytes.

    Computing this does not grant consent. A future authorized caller must resolve
    the manifest against the human-approved operation before constructing consent.
    """
    if (
        type(request.images) is not tuple
        or not 1 <= len(request.images) <= MAX_IMAGES
        or any(
            not isinstance(image, InlineImage) or type(image.data) is not bytes
            for image in request.images
        )
        or sum(len(image.data) for image in request.images) > MAX_IMAGE_BYTES
    ):
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
    for image in request.images:
        data = image.data
        recognized = (
            image.mime_type == "image/png"
            and data.startswith(b"\x89PNG\r\n\x1a\n")
            or image.mime_type == "image/jpeg"
            and data.startswith(b"\xff\xd8\xff")
            or image.mime_type == "image/webp"
            and len(data) >= 12
            and data[:4] == b"RIFF"
            and data[8:12] == b"WEBP"
        )
        if not recognized:
            raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
    try:
        value = {
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "task_profile": request.task_profile,
            "max_output_tokens": request.max_output_tokens,
            "temperature": request.temperature,
            "schema": dict(schema) if schema is not None else None,
            "images": [
                {"mime": i.mime_type, "sha256": hashlib.sha256(i.data).hexdigest()}
                for i in request.images
            ],
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE) from None


def check_image_consent(
    operation: ConnectionOperation,
    request: TextRequest,
    schema: Mapping[str, object] | None = None,
) -> None:
    dispatch, consent = operation.request, request.image_consent
    route = dispatch.route
    if dispatch.capabilities.vision is not True:
        raise ProviderError(ProviderErrorCode.CAPABILITY_UNAVAILABLE)
    if (
        dispatch.purpose != "generation"
        or "content_for_review" not in route.data_categories
        or consent is None
        or consent.accepted is not True
        or (consent.connection_id, consent.config_version, consent.model_id, consent.operation_id)
        != (route.connection_id, route.config_version, route.model_id, dispatch.operation_id)
        or consent.manifest_sha256 != image_manifest(request, schema)
    ):
        raise CredentialFailure("CONSENT_REQUIRED")
