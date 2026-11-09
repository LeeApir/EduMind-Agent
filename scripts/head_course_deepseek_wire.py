"""Fixed-route response checks for the DeepSeek development batch."""

from datetime import timedelta

from app.services.free_course_snapshots import SnapshotError, canonical
from scripts.isolated_diagnostics import p15_pilot_wire as wire

BATCH = "head-fixed-deepseek-r01"
VERSION = "head-deepseek-responses-v1"
DATABASE = "edumind_catalog_p15_t108_t114"
ENDPOINT = "https://api.deepseek.com/responses"
WINDOW_SECONDS = 1800
IO_TIMEOUT = 90

# Observed optional fields with the only values allowed on this route.
OPTIONAL_DEFAULTS = {
    "background": False,
    "content_filters": None,
    "error": None,
    "incomplete_details": None,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "max_tool_calls": None,
    "moderation": None,
    "parallel_tool_calls": True,
    "previous_response_id": None,
    "prompt_cache_key": None,
    "prompt_cache_retention": None,
    "safety_identifier": None,
    "service_tier": "default",
    "tool_choice": "auto",
    "tools": [],
    "top_logprobs": 0,
    "top_p": 1,
    "truncation": "disabled",
    "user": None,
    "metadata": {},
    "stream": False,
}


def operation_window(op):
    if op.config_snapshot.get("policy_version") != BATCH:
        return {}
    if op.deadline_at - op.created_at != timedelta(seconds=WINDOW_SECONDS):
        raise SnapshotError("HEAD_DIRECT_WINDOW_MISMATCH")
    return {
        "execution_window": {
            "starts_at": op.created_at.isoformat(),
            "expires_at": op.deadline_at.isoformat(),
        }
    }


def observe_generation(request, raw):
    from scripts.head_course_goal import raw_io

    if len(raw) > 2097152:
        raise SnapshotError("HEAD_DIRECT_RESPONSE_SIZE")
    body = wire.strict_json(raw)
    if type(body) is not dict:
        raise SnapshotError("HEAD_DIRECT_ENVELOPE")
    expected = {
        "object": "response",
        "status": "completed",
        "model": "deepseek-flash",
        "store": False,
        "temperature": 0.2,
        "max_output_tokens": request["max_output_tokens"],
    }
    if (
        body.keys()
        - OPTIONAL_DEFAULTS.keys()
        - expected.keys()
        - {
            "id",
            "created_at",
            "completed_at",
            "instructions",
            "reasoning",
            "text",
            "output",
            "usage",
        }
        or type(body.get("max_output_tokens")) is not int
        or any(not matches(body.get(key), value) for key, value in expected.items())
        or any(
            not matches(body[key], value)
            for key, value in OPTIONAL_DEFAULTS.items()
            if key in body
        )
    ):
        raise SnapshotError("HEAD_DIRECT_ENVELOPE")
    if (
        not isinstance(body.get("id"), str)
        or not body["id"]
        or type(body.get("created_at")) is not int
        or body["created_at"] < 0
        or (
            "completed_at" in body
            and (
                type(body["completed_at"]) is not int
                or body["completed_at"] < body["created_at"]
            )
        )
    ):
        raise SnapshotError("HEAD_DIRECT_METADATA")
    reasoning = body.get("reasoning")
    if reasoning not in ({"effort": "none"}, {"effort": "none", "summary": None}):
        raise SnapshotError("HEAD_DIRECT_REASONING")
    if body.get("instructions") not in (None, request["input"][0]["content"]):
        raise SnapshotError("HEAD_DIRECT_INSTRUCTIONS")
    text = body.get("text")
    if (
        type(text) is not dict
        or text.keys() - {"format", "verbosity"}
        or text.get("verbosity") is not None
    ):
        raise SnapshotError("HEAD_DIRECT_SCHEMA_ECHO")
    fmt = text.get("format")
    expected_fmt = request["text"]["format"]
    if type(fmt) is not dict or canonical(fmt) not in (
        canonical(expected_fmt),
        canonical(dict(expected_fmt, description=None)),
    ):
        raise SnapshotError("HEAD_DIRECT_SCHEMA_ECHO")
    usage = body.get("usage")
    if type(usage) is not dict or usage.keys() - {
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "input_tokens_details",
        "output_tokens_details",
    }:
        raise SnapshotError("HEAD_DIRECT_USAGE")
    input_tokens, output_tokens = usage.get("input_tokens"), usage.get("output_tokens")
    cache = usage.get("input_tokens_details", {})
    reasoning_usage = usage.get("output_tokens_details")
    if (
        type(input_tokens) is not int
        or not 0 <= input_tokens <= 139264
        or type(output_tokens) is not int
        or not 0 <= output_tokens <= expected["max_output_tokens"]
        or type(cache) is not dict
        or cache.keys() - {"cached_tokens"}
        or type(cache.get("cached_tokens", 0)) is not int
        or not 0 <= cache.get("cached_tokens", 0) <= input_tokens
        or type(reasoning_usage) is not dict
        or reasoning_usage.keys() != {"reasoning_tokens"}
        or type(reasoning_usage["reasoning_tokens"]) is not int
        or reasoning_usage["reasoning_tokens"] != 0
    ):
        raise SnapshotError("HEAD_DIRECT_USAGE")
    result, observation = raw_io.observe_generation(request, raw)
    return result, {**observation, "direct_response_contract": VERSION}


def matches(value, expected):
    if type(expected) in (int, float):
        return type(value) in (int, float) and value == expected
    return type(value) is type(expected) and value == expected
