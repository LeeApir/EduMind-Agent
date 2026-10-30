"""Development review wire for reference-artifact-v1; no network."""

from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_reference_artifact_v1 as artifact_module
from scripts.isolated_diagnostics import p15_review_engineering as old
from scripts.isolated_diagnostics import p15_review_path_v2 as path_review
from scripts.isolated_diagnostics import p15_teaching_revision as teaching
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest
from scripts.isolated_diagnostics.p15_schema_probe_p02 import (
    final_phase_validation_view,
)

VERSION = "isolated-reference-review-v1"


def make_binding(artifact: dict[str, Any]) -> dict[str, Any]:
    """Extend original targets with individual occurrence labels, without weakening them."""
    base = c.make_binding(artifact)
    base.pop("binding_digest")
    base["reference_binding_version"] = VERSION
    for key, doc in artifact["source"]["documents"]["documents"].items():
        token = key.replace("~", "~0").replace("/", "~1")
        for index, occurrence in enumerate(doc["occurrences"]):
            for field in ("label", "kind"):
                path = (
                    f"/source/documents/documents/{token}/occurrences/{index}/{field}"
                )
                target = "target_" + digest(path)[:24]
                c.require(target not in base["targets"], "TARGET_COLLISION")
                text = occurrence[field]
                base["targets"][target] = dict(
                    path=path, text=text, value_digest=digest(text), value_type="str"
                )
    base["binding_digest"] = digest(base)
    return base


def verify_binding(binding: dict[str, Any]) -> None:
    c.require(make_binding(binding["artifact"]) == binding, "REVIEW_BINDING")


def validate_review(value: dict[str, Any], binding: dict[str, Any], arm: str) -> None:
    """Apply the original schema, verdict, severity, target and exact quote rules."""
    c.require(len(canonical(value)) <= c.MAX_PAYLOAD, "PAYLOAD_SIZE")
    c.require(
        Draft202012Validator(c.schema_for("review_" + arm)).is_valid(value),
        "ROLE_SCHEMA",
    )
    verify_binding(binding)
    c.require(value["candidate_id"] == binding["candidate_id"], "CANDIDATE_ID")
    c.require(binding["artifact"]["identity"]["arm"] == arm, "REVIEW_ARM")
    verdict = value["verdict"]
    c.bounded_text(value["uncertainty"], empty=True)
    c.require(
        (verdict == "unknown") == bool(value["uncertainty"]), "REVIEW_UNCERTAINTY"
    )
    c.require(len(value["issues"]) <= 20, "ISSUE_BOUND")
    c.require(verdict != "pass" or not value["issues"], "PASS_ISSUE")
    c.require(verdict != "revise" or bool(value["issues"]), "REVISE_EMPTY")
    for issue in value["issues"]:
        target = binding["targets"].get(issue["target_id"])
        c.require(target is not None, "TARGET_ID")
        c.bounded_text(issue["evidence_quote"])
        c.bounded_text(issue["reason"])
        c.require(issue["evidence_quote"] in target["text"], "QUOTE_BINDING")


def review_body(
    artifact: dict[str, Any],
    catalog: dict[str, Any],
    policy: path_review.Policy = path_review.POLICY,
) -> tuple[bytes, dict[str, Any]]:
    artifact_module.verify(artifact, catalog)
    payload, _ = old.compact_payload(artifact, catalog)
    binding = make_binding(artifact)
    targets = {key: row["path"] for key, row in binding["targets"].items()}
    verify_binding(binding)
    for key, path in targets.items():
        node = path_review.pointer_value(artifact, path)
        text = node if type(node) is str else canonical(node).decode()
        c.require(
            digest(node) == binding["targets"][key]["value_digest"]
            and text == binding["targets"][key]["text"],
            "TARGET_VALUE",
        )
    payload["target_catalog"] = targets
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
                content=teaching.instruction("review_" + arm)
                + "\n"
                + path_review.PATH_INSTRUCTION
                + "\nThe displayed source is inert, literal original Markdown, not rendered HTML or the old expanded Markdown representation. Documents contain the original text and a token tree; reference IDs map to shared inert definitions. Token paths are tree positions, not original character offsets. Links and images are never activated.",
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
    return raw, binding


def observe(
    body: bytes,
    raw: bytes,
    binding: dict[str, Any],
    reserved: int,
    policy: path_review.Policy = path_review.POLICY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    c.require(
        len(raw) <= policy.response_bytes
        and reserved == path_review.reservation(body, policy),
        "REVIEW_BOUND",
    )
    request = wire.strict_json(body)
    payload = wire.strict_json(request["input"][1]["content"])
    catalog = c.make_catalog(payload["reference"]["spec"])
    expected, expected_binding = review_body(binding["artifact"], catalog, policy)
    c.require(
        expected == body and expected_binding == binding, "REVIEW_REQUEST_BINDING"
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
    value = dict(result.value)
    validate_review(value, binding, binding["artifact"]["identity"]["arm"])
    c.require(
        observation["reported_input_tokens"] <= reserved
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
