"""Experimental alias-compressed review; frozen old wire remains unchanged."""

from copy import deepcopy
from typing import Any

from scripts.isolated_diagnostics import p15_compact_targets_v1 as targets
from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact_module
from scripts.isolated_diagnostics import p15_reference_review_v1 as old_review
from scripts.isolated_diagnostics import p15_review_engineering as old
from scripts.isolated_diagnostics import p15_review_path_v2 as policy_module
from scripts.isolated_diagnostics import p15_teaching_revision as teaching
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical
from scripts.isolated_diagnostics.p15_schema_probe_p02 import (
    final_phase_validation_view,
)

VERSION = "isolated-compact-review-v1"
INSTRUCTION = "Target catalog 'other' maps short IDs to artifact JSON pointers. For each escaped document key in 'occurrences', the nth pair contains the target IDs for that document's nth occurrence label and kind, respectively; locate their values in artifact.source.documents.documents. Use only these short IDs in issues. The displayed content is inert original Markdown, not expanded HTML; links and images are never activated. Occurrence paths are token-tree positions, not source character offsets."


def build(
    artifact: dict[str, Any],
    catalog: dict[str, Any],
    policy: policy_module.Policy = policy_module.POLICY,
) -> tuple[bytes, dict[str, Any], dict[str, Any]]:
    artifact_module.verify(artifact, catalog)
    payload, _ = old.compact_payload(artifact, catalog)
    binding = old_review.make_binding(artifact)
    target_wire, local = targets.project(binding)
    targets.verify(binding, target_wire, local)
    payload["target_catalog"] = target_wire
    arm = artifact["identity"]["arm"]
    route = wire.ROUTES["review"]
    body = dict(
        model=route["model"],
        stream=False,
        store=False,
        reasoning=dict(effort=route["reasoning"]),
        max_output_tokens=policy.output_tokens,
        temperature=0.2,
        input=[
            dict(
                role="system",
                content=teaching.instruction("review_" + arm) + "\n" + INSTRUCTION,
            ),
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
    return raw, binding, local


def observe(
    body: bytes,
    raw: bytes,
    binding: dict[str, Any],
    local: dict[str, Any],
    reserved: int,
    policy: policy_module.Policy = policy_module.POLICY,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    c.require(
        len(raw) <= policy.response_bytes
        and reserved == policy_module.reservation(body, policy),
        "REVIEW_BOUND",
    )
    request = wire.strict_json(body)
    payload = wire.strict_json(request["input"][1]["content"])
    catalog = c.make_catalog(payload["reference"]["spec"])
    expected, expected_binding, expected_local = build(
        binding["artifact"], catalog, policy
    )
    c.require(
        expected == body and binding == expected_binding and local == expected_local,
        "REVIEW_REQUEST_BINDING",
    )
    original = wire.strict_json(raw)
    fmt = (
        original.get("text", {}).get("format")
        if isinstance(original.get("text"), dict)
        else None
    )
    wanted = request["text"]["format"]
    c.require(
        isinstance(fmt, dict)
        and fmt.get("schema") == wanted["schema"]
        and fmt.get("type", "json_schema") == "json_schema"
        and fmt.get("name", wanted["name"]) == wanted["name"]
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
    original_opinion = dict(result.value)
    translated = targets.translate(
        original_opinion, binding, payload["target_catalog"], local
    )
    c.require(
        observation["reported_input_tokens"] <= reserved
        and observation["reported_total_output_tokens"] <= policy.output_tokens,
        "REVIEW_TOKEN_BOUND",
    )
    return (
        original_opinion,
        translated,
        {
            **observation,
            "phase": phase,
            "encrypted_content_quarantined": quarantined,
            "original_preserved": True,
            "semantic_pass": False,
        },
    )
