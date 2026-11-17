"""Read-only r02 observations; HTTP 200 and useful advice cannot manufacture admission."""

# ruff: noqa: E402
import argparse
import hashlib
import json
import sqlite3
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import check_p15_split_provider_design as design
from jsonschema import Draft202012Validator, ValidationError
from run_p15_split_exploration_r02 import BASE, OUTPUT, BATCH, gate


def review_observation(request, response, payload):
    expected = "\n\n".join(
        m["content"] for m in request["input"] if m["role"] == "system"
    )
    actual = response.get("instructions")
    opinion = None
    texts = [
        c.get("text")
        for item in response.get("output", [])
        if item.get("type") == "message"
        for c in item.get("content", [])
        if c.get("type") == "output_text"
    ]
    if len(texts) == 1:
        try:
            opinion = json.loads(texts[0])
        except (TypeError, ValueError):
            pass
    valid_schema = False
    original_valid = False
    counterfactual = False
    if isinstance(opinion, dict):
        schema = json.loads((design.BASE / "scene-review.schema.json").read_text())
        valid_schema = not list(Draft202012Validator(schema).iter_errors(opinion))
        try:
            design.validate_opinion(payload, opinion)
            original_valid = True
        except (ValueError, ValidationError, TypeError):
            pass
        fixed = deepcopy(opinion)
        if (
            isinstance(fixed.get("issues"), list)
            and fixed["issues"]
            and all(
                isinstance(v.get("source_pointer"), str)
                and v["source_pointer"].startswith("/source/")
                for v in fixed["issues"]
            )
        ):
            for issue in fixed["issues"]:
                issue["source_pointer"] = issue["source_pointer"][len("/source") :]
            try:
                design.validate_opinion(payload, fixed)
                counterfactual = True
            except (ValueError, ValidationError, TypeError):
                pass
    usage = response.get("usage", {})
    return {
        "requested_reasoning": request.get("reasoning"),
        "reported_reasoning_effort": response.get("reasoning", {}).get("effort"),
        "reported_reasoning_tokens": usage.get("output_tokens_details", {}).get(
            "reasoning_tokens"
        ),
        "output_item_types": [item.get("type") for item in response.get("output", [])],
        "instructions_identical": actual == expected,
        "expected_instruction_characters": len(expected),
        "reported_instruction_characters": len(actual)
        if isinstance(actual, str)
        else None,
        "extra_instruction_suffix": actual[len(expected) :]
        if isinstance(actual, str) and actual.startswith(expected)
        else None,
        "opinion_static_schema_valid": valid_schema,
        "original_pointer_quote_contract_valid": original_valid,
        "opinion_verdict": opinion.get("verdict")
        if isinstance(opinion, dict)
        else None,
        "opinion_issues": len(opinion.get("issues", []))
        if isinstance(opinion, dict)
        else None,
        "opinion_severities": [i.get("severity") for i in opinion.get("issues", [])]
        if isinstance(opinion, dict)
        else [],
        "source_pointer_wrapper_counterfactual_valid": counterfactual,
        "counterfactual_applied_to_live_evidence": False,
        "actual_upstream_context_independently_verified": False,
    }


def inspect():
    package, *_ = gate()
    index = json.loads((BASE / "evidence-index.json").read_text())
    for name, sha in index["sha256"].items():
        path = Path(name)
        if (
            path.parent != OUTPUT
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise ValueError("PRIVATE_EVIDENCE_CHANGED")
    wal = OUTPUT / "ledger.sqlite-wal"
    if wal.exists() and wal.stat().st_size:
        raise ValueError("NONEMPTY_WAL_REFUSED")
    db = sqlite3.connect(
        (OUTPUT / "ledger.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True
    )
    try:
        state, reason, actual_package, approval = db.execute(
            "SELECT state,reason,package,approval FROM batches WHERE id=?", (BATCH,)
        ).fetchone()
        if actual_package != package or approval != design.digest(
            json.loads((BASE / "user-direction.json").read_bytes())
        ):
            raise ValueError("EXACT_BATCH_AUTHORITY_CHANGED")

        def events(kind):
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT body FROM receipts WHERE batch=? AND kind=? ORDER BY seq",
                    (BATCH, kind),
                )
            ]

        calls = events("live_dispatch_reserved")
        target = events("scene_source_frozen")[0]
        source = target["payload"]["source"]["scene"]
        pg = json.loads((OUTPUT / "pg-export.json").read_bytes())
        scene = pg["tables"]["free_course_scene_versions"][0]
        if (
            scene["content_digest"] != source["digest"]
            or scene["content_json"] != source["content"]
            or scene["actions_json"] != source["actions"]
            or scene["id"] != source["scene_version_id"]
        ):
            raise ValueError("PG_SOURCE_MISMATCH")
        reported_in = reported_out = 0
        observation = None
        statuses = []
        for call in calls:
            ticket = call["ticket"]
            request_raw = (OUTPUT / f"{ticket}-request.json").read_bytes()
            if hashlib.sha256(request_raw).hexdigest() != call["request_sha256"]:
                raise ValueError("REQUEST_CHANGED")
            request = json.loads(request_raw)
            response = json.loads((OUTPUT / f"{ticket}-response.json").read_bytes())
            status = json.loads((OUTPUT / f"{ticket}-status.json").read_bytes())[
                "http_status"
            ]
            statuses.append(status)
            reported_in += response["usage"]["input_tokens"]
            reported_out += response["usage"]["output_tokens"]
            if call["provider"] == "review":
                observation = review_observation(request, response, target["payload"])
        return {
            "batch_id": BATCH,
            "package_sha256": package,
            "durable_state": state,
            "durable_stop_reason": reason,
            "safe_failure_code": events("step_summary")[-1]["safe_failure_code"],
            "model_requests": len(calls),
            "generation_requests": sum(c["provider"] == "generation" for c in calls),
            "review_requests": sum(c["provider"] == "review" for c in calls),
            "http_statuses": statuses,
            "workflow_requests_including_old_r01": 3 + len(calls),
            "reported_input_tokens_all_responses": reported_in,
            "reported_output_tokens_all_responses": reported_out,
            "workflow_reported_input_tokens": 10455 + reported_in,
            "workflow_reported_output_tokens": 5465 + reported_out,
            "unknown_protocol_outcomes": db.execute(
                "SELECT count(*) FROM attempts WHERE batch=? AND state='unknown'",
                (BATCH,),
            ).fetchone()[0],
            "operation_states": [
                r["state"] for r in pg["tables"]["free_course_operations"]
            ],
            "step_states": [r["state"] for r in pg["tables"]["free_course_steps"]],
            "ready_scene_versions": len(pg["tables"]["free_course_scene_versions"]),
            "generated_block_kinds": [b["kind"] for b in source["content"]["blocks"]],
            "first_schema_checks": [v["valid"] for v in events("primary_schema")],
            "scene_review_finished_records": len(events("scene_review_finished")),
            "assistant_review_records": len(events("assistant_review")),
            "human_review_records": len(events("human_review")),
            "source_sha256": target["payload"]["source_sha256"],
            "review_observation": observation,
            "actual_invoice_usd": None,
            "T038_completed": False,
            "course_quality_pass_claimed": False,
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.parse_args()
    result = inspect()
    if result != json.loads((BASE / "results.json").read_bytes()):
        raise ValueError("DERIVED_RESULT_CHANGED")
    print(json.dumps(result, ensure_ascii=False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
