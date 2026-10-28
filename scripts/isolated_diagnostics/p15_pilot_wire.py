"""Proposed T069 wire contract. Pure request/response checks; no HTTP or credentials.

New pilot scope requires exact approval. Production and old batch policies are unchanged.
"""

import json
import re
from copy import deepcopy
from typing import Any, cast

from app.services.provider_gateway import (
    StructuredRequest,
    StructuredResult,
    TokenUsage,
)
from scripts.isolated_diagnostics.p15_agent_pilot import PilotError, check_schema
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

VERSION = "pilot-responses-wire-v1"
SUFFIX = "\n\nYou are a helpful coding assistant."
ROUTES = {
    "generation": dict(
        url="https://api.deepseek.com/responses",
        model="deepseek-flash",
        reasoning="none",
        credential_env="EDUMIND_DEEPSEEK_COMPAT_API_KEY",
    ),
    "review": dict(
        url="https://aiapi.world/v1/responses",
        model="gpt-6.1-sol",
        reasoning="low",
        credential_env="EDUMIND_AIAPI_REVIEW_API_KEY",
    ),
}
STAGES = {
    "pilot_plan",
    "pilot_content",
    "pilot_repair",
    "pilot_baseline",
    "pilot_baseline_repair",
    "pilot_review",
}


def strict_json(raw: bytes | str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        output = {}
        for key, value in items:
            if key in output:
                raise PilotError("DUPLICATE_JSON_KEY")
            output[key] = value
        return output

    def nonfinite(value: str) -> Any:
        raise PilotError("NONFINITE_JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def request_body(request: StructuredRequest, role: str) -> dict[str, Any]:
    if (
        role not in ROUTES
        or request.stage not in STAGES
        or ((request.stage == "pilot_review") != (role == "review"))
    ):
        raise PilotError("WIRE_STAGE")
    if request.prompt.images or request.prompt.image_consent is not None:
        raise PilotError("WIRE_IMAGE_FORBIDDEN")
    if [m.role for m in request.prompt.messages] != ["system", "user"]:
        raise PilotError("WIRE_MESSAGES")
    if request.prompt.max_output_tokens != 8000 or request.prompt.temperature != 0.2:
        raise PilotError("WIRE_PARAMETERS")
    route = ROUTES[role]
    result = dict(
        model=route["model"],
        stream=False,
        store=False,
        reasoning=dict(effort=route["reasoning"]),
        max_output_tokens=8000,
        temperature=0.2,
        input=[dict(role=m.role, content=m.content) for m in request.prompt.messages],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_agent_pilot",
                strict=True,
                schema=deepcopy(dict(request.json_schema)),
            )
        ),
    )
    if len(canonical(result)) > 131072:
        raise PilotError("WIRE_REQUEST_TOO_LARGE")
    return result


