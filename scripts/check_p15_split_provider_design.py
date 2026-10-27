"""Offline split-provider design invariants. No keys, transport, execution or authority."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-split-provider-design-r01"


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def route(policy, stage, schema_sha256):
    entry = policy["stages"].get(stage)
    if not entry or entry["schema_sha256"] != schema_sha256:
        raise ValueError("UNKNOWN_STAGE_OR_SCHEMA")
    return dict(policy["providers"][entry["provider"]])


def review_source(*, original_goal, plan_constraints, scene, upstream):
    # Caller supplies only these named arguments, never a whole slot/gold/label object.
    if (
        not isinstance(original_goal, str)
        or not original_goal.strip()
        or not isinstance(scene, dict)
        or not scene
    ):
        raise ValueError("REVIEW_SOURCE_MISSING")
    if not isinstance(plan_constraints, dict) or not isinstance(upstream, list):
        raise ValueError("REVIEW_CONTEXT_INVALID")
    if set(plan_constraints) & {"expected", "gold", "proposed_label", "human_review"}:
        raise ValueError("LABEL_METADATA_FORBIDDEN")
    source = {
        "original_goal": original_goal,
        "plan_constraints": plan_constraints,
        "scene": scene,
        "upstream": upstream,
    }
    return {"source": source, "source_sha256": digest(source)}


def validate_opinion(payload, opinion):
    from jsonschema import Draft202012Validator

    schema = json.loads((BASE / "scene-review.schema.json").read_text())
    Draft202012Validator(schema).validate(opinion)
    if (
        payload["source_sha256"] != digest(payload["source"])
        or opinion["source_sha256"] != payload["source_sha256"]
    ):
        raise ValueError("SNAPSHOT_BINDING_MISMATCH")
    if opinion["scope_status"] != "complete" and (
        opinion["verdict"] != "uncertain" or not opinion["uncertain_reason"]
    ):
        raise ValueError("INSUFFICIENT_EVIDENCE_CANNOT_PASS")
    if (
        opinion["scope_status"] == "complete"
        and opinion["uncertain_reason"] is not None
    ):
        raise ValueError("CONFLICTING_SCOPE_REASON")
    if (
        opinion["verdict"] == "uncertain"
        and opinion["scope_status"] != "insufficient_evidence"
    ):
        raise ValueError("UNCERTAIN_SCOPE_REQUIRED")
    if opinion["verdict"] == "pass" and opinion["issues"]:
        raise ValueError("PASS_WITH_ISSUES")
    if opinion["verdict"] in ("revise", "reject") and not opinion["issues"]:
        raise ValueError("ISSUES_REQUIRED")
    for issue in opinion["issues"]:
        pointer = issue["source_pointer"]
        if pointer != "/original_goal" and not pointer.startswith(
            ("/scene/", "/upstream/", "/plan_constraints/")
        ):
            raise ValueError("EVIDENCE_SCOPE_INVALID")
        current = payload["source"]
        try:
            for token in pointer.split("/")[1:]:
                token = token.replace("~1", "/").replace("~0", "~")
                if isinstance(current, list):
                    if (
                        not token.isascii()
                        or not token.isdecimal()
                        or (len(token) > 1 and token.startswith("0"))
                    ):
                        raise ValueError("INVALID_INDEX")
                    current = current[int(token)]
                else:
                    current = current[token]
        except (KeyError, IndexError, TypeError):
            raise ValueError("EVIDENCE_POINTER_INVALID") from None
        if not isinstance(current, str) or issue["evidence_quote"] not in current:
            raise ValueError("QUOTE_NOT_IN_SOURCE")
    return opinion["verdict"]


def budget(slots):
    courses = [s for s in slots if s["kind"] == "course"]
    negatives = [s for s in slots if s["kind"] == "negative"]
    probes = [s for s in slots if s["kind"] == "probe"]
    if (len(courses), len(negatives), len(probes)) != (12, 2, 20):
        raise ValueError("FIXED_DENOMINATORS_CHANGED")
    scenes = sum(s["scene_count_range"][1] for s in courses)
    generator_requests = (len(courses) + len(negatives)) * 13
    reviewer_requests = scenes + len(probes)
    generation_input = (len(courses) + len(negatives)) * 200000
    generation_output = (len(courses) + len(negatives)) * 48000
    review_input, review_output = reviewer_requests * 32000, reviewer_requests * 8000
    gen_cost = (
        Decimal(generation_input) * Decimal("0.30")
        + Decimal(generation_output) * Decimal("1.20")
    ) / 1000000
    review_cost = (
        Decimal(review_input) * Decimal("2.50")
        + Decimal(review_output) * Decimal("15.00")
    ) / 1000000
    return {
        "scene_reviews": scenes,
        "review_requests": reviewer_requests,
        "generator_requests": generator_requests,
        "http_requests": generator_requests + reviewer_requests,
        "input_tokens": generation_input + review_input,
        "output_tokens": generation_output + review_output,
        "generation_reference_usd": str(gen_cost),
        "review_reference_usd": str(review_cost),
        "total_reference_usd": str(gen_cost + review_cost),
    }


def check():
    manifest = json.loads((BASE / "manifest.json").read_text())
    for name, sha in manifest["sha256"].items():
        path = (ROOT / name).resolve()
        assert (
            path.is_relative_to(ROOT)
            and hashlib.sha256(path.read_bytes()).hexdigest() == sha
        )
    policy = json.loads((BASE / "policy.json").read_text())
    slots = json.loads((BASE / "slots.json").read_text())
    old = json.loads((ROOT / policy["original_slots_source"]).read_text())
    assert slots == old["slots"]
    assert (
        policy["execution_ready"] is False and policy["real_requests_authorized"] == 0
    )
    assert policy["bounded_output_verified"] is False
    assert budget(slots) == policy["budget_calculation"]
    assert budget(slots)["scene_reviews"] == 48
    assert policy["local_hold_usd"] == "20" and Decimal(
        budget(slots)["total_reference_usd"]
    ) < Decimal("20")
    assert sum(
        Decimal(v) for v in policy["local_holds_by_provider_usd"].values()
    ) == Decimal("20")
    assert policy["actual_invoice_hard_cap_usd"] is None
    assert policy["providers"]["generation"]["model"] == "deepseek-flash"
    assert policy["providers"]["review"]["model"] == "gpt-6.1-sol"
    assert {s: v["provider"] for s, v in policy["stages"].items()} == {
        "free_course_plan_generation": "generation",
        "free_scene_generation": "generation",
        "development_scene_review": "review",
        "development_review_probe": "review",
    }
    assert (
        policy["providers"]["generation"]["url"] == "https://api.deepseek.com/responses"
    )
    assert policy["providers"]["review"]["url"] == "https://aiapi.world/v1/responses"
    assert (
        policy["providers"]["generation"]["credential_env"]
        != policy["providers"]["review"]["credential_env"]
    )
    return {
        "design_verified": True,
        "real_requests": 0,
        "execution_ready": False,
        "budget": budget(slots),
    }


if __name__ == "__main__":
    import argparse

    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(check(), ensure_ascii=False))
