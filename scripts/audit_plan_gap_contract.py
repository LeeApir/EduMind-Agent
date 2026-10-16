"""Zero-call audit of the actual frozen wire, not a reconstructed prompt."""

# ruff: noqa: E402
import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from jsonschema import Draft202012Validator
from app.agents.hybrid_resource_review import INSTRUCTION, review_output_schema
from acceptance_support.om_diagnostic import stable, valid_review
from acceptance_support.phase1_budget import sha

BASE = "docs/acceptance/phase-1-plan-gap-contract-audit"
PRIOR = "docs/acceptance/phase-1-review-suite-r01"
SLOT = "plan-only-gap:candidate"


def audit(root=ROOT):
    p = json.loads((root / PRIOR / "proposal.json").read_text())
    data = json.loads((root / PRIOR / "cases.json").read_text())
    assert (
        stable(p) == "d932bb269cd4a9aaa6038d2c50cc6f4b9fa395516784d08bb46f9862921958f3"
    )
    assert stable(data) == p["cases_sha256"]
    c = data[SLOT]
    wire = bytes.fromhex(c["wire_hex"])
    body = json.loads(wire)
    assert sha(wire) == p["slots"][0]["wire_sha256"]
    fmt = body["text"]["format"]
    schema = fmt["schema"]
    Draft202012Validator.check_schema(schema)
    assert body["input"][0] == {"role": "system", "content": INSTRUCTION}
    assert [m["role"] for m in body["input"]] == ["system", "user"]
    assert schema == review_output_schema(
        "unit", anchor_ids=[a["anchor_id"] for a in c["anchors"]]
    )
    assert (
        set(schema["properties"])
        == set(schema["required"])
        == {"schema_version", "scope", "verdict", "findings", "coverage", "unresolved"}
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["unresolved"]["type"] == "array"
    assert schema["properties"]["unresolved"]["items"]["type"] == "string"
    assert (
        set(fmt) == {"type", "name", "schema"}
        and fmt["type"] == "json_schema"
        and fmt["name"] == "edumind_result"
    )
    examples = {
        "pass": valid_review("unit"),
        "needs_human": {
            **valid_review("unit"),
            "verdict": "needs_human",
            "unresolved": ["缺少学生可见循环状态和退出边界的明确教学支持。"],
        },
    }
    for value in examples.values():
        Draft202012Validator(schema).validate(value)
    bad = {}
    bad["unresolved_object"] = {
        **examples["needs_human"],
        "unresolved": [{"reason": "教学支持不足"}],
    }
    bad["unresolved_string"] = {**examples["needs_human"], "unresolved": "教学支持不足"}
    bad["extra_top_explanation"] = {
        **examples["needs_human"],
        "explanation": "额外说明",
    }
    bad["extra_coverage_field"] = deepcopy(examples["needs_human"])
    bad["extra_coverage_field"]["coverage"]["reason"] = "额外说明"
    rejected = {}
    for name, value in bad.items():
        errors = list(Draft202012Validator(schema).iter_errors(value))
        assert errors
        rejected[name] = [
            {"keyword": e.validator, "path": list(e.absolute_path)} for e in errors
        ]
    doc = json.loads(
        (
            root / "docs/acceptance/phase-1-om-redesign/contract-examples.json"
        ).read_text()
    )["review_record"]["result"]
    resource = review_output_schema("resource", anchor_ids=["a1"])
    Draft202012Validator(resource).validate(doc)
    assert type(doc["unresolved"]) is list and all(
        type(t) is str for t in doc["unresolved"]
    )
    user = json.loads(body["input"][1]["content"])
    assert (
        user["review_contract"]["allowed_verdicts"]
        == schema["properties"]["verdict"]["enum"]
    )
    return {
        "version": "plan-gap-wire-contract-audit-v1",
        "provider_requests": 0,
        "prior_proposal_sha256": stable(p),
        "wire_sha256": sha(wire),
        "wire_bytes": len(wire),
        "prompt_sha256": sha(INSTRUCTION.encode()),
        "schema_sha256": stable(schema),
        "clear_contract_conflict_found": False,
        "actual_request_output_examples": {
            "count": 0,
            "note": "No assistant/few-shot review output examples in actual wire; student samples and plan traces are input data, not review output examples.",
        },
        "offline_only_examples": examples,
        "offline_examples_sent_to_provider": False,
        "original_resource_example": "valid at resource scope; different mandatory check IDs, not sent as unit example",
        "negative_schema_checks": rejected,
        "provider_configuration": {
            "endpoint": "https://api.deepseek.com/responses",
            "format_type": fmt["type"],
            "format_keys": list(fmt),
            "strict_present": False,
            "strict_in_provider_response_format_reference": "not documented in inspected DeepSeek Responses text.format reference; tool strict is a separate beta interface, not assumed required here",
            "local_validation": "unchanged Draft202012Validator.validate, extra fields rejected",
            "reasoning": body["reasoning"],
            "output_limit": body["max_output_tokens"],
            "temperature": str(body["temperature"]),
            "timeout_seconds": 60,
        },
        "prompt_review": {
            "unit_allowed_verdicts_match": True,
            "pure_gap_unresolved_matches_schema": True,
            "unresolved_item_type_not_repeated_in_prose": "schema explicitly requires string items; prose does not prescribe objects",
            "findings_only_phrase": "read in context as findings/no repairs, not a requirement to omit mandatory protocol metadata; wording is imprecise but no explicit incompatible field/type example found",
            "extra_top_level_explanation_requested": False,
        },
        "limitations": [
            "No vendor internal constraint enforcement or strict guarantee inferred from docs.",
            "Old additionalProperties field is still unknown; no inference about unresolved or any named field.",
            "No prompt/schema/strict flag changes based on this audit.",
        ],
        "official_sources": [
            "https://api-docs.deepseek.com/api/create-response/",
            "https://api-docs.deepseek.com/guides/responses_api/",
        ],
        "official_terms_checked_on": "2026-10-16",
    }


if __name__ == "__main__":
    result = audit()
    dest = ROOT / BASE
    dest.mkdir(exist_ok=True)
    (dest / "audit.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "clear_contract_conflict_found": result[
                    "clear_contract_conflict_found"
                ],
                "wire_sha256": result["wire_sha256"],
                "provider_requests": 0,
            }
        )
    )