def validate(
    body: dict[str, Any], raw: bytes, role: str
) -> tuple[StructuredResult, dict[str, Any]]:
    if len(raw) > 2097152 or role not in ROUTES:
        raise PilotError("WIRE_RESPONSE_SIZE_OR_ROLE")
    p = strict_json(raw)
    route = ROUTES[role]
    if (
        type(p) is not dict
        or p.get("status") != "completed"
        or p.get("model") != route["model"]
        or p.get("error") is not None
        or p.get("incomplete_details") is not None
        or p.get("store") is not False
        or p.get("tools") not in (None, [])
    ):
        raise PilotError("WIRE_ENVELOPE")
    usage = p.get("usage")
    if type(usage) is not dict:
        raise PilotError("WIRE_USAGE")
    counts = cast(
        list[int],
        [usage.get(k) for k in ("input_tokens", "output_tokens", "total_tokens")],
    )
    if (
        any(type(n) is not int or n < 0 for n in counts)
        or counts[0] + counts[1] != counts[2]
    ):
        raise PilotError("WIRE_USAGE")
    if counts[1] > 8000:
        raise PilotError("WIRE_REPORTED_OUTPUT_OVER_REQUEST")
    details = usage.get("output_tokens_details")
    if details is not None and (
        type(details) is not dict
        or type(details.get("reasoning_tokens")) is not int
        or not 0 <= details["reasoning_tokens"] <= counts[1]
    ):
        raise PilotError("WIRE_REASONING_USAGE")
    if role == "generation" and details and details["reasoning_tokens"] != 0:
        raise PilotError("GENERATION_REASONING_NOT_NONE")
    echo = p.get("instructions")
    expected = body["input"][0]["content"]
    if echo is not None and echo not in (
        expected,
        expected + SUFFIX if role == "review" else expected,
    ):
        raise PilotError("WIRE_INSTRUCTIONS")
    reasoning = p.get("reasoning")
    if reasoning is not None and (
        type(reasoning) is not dict or reasoning.get("effort") != route["reasoning"]
    ):
        raise PilotError("WIRE_REASONING_ECHO")
    items = p.get("output")
    if type(items) is not list or not 1 <= len(items) <= 2:
        raise PilotError("WIRE_OUTPUT")
    messages = []
    quarantined = False
    summary_quarantined = False
    reasoning_items = 0
    for item in items:
        if type(item) is not dict:
            raise PilotError("WIRE_OUTPUT")
        if item.get("type") == "reasoning":
            reasoning_items += 1
            if role != "review" or reasoning_items > 1:
                raise PilotError("UNREQUESTED_REASONING_ITEM")
            allowed = {
                "id",
                "type",
                "status",
                "summary",
                "content",
                "encrypted_content",
                "metadata",
                "internal_chat_message_metadata_passthrough",
            }
            if (
                set(item) - allowed
                or item.get("content") not in (None, [])
                or item.get("encrypted_content") not in (None, "")
            ):
                raise PilotError("UNRECOGNIZED_REASONING_CONTENT")
            summary = item.get("summary")
            if (
                type(summary) is not list
                or len(summary) > 1
                or summary
                and (
                    type(summary[0]) is not dict
                    or set(summary[0]) != {"type", "text"}
                    or summary[0]["type"] != "summary_text"
                    or type(summary[0]["text"]) is not str
                    or len(summary[0]["text"]) > 4096
                )
            ):
                raise PilotError("REASONING_SUMMARY")
            summary_quarantined |= bool(summary)
            names = ("metadata", "internal_chat_message_metadata_passthrough")
            if any(k in item for k in names):
                values = [item.get(k) for k in names]
                if (
                    any(
                        type(v) is not dict
                        or set(v) != {"turn_id"}
                        or type(v["turn_id"]) is not str
                        or not re.fullmatch(
                            r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", v["turn_id"]
                        )
                        for v in values
                    )
                    or values[0] != values[1]
                ):
                    raise PilotError("REASONING_METADATA")
                quarantined = True
        elif item.get("type") == "message":
            messages.append(item)
        else:
            raise PilotError("UNREQUESTED_OUTPUT_TYPE")
    if len(messages) != 1:
        raise PilotError("ONE_OUTPUT_MESSAGE")
    message = messages[0]
    if (
        message.get("role") != "assistant"
        or message.get("status") != "completed"
        or set(message) - {"id", "type", "role", "status", "content"}
    ):
        raise PilotError("WIRE_MESSAGE")
    content = message.get("content")
    if (
        type(content) is not list
        or len(content) != 1
        or type(content[0]) is not dict
        or content[0].get("type") != "output_text"
        or type(content[0].get("text")) is not str
        or not content[0]["text"].strip()
        or set(content[0]) - {"type", "text", "annotations", "logprobs"}
        or content[0].get("annotations") not in (None, [])
        or content[0].get("logprobs") not in (None, [])
    ):
        raise PilotError("WIRE_TEXT")
    value = strict_json(content[0]["text"])
    check_schema(value, body["text"]["format"]["schema"])
    return StructuredResult(
        value, route["model"], TokenUsage(counts[0], counts[1])
    ), dict(
        policy=VERSION,
        instruction_echo="unavailable" if echo is None else "recognized",
        known_suffix_observed=echo == expected + SUFFIX,
        instruction_delivery_verified=False,
        upstream_context_verified=False,
        summary_quarantined=summary_quarantined,
        opaque_turn_metadata_quarantined=quarantined,
        opaque_identity_verified=False,
        actual_invoice_verified=False,
        reported_input_tokens=counts[0],
        reported_total_output_tokens=counts[1],
    )
