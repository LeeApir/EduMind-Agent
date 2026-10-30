"""Isolated review representation: full artifact and reference, target IDs map to paths.

No network or credentials. This is a new development version, not an execution grant.
"""

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as c
from scripts.isolated_diagnostics import p15_pilot_wire as wire
from scripts.isolated_diagnostics import p15_teaching_revision as teaching
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest
from scripts.isolated_diagnostics.p15_schema_probe_p02 import (
    final_phase_validation_view,
)

VERSION = "isolated-review-path-v2"
PATH_INSTRUCTION = (
    "Target catalog values are RFC 6901 JSON pointers into artifact. "
    "Follow each pointer to the complete target; for an object, array, number or null, "
    "its evidence text is canonical JSON. Quote the exact target text. "
    "Never infer omitted material: the full artifact and reference are included."
)


@dataclass(frozen=True)
class Policy:
    request_bytes: int = 4 * 1024 * 1024
    response_bytes: int = 65536
    output_tokens: int = 8000
    encrypted_reasoning_chars: int = 8192
    # Local reservation only: byte count + allowance; not an upstream guarantee.
    token_allowance: int = 8192


POLICY = Policy()


def pointer_value(root: Any, pointer: str) -> Any:
    c.require(
        type(pointer) is str and (pointer == "" or pointer.startswith("/")), "POINTER"
    )
    value = root
    if pointer == "":
        return value
    for part in pointer[1:].split("/"):
        c.require("~" not in part.replace("~0", "").replace("~1", ""), "POINTER_ESCAPE")
        token = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            c.require(token.isdecimal() and str(int(token)) == token, "POINTER_INDEX")
            index = int(token)
            c.require(index < len(value), "POINTER_MISSING")
            value = value[index]
        else:
            c.require(type(value) is dict and token in value, "POINTER_MISSING")
            value = value[token]
    return value


def verify_targets(
    artifact: dict[str, Any], binding: dict[str, Any], targets: dict[str, str]
) -> None:
    c.verify_binding(binding)
    c.require(binding["artifact"] == artifact, "TARGET_ARTIFACT")
    rows = binding["targets"]
    c.require(set(targets) == set(rows), "TARGET_COVERAGE")
    for key, path in targets.items():
        row = rows[key]
        c.require(path == row["path"], "TARGET_PATH")
        node = pointer_value(artifact, path)
        text = node if type(node) is str else canonical(node).decode()
        c.require(
            digest(node) == row["value_digest"] and text == row["text"], "TARGET_VALUE"
        )


def review_body(
    artifact: dict[str, Any], catalog: dict[str, Any], policy: Policy = POLICY
) -> tuple[bytes, dict[str, Any]]:
    c.verify_artifact(artifact)
    c.verify_catalog(catalog)
    c.require(
        artifact["identity"]["spec_digest"] == catalog["spec_digest"],
        "REVIEW_SPEC_BINDING",
    )
    arm = artifact["identity"]["arm"]
    c.require(arm in ("B", "C"), "REVIEW_ARM")
    ident = artifact["identity"]
    base = c.identity(
        ident["run_id"],
        ident["slot_id"],
        arm,
        ident["revision"],
        catalog["example"]["spec"],
        ident["parent_digest"],
    )
    expanded = {
        "binding_version",
        "stage",
        "instruction_digest",
        "request_digest",
        "response_digest",
        "receipt_digest",
        "plan_receipt_digest",
        "parent_review_receipt_digest",
    }
    c.require(set(ident) in (set(base), set(base) | expanded), "IDENTITY_FIELDS")
    for name in set(base) - {"prompt_version"}:
        c.require(ident[name] == base[name], "IDENTITY_VALUE")
    c.require(
        ident["prompt_version"] in (base["prompt_version"], teaching.PROMPT_VERSION),
        "IDENTITY_PROMPT",
    )
    if set(ident) != set(base):
        c.require(
            ident["prompt_version"] == teaching.PROMPT_VERSION
            and ident["binding_version"] == "bound-teaching-pilot-v3",
            "IDENTITY_VERSION",
        )
        c.require(
            ident["stage"]
            in (
                {"C_content", "C_repair"} if arm == "C" else {"B_generate", "B_repair"}
            ),
            "IDENTITY_STAGE",
        )
        for name in expanded - {"binding_version", "stage"}:
            value = ident[name]
            optional = name in {"plan_receipt_digest", "parent_review_receipt_digest"}
            c.require(
                (optional and value is None)
                or (
                    type(value) is str
                    and re.fullmatch(r"[0-9a-f]{64}", value) is not None
                ),
                "IDENTITY_DIGEST",
            )
    c.require(
        c.assemble(
            artifact["raw_output"],
            artifact["identity"],
            catalog if arm == "C" else None,
        )
        == artifact,
        "ARTIFACT_RECONSTRUCTION",
    )
    if arm == "C":
        c.require(
            artifact["source"]["example_digest"]
            == catalog["example"]["payload_digest"],
            "REVIEW_EXAMPLE_BINDING",
        )
    from scripts.isolated_diagnostics import p15_review_engineering as old

    payload, binding = old.compact_payload(artifact, catalog)
    targets = {key: row["path"] for key, row in binding["targets"].items()}
    verify_targets(artifact, binding, targets)
    payload["target_catalog"] = targets
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
                content=teaching.instruction("review_" + arm) + "\n" + PATH_INSTRUCTION,
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


def reservation(body: bytes, policy: Policy = POLICY) -> int:
    c.require(
        type(body) is bytes and len(body) <= policy.request_bytes, "REQUEST_BOUND"
    )
    return len(body) + policy.token_allowance


def observe_review(
    body: bytes,
    raw: bytes,
    binding: dict[str, Any],
    reserved: int,
    policy: Policy = POLICY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    c.require(
        len(raw) <= policy.response_bytes and reserved == reservation(body, policy),
        "REVIEW_BOUND",
    )
    request = wire.strict_json(body)
    payload = wire.strict_json(request["input"][1]["content"])
    catalog = c.make_catalog(payload["reference"]["spec"])
    expected, rebuilt = review_body(binding["artifact"], catalog, policy)
    c.require(expected == body and rebuilt == binding, "REVIEW_REQUEST_BINDING")
    original = wire.strict_json(raw)
    fmt = (
        original.get("text", {}).get("format")
        if isinstance(original.get("text"), dict)
        else None
    )
    expected_format = request["text"]["format"]
    c.require(
        isinstance(fmt, dict)
        and fmt.get("schema") == expected_format["schema"]
        and fmt.get("type", "json_schema") == "json_schema"
        and fmt.get("name", expected_format["name"]) == expected_format["name"]
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
    c.validate(
        "review_" + binding["artifact"]["identity"]["arm"], value, binding=binding
    )
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
