"""Allowlisted failure diagnostics. Never serialize vendor/error/response text."""

import asyncio
import hashlib

import httpx
from acceptance_support.connection_diagnostics import classify_failure
from acceptance_support.phase1_budget import ERRORS, GateFailure

from app.services.provider_gateway import (
    JsonExtraDataKind,
    JsonSyntaxReason,
    OutputFailureReason,
    ProviderError,
    ProviderErrorCode,
)
from app.services.provider_protocol import strict_json

SCHEMA_KEYWORDS = frozenset(
    {
        "type",
        "required",
        "additionalProperties",
        "const",
        "enum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "uniqueItems",
        "pattern",
        "other",
    }
)
GATE_CODES = frozenset(
    {
        "CANDIDATE_CRITERION_FAILED",
        "INVALID_OUTPUT",
        "USAGE_UNKNOWN",
        "USAGE_BOUND_EXCEEDED",
        "TARGET_CHANGED",
        "FREEZE_CHANGED",
        "SAFETY_FAILURE",
    }
)
STAGES = frozenset(
    {
        "credentials",
        "target_resolution",
        "provider",
        "response_checks",
        "review_assessment",
        "receipt_write",
        "ledger_finish",
    }
)


class CompletionStream(httpx.AsyncByteStream):
    """Set completion only after exhaustion, never on cancellation or aclose."""

    def __init__(self, inner, audit):
        self.inner, self.audit = inner, audit

    async def __aiter__(self):
        async for chunk in self.inner:
            yield chunk
        self.audit.capture_complete = True

    async def aclose(self):
        await self.inner.aclose()


def count(value):
    return value if type(value) is int and 0 <= value <= 10**12 else None


def enum_value(value, enum):
    return value.value if isinstance(value, enum) else None


def member(value, allowed):
    return value if type(value) is str and value in allowed else None


def observe_failure(error, *, audit=None, usage=None, stage=None):
    """Return safe evidence only; absent information stays None, not zero."""
    normalized, category = classify_failure(error)
    local_code = member(error.code, GATE_CODES) if isinstance(error, GateFailure) else None
    if local_code == "CANDIDATE_CRITERION_FAILED":
        normalized, category = "INVALID_OUTPUT", "local_criterion"
    elif local_code in ERRORS:
        normalized, category = local_code, "local_gate"
    if isinstance(error, asyncio.CancelledError):
        normalized, category = "SAFETY_FAILURE", "cancellation"
    provider = error if isinstance(error, ProviderError) else None
    payload = bytes(audit.payload) if audit is not None else b""
    complete = audit is not None and getattr(audit, "capture_complete", False) is True
    decoded, envelope, decode_status = None, {}, "not_complete"
    if complete:
        try:
            decoded = audit.decoded()
            decode_status = "decoded"
        except Exception:
            decode_status = "unavailable"
        if decoded is not None:
            try:
                parsed = strict_json(decoded)
                if type(parsed) is dict:
                    envelope = parsed
            except Exception:
                pass  # Hash/counts retained; never serialize parser text or partial JSON.

    raw_usage = envelope.get("usage")
    raw_usage = raw_usage if type(raw_usage) is dict else {}
    attached = getattr(provider, "usage", None)
    usage_values, usage_sources, invalid_fields = {}, {}, []
    for key in ("input_tokens", "output_tokens"):
        candidates = (
            ("result", getattr(usage, key, None)),
            ("provider_error", getattr(attached, key, None)),
            ("decoded_envelope", raw_usage.get(key)),
        )
        usage_values[key] = usage_sources[key] = None
        for source, value in candidates:
            if value is not None and count(value) is None:
                invalid_fields.append(key)
            if count(value) is not None:
                usage_values[key], usage_sources[key] = count(value), source
                break
    texts = getattr(provider, "output_text_counts", None)
    sent = getattr(audit, "sent", None)
    dispatch_count = count(sent) if audit is not None else (0 if stage == "credentials" else None)
    status = getattr(audit, "status", None)
    http_status = status if type(status) is int and 100 <= status <= 599 else None
    response_status = envelope.get("status")
    incomplete = envelope.get("incomplete_details")
    incomplete = incomplete.get("reason") if type(incomplete) is dict else None
    return {
        "version": "safe-failure-observation-v1",
        "normalized_error": normalized,
        "error_category": category,
        "stage": member(stage, STAGES),
        "local_gate_code": local_code,
        "provider_error_code": enum_value(getattr(provider, "code", None), ProviderErrorCode),
        "output_failure_reason": enum_value(
            getattr(provider, "output_failure_reason", None), OutputFailureReason
        ),
        "schema_keyword": member(getattr(provider, "schema_keyword", None), SCHEMA_KEYWORDS),
        "json_syntax_reason": enum_value(
            getattr(provider, "json_syntax_reason", None), JsonSyntaxReason
        ),
        "json_extra_data_kind": enum_value(
            getattr(provider, "json_extra_data_kind", None), JsonExtraDataKind
        ),
        "transport_dispatch_count": dispatch_count,
        "dispatch_is_server_receipt_proof": False,
        "http_status": http_status,
        "captured_wire_bytes": len(payload) if audit is not None else None,
        "captured_wire_sha256": hashlib.sha256(payload).hexdigest() if payload else None,
        "response_capture_complete": complete,
        "decode_status": decode_status,
        "decoded_response_sha256": hashlib.sha256(decoded).hexdigest()
        if decoded is not None
        else None,
        "response_status": member(
            response_status, {"completed", "incomplete", "failed", "in_progress"}
        ),
        "incomplete_reason": member(incomplete, {"max_output_tokens", "content_filter"}),
        "input_tokens": usage_values["input_tokens"],
        "output_tokens_including_reasoning": usage_values["output_tokens"],
        "usage_sources": usage_sources,
        "invalid_usage_fields": sorted(set(invalid_fields)),
        "assistant_message_count": count(getattr(texts, "messages", None)),
        "output_text_block_count": count(getattr(texts, "blocks", None)),
    }
