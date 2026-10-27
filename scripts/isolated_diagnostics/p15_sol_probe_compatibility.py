"""Original probe Schema with explicitly bounded sol low/known-echo compatibility."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator, ValidationError
from app.agents.review_schema import review_output_schema, validate_review

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "docs/acceptance/phase-1.5-sol-compatibility-plan-r01"
SUFFIX = "\n\nYou are a helpful coding assistant."


def schema():
    return dict(review_output_schema())


def validate_envelope(request, response):
    """Proposed narrow compatibility rules, never proof of upstream instruction integrity."""
    if request.get("model") != "gpt-6.1-sol" or request.get("reasoning") != {
        "effort": "low"
    }:
        raise ValueError("PROPOSED_REQUEST_CONFIGURATION_REQUIRED")
    if request.get("stream") is not False or request.get("store") is not False:
        raise ValueError("REQUEST_MODE_CHANGED")
    fmt = request.get("text", {}).get("format", {})
    if fmt.get("strict") is not True or fmt.get("schema") != schema():
        raise ValueError("ACCURATE_V2_SCHEMA_REQUIRED")
    if (
        response.get("object") != "response"
        or response.get("status") != "completed"
        or response.get("model") != "gpt-6.1-sol"
        or response.get("store") is not False
        or response.get("error") is not None
        or response.get("tools") not in (None, [])
    ):
        raise ValueError("RESPONSE_CONTRACT_FAILED")
    systems = [
        m["content"] for m in request.get("input", []) if m.get("role") == "system"
    ]
    if len(systems) != 1 or not isinstance(systems[0], str) or not systems[0]:
        raise ValueError("ONE_EXACT_SYSTEM_REQUIRED")
    echo = response.get("instructions")
    if echo not in (systems[0], systems[0] + SUFFIX):
        raise ValueError("UNRECOGNIZED_INSTRUCTION_ECHO")
    if response.get("reasoning", {}).get("effort") != "low":
        raise ValueError("REASONING_CONFIGURATION_CHANGED")
    usage = response.get("usage", {})
    values = [usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")]
    if not all(type(v) is int and v >= 0 for v in values) or values[2] != sum(
        values[:2]
    ):
        raise ValueError("USAGE_INVALID")
    reasoning = usage.get("output_tokens_details", {}).get("reasoning_tokens")
    if type(reasoning) is not int or not 0 <= reasoning <= values[1]:
        raise ValueError("REASONING_USAGE_INVALID")
    items = response.get("output")
    if not isinstance(items, list) or not 1 <= len(items) <= 2:
        raise ValueError("OUTPUT_ITEMS_INVALID")
    messages = [i for i in items if isinstance(i, dict) and i.get("type") == "message"]
    reasons = [i for i in items if isinstance(i, dict) and i.get("type") == "reasoning"]
    if (
        len(messages) != 1
        or len(messages) + len(reasons) != len(items)
        or len(reasons) > 1
    ):
        raise ValueError("UNREQUESTED_OUTPUT_TYPE")
    if reasons:
        r = reasons[0]
        # Never read, store separately, forward, or execute hidden reasoning. Only check emptiness.
        if (
            items[0] is not r
            or set(r)
            - {"type", "id", "summary", "content", "encrypted_content", "status"}
            or r.get("summary") != []
            or r.get("content") not in (None, [])
            or (
                r.get("encrypted_content") is not None
                and (
                    not isinstance(r["encrypted_content"], str)
                    or len(r["encrypted_content"]) > 262144
                )
            )
            or r.get("status") not in (None, "completed")
        ):
            raise ValueError("NONEMPTY_OR_UNKNOWN_REASONING_ITEM")
    elif reasoning != 0:
        raise ValueError("REASONING_ITEM_MISSING")
    message = messages[0]
    content = message.get("content")
    if (
        message.get("role") != "assistant"
        or message.get("status") != "completed"
        or not isinstance(content, list)
        or len(content) != 1
        or content[0].get("type") != "output_text"
        or not isinstance(content[0].get("text"), str)
    ):
        raise ValueError("ONE_FINAL_JSON_REQUIRED")
    opinion = json.loads(content[0]["text"])
    try:
        Draft202012Validator(schema()).validate(opinion)
    except ValidationError:
        raise ValueError("OPINION_SCHEMA_INVALID") from None
    opinion = validate_review(opinion)
    verdict = opinion["verdict"]
    return {
        "verdict": verdict,
        "opinion": opinion,
        "observed_known_suffix": echo == systems[0] + SUFFIX,
        "reported_reasoning_tokens": reasoning,
        "reported_output_tokens_including_reasoning": values[1],
        "upstream_context_verified": False,
        "production_admission": False,
        "live_execution_authorized": False,
    }
