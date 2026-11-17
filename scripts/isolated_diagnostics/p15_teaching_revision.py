"""One bounded teaching revision for the isolated head-insertion pilot.

No network, credentials, model calls, production routing, or changes to frozen v2.
"""

from copy import deepcopy
from typing import Any

from app.services.provider_gateway import (
    ChatMessage,
    StructuredRequest,
    TaskProfile,
    TextRequest,
)
from scripts.isolated_diagnostics import p15_clean_pilot_prompts as previous
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_review_engineering as review
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics.p15_schema_probe_p02 import (
    final_phase_validation_view,
)
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical

PROMPT_VERSION = "minimal-pilot-teaching-v3"
RULE_VERSION = "head-insertion-teaching-rules-v1"
RULES = """\
Teaching rules for this isolated experiment:
1. Write all learner-facing explanation, question stems and explanations in Simplified Chinese.
Keep C code, exact schema keys, enum tokens, identifiers, IDs and evidence quotes unchanged.
When an answer uses fixed enum tokens, state the accepted tokens and their Chinese meanings in the question; do not invent answer normalization.
2. State the traversal classification and the scope of the observation. If observed next pointers
reach NULL without unknown or repetition, the observed values are the complete traversal for that
specified example. If traversal cycles or reaches an indeterminate pointer, report only the known
prefix and the appropriate classification; never assert a finite exact complete output.
3. Explain exactly which variant, inputs, allocation assumptions and executed trace are shown.
Do not claim the example or its actions demonstrate a branch or step absent from the actual example or candidate trace.
Trace node IDs such as i0 and t0 are labels, not declarations of additional C variables. A local
pointer after a call returns is a snapshot from the function, not a variable still in scope.
4. Explain ownership and resource lifetime accurately within the shown example: successful malloc
allocations need eventual safe release when no longer needed; do not free stack nodes, unallocated or
unknown pointers, or present unsafe cleanup for cycles or indeterminate links. The allocation mask is
an abstract test assumption, not a guarantee that a real malloc call succeeds. If cleanup is not shown
in the code or trace, say it is not demonstrated; do not assert that cleanup has occurred.
"""


def instruction(stage: str) -> str:
    c.require(stage in c.STAGES, "STAGE")
    key = "review" if stage.startswith("review_") else stage
    return previous.INSTRUCTIONS[key] + "\n" + RULES


def request_for(stage: str, payload: dict[str, Any]) -> StructuredRequest:
    return StructuredRequest(
        TextRequest(
            (
                ChatMessage("system", instruction(stage)),
                ChatMessage("user", canonical(payload).decode()),
            ),
            TaskProfile.QUALITY,
            8000,
            0.2,
        ),
        c.schema_for(stage),
        stage="minimal_" + stage,
    )


def review_body(
    artifact: dict[str, Any], catalog: dict[str, Any]
) -> tuple[bytes, dict[str, Any]]:
    """Use the existing compact full-artifact review and its one budget policy."""
    c.verify_artifact(artifact)
    c.verify_catalog(catalog)
    c.require(
        artifact["identity"]["spec_digest"] == catalog["spec_digest"],
        "REVIEW_SPEC_BINDING",
    )
    if artifact["identity"]["arm"] == "C":
        c.require(
            artifact["source"]["example_digest"]
            == catalog["example"]["payload_digest"],
            "REVIEW_EXAMPLE_BINDING",
        )
    payload, binding = review.compact_payload(artifact, catalog)
    arm = artifact["identity"]["arm"]
    c.require(arm in ("B", "C"), "REVIEW_ARM")
    route = wire.ROUTES["review"]
    policy = review.POLICY
    body = dict(
        model=route["model"],
        stream=False,
        store=False,
        reasoning=dict(effort=route["reasoning"]),
        max_output_tokens=policy.output_tokens,
        temperature=0.2,
        input=[
            dict(role="system", content=instruction("review_" + arm)),
            dict(role="user", content=canonical(payload).decode()),
        ],
        text=dict(
            format=dict(
                type="json_schema",
                name="edumind_agent_pilot",
                strict=True,
                schema=deepcopy(c.schema_for("review_" + arm)),
            )
        ),
    )
    raw = canonical(body)
    c.require(len(raw) <= policy.request_bytes, "REVIEW_REQUEST_SIZE")
    return raw, binding


def observe_review(
    body: bytes,
    raw: bytes,
    binding: dict[str, Any],
    policy: review.ReviewPolicy = review.POLICY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    c.require(
        len(body) <= policy.request_bytes and len(raw) <= policy.response_bytes,
        "REVIEW_BYTE_BOUND",
    )
    request = wire.strict_json(body)
    c.verify_binding(binding)
    given = wire.strict_json(request["input"][1]["content"])
    catalog = c.make_catalog(given["reference"]["spec"])
    rebuilt_body, rebuilt_binding = review_body(binding["artifact"], catalog)
    c.require(
        rebuilt_body == body and rebuilt_binding == binding, "REVIEW_REQUEST_BINDING"
    )
    c.require(
        request.get("max_output_tokens") == policy.output_tokens,
        "OUTPUT_RESERVATION_MISMATCH",
    )
    original = wire.strict_json(raw)
    fmt = (
        original.get("text", {}).get("format")
        if isinstance(original.get("text"), dict)
        else None
    )
    expected = request["text"]["format"]
    c.require(
        isinstance(fmt, dict)
        and fmt.get("schema") == expected["schema"]
        and fmt.get("type", "json_schema") == "json_schema"
        and fmt.get("name", expected["name"]) == expected["name"]
        and fmt.get("strict", True) is True,
        "SCHEMA_ECHO",
    )
    normalized, phase = final_phase_validation_view(raw)
    view = wire.strict_json(normalized)
    quarantined = False
    for item in view.get("output", []):
        if (
            isinstance(item, dict)
            and item.get("type") == "reasoning"
            and item.get("encrypted_content") not in (None, "")
        ):
            value = item["encrypted_content"]
            c.require(
                type(value) is str
                and 1 <= len(value) <= policy.encrypted_reasoning_chars,
                "ENCRYPTED_REASONING_BOUND",
            )
            item["encrypted_content"] = None
            quarantined = True
    result, observation = wire.validate(request, canonical(view), "review")
    value = dict(result.value)
    arm = binding["artifact"]["identity"]["arm"]
    c.require(arm in ("B", "C"), "REVIEW_ARM")
    c.validate("review_" + arm, value, binding=binding)
    c.require(
        observation["reported_input_tokens"] <= policy.input_tokens
        and observation["reported_total_output_tokens"] <= policy.output_tokens,
        "REVIEW_TOKEN_BOUND",
    )
    return value, {
        **observation,
        "phase": phase,
        "encrypted_content_quarantined": quarantined,
        "original_preserved": True,
        "semantic_pass": False,
    }
