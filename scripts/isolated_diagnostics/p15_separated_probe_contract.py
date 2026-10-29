"""ADR0048 exact inputs and separate postconditions; no Provider I/O or semantic grader."""

import json
from pathlib import Path
from typing import Any

from scripts.isolated_diagnostics import p15_minimal_contract as local
from scripts.isolated_diagnostics.p15_head_insertion_engine import canonical, digest

VERSION = "separated-diagnostic-validation-v1"
ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "docs/acceptance/phase-1.5-separated-protocol-repair-r01"
ORDER = ("P0", "W0", "W1", "W2", "W3", "W4", "R0")
ROLES = dict.fromkeys(ORDER, "generation")
CAPS = dict.fromkeys(ORDER, (8192, 4096))
LIMITS = dict(
    requests=7,
    input_reservation=57344,
    output_reservation=28672,
    fee_cap=None,
    wall_seconds=900,
    per_request_seconds=60,
    dns_seconds=9,
    request_bytes=65536,
    response_bytes=262144,
)


def bodies() -> dict[str, bytes]:
    return {name: (DESIGN / (name + ".request.json")).read_bytes() for name in ORDER}


def pointer_changes(left: Any, right: Any, path: str = "") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        result: list[str] = []
        for key in sorted(set(left) | set(right)):
            p = path + "/" + key.replace("~", "~0").replace("/", "~1")
            result.extend(
                [p]
                if key not in left or key not in right
                else pointer_changes(left[key], right[key], p)
            )
        return result
    if isinstance(left, list):
        if len(left) != len(right):
            return [path]
        return [
            p
            for i, (a, b) in enumerate(zip(left, right))
            for p in pointer_changes(a, b, path + "/" + str(i))
        ]
    return [] if left == right else [path]


def validate_task(
    name: str, value: dict[str, Any], body: dict[str, Any]
) -> dict[str, Any]:
    local.require(name in ORDER, "SAMPLE_ID")
    local.require(
        canonical(body) == canonical(json.loads(bodies()[name])), "REQUEST_BODY_DRIFT"
    )
    local.validate("B_repair", value)
    user = json.loads(body["input"][1]["content"])
    common = dict(
        output_digest=digest(value), repair_success=False, semantic_evaluated=False
    )
    if name != "R0":
        local.require(
            canonical(value) == canonical(user["expected_output"]),
            "SYNTHETIC_FIXTURE_MISMATCH",
        )
        return dict(
            **common,
            task_kind="echo",
            sample_status="exact_echo",
            fixed_echo_verified=True,
            independent_semantic_review_required=False,
            changed_paths=[],
        )
    local.require("expected_output" not in user, "REPAIR_CANNOT_USE_ECHO_TARGET")
    context = json.loads((DESIGN / "repair-context.json").read_bytes())
    local.verify_artifact(context["original_artifact"])
    local.verify_binding(context["binding"])
    local.require(
        user["previous_candidate_digest"]
        == context["original_artifact"]["artifact_digest"],
        "REPAIR_SOURCE_BINDING",
    )
    local.require(
        user["original"] == context["original_artifact"]["raw_output"],
        "REPAIR_ORIGINAL_BINDING",
    )
    for issue in user["issues"]:
        local.require(
            issue["area"] == "difficulty" and issue["severity"] == "minor",
            "REPAIR_ISSUE_SCOPE",
        )
        target = context["binding"]["targets"].get(issue["target_id"])
        local.require(
            target is not None and issue["evidence_quote"] in target["text"],
            "REPAIR_ISSUE_BINDING",
        )
    changed = pointer_changes(user["original"], value)
    local.require(bool(changed), "REPAIR_NO_CHANGE")
    local.require(changed == ["/paragraphs/0/text"], "REPAIR_UNAUTHORIZED_DELTA")
    return dict(
        **common,
        task_kind="repair",
        sample_status="pending_independent_semantic_review",
        fixed_echo_verified=False,
        independent_semantic_review_required=True,
        changed_paths=changed,
        original_digest=digest(user["original"]),
        previous_candidate_digest=user["previous_candidate_digest"],
    )


def policy_requests() -> list[dict[str, Any]]:
    return [
        dict(
            name=name,
            task_kind="repair" if name == "R0" else "echo",
            url="https://api.deepseek.com/responses",
            model="deepseek-flash",
            reasoning="none",
            input_reservation=8192,
            max_output_tokens=4096,
        )
        for name in ORDER
    ]
