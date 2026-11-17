"""ADR0038 isolated, offline response adapter. No transport or execution authorization.

A private validation view reuses the frozen hard validators after checking the newly
approved metadata policy. It is never returned, persisted or called an original echo.
Raw evidence, old batch settlement and production adapters are not modified.
"""

import hashlib
import json
from copy import deepcopy

from isolated_diagnostics import p15_sol_compatibility_proposal as scene
from isolated_diagnostics import p15_sol_probe_compatibility as probe

VERSION = "isolated-review-observability-v1"
BASE = scene.BASE
SUFFIX = scene.SUFFIX
schema = scene.schema


def _observation_view(request, response):
    systems = [
        m.get("content")
        for m in request.get("input", [])
        if isinstance(m, dict) and m.get("role") == "system"
    ]
    if len(systems) != 1 or not isinstance(systems[0], str) or not systems[0]:
        raise ValueError("ONE_EXACT_SYSTEM_REQUIRED")
    echo = response.get("instructions")
    if echo is not None and (
        not isinstance(echo, str) or echo not in (systems[0], systems[0] + SUFFIX)
    ):
        raise ValueError("UNRECOGNIZED_INSTRUCTION_ECHO")
    unavailable = echo is None
    # Check shape and size only; never interpret or emit summary/encrypted text.
    items = response.get("output")
    if not isinstance(items, list):
        raise ValueError("OUTPUT_ITEMS_INVALID")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("UNREQUESTED_OUTPUT_TYPE")
        if item.get("type") != "reasoning":
            continue
        summary = item.get("summary")
        if not isinstance(summary, list) or len(summary) > 1:
            raise ValueError("SUMMARY_METADATA_INVALID")
        if summary and (
            not isinstance(summary[0], dict)
            or set(summary[0]) != {"type", "text"}
            or summary[0]["type"] != "summary_text"
            or not isinstance(summary[0]["text"], str)
            or len(summary[0]["text"]) > 4096
        ):
            raise ValueError("SUMMARY_METADATA_INVALID")
    view = deepcopy(response)
    if unavailable:
        view["instructions"] = systems[0]
    for item in view["output"]:
        if item.get("type") == "reasoning":
            item["summary"] = []
    return view, {
        "compatibility_policy": VERSION,
        "instruction_echo_status": "echo_unavailable"
        if unavailable
        else "recognized_echo",
        "instruction_delivery_verified": False,
        "upstream_context_verified": False,
        "summary_interpreted_or_forwarded": False,
    }


def _validate(request, response, payload, *, is_probe):
    try:
        view, observation = _observation_view(request, response)
        result = (
            probe.validate_envelope(request, view)
            if is_probe
            else scene.validate_envelope(request, view, payload)
        )
    except (TypeError, KeyError, AttributeError, IndexError):
        raise ValueError("RESPONSE_SHAPE_INVALID") from None
    # Return only the frozen validator's final opinion and safe observation flags.
    # Its known-suffix flag was computed on the private view: derive from raw evidence.
    result["observed_known_suffix"] = (
        observation["instruction_echo_status"] != "echo_unavailable"
        and result["observed_known_suffix"]
    )
    return {**result, **observation}


def validate_envelope(request, response, payload):
    """Validate scene opinion/source exactly; compatibility is advisory, never quality pass."""
    return _validate(request, response, payload, is_probe=False)


def validate_probe_envelope(request, response):
    """Keep the original probe Schema and denominator, with the same metadata policy."""
    return _validate(request, response, None, is_probe=True)


class ReviewObservationAdapter:
    """Offline source-bound integration point; cannot construct or send an HTTP request."""

    @staticmethod
    def validate_scene(request, response, payload):
        from isolated_diagnostics.p15_course_sol_bridge import review_request

        expected = review_request("development_scene_review", payload)
        if request.get("input") != expected["input"]:
            raise ValueError("EXACT_V2_REVIEW_REQUEST_REQUIRED")
        result = validate_envelope(request, response, payload)
        # Bind the precise wire dictionary, not a normalized validation view.
        result["request_sha256"] = hashlib.sha256(
            json.dumps(
                request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        return result
