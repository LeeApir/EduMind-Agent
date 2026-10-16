"""Private, bounded schema locations; never persist instances or exception messages."""

import hashlib
import json

from acceptance_support.failure_observation import SCHEMA_KEYWORDS
from acceptance_support.failure_observation import observe_failure as legacy_observe
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from app.services.deepseek_responses import _reject_external_schema_refs, _result
from app.services.provider_protocol import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES, strict_json

# Static names only: a model cannot smuggle text into logs by inventing a field name.
SAFE_FIELDS = frozenset(
    {
        "schema_version",
        "scope",
        "verdict",
        "coverage",
        "checked",
        "unchecked",
        "findings",
        "unresolved",
        "category",
        "severity",
        "anchors",
        "condition_or_counterexample",
        "impact",
        "reason",
        "message",
        "description",
        "evidence",
        "suggestion",
        "recommendation",
        "summary",
        "details",
        "location",
        "confidence",
        "check_id",
        "status",
        "id",
        "field",
        "explanation",
    }
)
SAFE_SCHEMA_TOKENS = (
    SAFE_FIELDS
    | SCHEMA_KEYWORDS
    | frozenset(
        {
            "properties",
            "items",
            "$defs",
            "finding",
            "review_result",
            "anyOf",
            "allOf",
            "oneOf",
            "not",
            "if",
            "then",
            "else",
            "prefixItems",
            "$ref",
        }
    )
)
MAX_PATH = 32
MAX_FIELDS = 16


def _path(parts, allowed):
    parts = list(parts)
    return {
        "segments": [
            p
            if type(p) is str and p in allowed
            else p
            if type(p) is int and 0 <= p <= 100000
            else "<redacted>"
            for p in parts[:MAX_PATH]
        ],
        "truncated": len(parts) > MAX_PATH,
    }


def _fields(names):
    # Stable ordering uses hashes, never emits arbitrary strings even when short/ASCII.
    names = sorted(names, key=lambda name: hashlib.sha256(name.encode()).hexdigest())
    return {
        "fields": [
            {
                "name": name if name in SAFE_FIELDS else "<redacted>",
                "name_sha256": hashlib.sha256(name.encode()).hexdigest(),
            }
            for name in names[:MAX_FIELDS]
        ],
        "count": len(names),
        "truncated": len(names) > MAX_FIELDS,
    }


def schema_location(error, *, audit=None, request_wire=None):
    """Replay the unchanged first schema check in memory from a complete response.

    Diagnostic replay cannot change the adapter outcome or make a failed review valid.
    The caller supplies the exact reserved request bytes, not a replacement schema.
    """
    unavailable = {"version": "safe-schema-location-v1", "status": "NOT_AVAILABLE"}
    try:
        if (
            getattr(error, "output_failure_reason", None) is None
            or error.output_failure_reason.value != "STRUCTURED_SCHEMA_MISMATCH"
        ):
            return {**unavailable, "status": "NOT_SCHEMA_FAILURE"}
        if audit is None or getattr(audit, "capture_complete", False) is not True:
            return {**unavailable, "status": "INCOMPLETE_CAPTURE"}
        if type(request_wire) is not bytes or not 0 < len(request_wire) <= MAX_REQUEST_BYTES:
            return {**unavailable, "status": "REQUEST_UNAVAILABLE"}
        request = strict_json(request_wire)
        schema = request["text"]["format"]["schema"]
        _reject_external_schema_refs(schema)
        Draft202012Validator.check_schema(schema)
        raw = audit.decoded()
        if not 0 < len(raw) <= MAX_RESPONSE_BYTES:
            return {**unavailable, "status": "RESPONSE_UNAVAILABLE"}
        envelope = strict_json(raw)
        if (
            envelope.get("status") != "completed"
            or envelope.get("error")
            or envelope.get("incomplete_details")
        ):
            return {**unavailable, "status": "RESPONSE_NOT_COMPLETED"}
        # Same adapter text selection and json.loads semantics, not a relaxed parser.
        parsed = _result(envelope)
        if parsed.output_text_counts.messages != 1 or parsed.output_text_counts.blocks != 1:
            return {**unavailable, "status": "AMBIGUOUS_TEXT"}
        value = json.loads(parsed.text)
        if not isinstance(value, dict):
            return {**unavailable, "status": "REPLAY_NOT_OBJECT"}
        try:
            Draft202012Validator(schema).validate(value)
        except ValidationError as cause:
            result = {
                "version": "safe-schema-location-v1",
                "status": "LOCATED",
                "request_wire_sha256": hashlib.sha256(request_wire).hexdigest(),
                "schema_sha256": hashlib.sha256(
                    json.dumps(
                        schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    ).encode()
                ).hexdigest(),
                "keyword": cause.validator if cause.validator in SCHEMA_KEYWORDS else "other",
                "instance_path": _path(cause.absolute_path, SAFE_FIELDS),
                "schema_path": _path(cause.absolute_schema_path, SAFE_SCHEMA_TOKENS),
                "first_violation_only": True,
            }
            if (
                cause.validator == "additionalProperties"
                and cause.validator_value is False
                and isinstance(cause.instance, dict)
                and not cause.schema.get("patternProperties")
            ):
                result["unexpected"] = _fields(
                    set(cause.instance) - set(cause.schema.get("properties", {}))
                )
            if cause.validator == "required" and isinstance(cause.instance, dict):
                result["missing"] = _fields(set(cause.validator_value) - set(cause.instance))
            return result
        return {**unavailable, "status": "REPLAY_NO_SCHEMA_ERROR"}
    except Exception:
        # A diagnostic failure must neither replace the original error nor leak its text.
        return {**unavailable, "status": "REPLAY_UNAVAILABLE"}


def observe_failure(error, *, audit=None, usage=None, stage=None, request_wire=None):
    result = legacy_observe(error, audit=audit, usage=usage, stage=stage)
    result["version"] = "safe-failure-observation-v2"
    result["schema_location"] = schema_location(error, audit=audit, request_wire=request_wire)
    return result
