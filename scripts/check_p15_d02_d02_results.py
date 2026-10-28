"""Read-only final D02 planning-stop audit. No repair, replay send or source mutation."""

# ruff: noqa: E402
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_p15_d02_recheck_d02 as cli
from acceptance_support.p15_diagnostic_ledger import digest
from app.agents import free_course_planning as planner
from app.services.free_course_snapshots import SnapshotError


def validate_summary(value):
    expected = dict(
        state="stopped",
        reason="threshold_unreachable",
        requests=1,
        generation_requests=1,
        review_requests=0,
        http_200=1,
        complete=1,
        unknown=0,
        reported_input=1966,
        reported_output=665,
        workflow_requests=30,
        workflow_reported_input=138390,
        workflow_reported_output=31075,
        json_schema_valid=True,
        local_planning_validation_passed=False,
        primary_valid=0,
        uncovered_objective_ids=["obj_two_scenes"],
        generated_plans=0,
        generated_scenes=0,
        scene_reviews_unrun=2,
        scene_v5_exercised=False,
        review_protocol_exercised_live=False,
        scene_quality_observed=False,
        standard_assistant_reports=0,
        local_recheck_pass=False,
        T038_completed=False,
        route_reassessment_required=True,
    )
    if any(value.get(k) != v for k, v in expected.items()):
        raise ValueError("EXACT_FINAL_STOP_FACTS_CHANGED")


def check():
    package, grant, plan, slots = cli.gate()
    assert (
        grant["approved"]
        and grant["adr0040_A_C_approved"]
        and grant["final_one_shot_stop_rule_approved"]
    )
    db = sqlite3.connect((cli.OUTPUT / "ledger.sqlite").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")

        def events(kind):
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT body FROM receipts WHERE batch=? AND kind=? ORDER BY seq",
                    (cli.BATCH, kind),
                )
            ]

        batch = db.execute(
            "SELECT package,approval,state,reason FROM batches WHERE id=?", (cli.BATCH,)
        ).fetchone()
        assert (batch["package"], batch["approval"]) == (package, digest(grant))
        assert events("planned_slots") == [dict(slots=slots)]
        calls = events("live_dispatch_reserved")
        attempts = db.execute(
            "SELECT * FROM attempts WHERE batch=?", (cli.BATCH,)
        ).fetchall()
        assert len(calls) == len(attempts) == 1
        call, attempt = calls[0], attempts[0]
        ticket = call["ticket"]
        assert (
            attempt["id"] == ticket and call["stage"] == "free_course_plan_generation"
        )
        assert call["provider"] == "generation"
        assert (
            digest(
                dict(
                    identity=call["identity"],
                    stage=call["stage"],
                    request_sha256=call["request_sha256"],
                )
            )
            == ticket
        )
        request_raw = (cli.OUTPUT / (ticket + "-request.json")).read_bytes()
        response_raw = (cli.OUTPUT / (ticket + "-response.json")).read_bytes()
        assert hashlib.sha256(request_raw).hexdigest() == call["request_sha256"]
        request, response = json.loads(request_raw), json.loads(response_raw)
        assert (
            request["model"]
            == response["model"]
            == plan["providers"]["generation"]["model"]
        )
        assert response["status"] == "completed" and response["store"] is False
        assert request["reasoning"] == dict(effort="none")
        assert (
            json.loads((cli.OUTPUT / (ticket + "-status.json")).read_bytes())[
                "http_status"
            ]
            == 200
        )
        settlements = events("settled_observation")
        assert len(settlements) == 1
        assert (
            settlements[0]["proof_sha256"] == hashlib.sha256(response_raw).hexdigest()
        )
        usage = response["usage"]
        assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
        assert (attempt["input_used"], attempt["output_used"]) == (
            usage["input_tokens"],
            usage["output_tokens"],
        )
        source = json.loads(request["input"][-1]["content"])
        assert source["prompt_version"] == "free-course-plan-v1"
        assert source["original_goal"] == slots[0]["original_goal"]
        value = json.loads(response["output"][0]["content"][0]["text"])
        Draft202012Validator(planner.SCHEMA).validate(value)
        before = digest(value)
        try:
            planner.validate_response(value, source)
        except SnapshotError as exc:
            assert str(exc) == "SCHEMA_INVALID"
        else:
            raise ValueError("ORIGINAL_LOCAL_FAILURE_DISAPPEARED")
        assert digest(value) == before
        ids = {o["id"] for o in value["plan"]["objectives"]}
        coverage = {k for s in value["plan"]["scenes"] for k in s["objective_ids"]}
        missing = sorted(ids - coverage)
        assert len(ids) == 4 and len(coverage) == 3
        assert events("primary_schema") == [
            dict(attempt=events("primary_schema")[0]["attempt"], valid=False)
        ]
        for kind in (
            "slot_output",
            "scene_source_frozen",
            "scene_review_started",
            "scene_review_finished",
            "review_protocol_observation",
            "assistant_review",
        ):
            assert not events(kind)
        pg = json.loads((cli.OUTPUT / "pg-export.json").read_bytes())["tables"]
        assert (
            len(pg["free_course_attempts"]) == len(pg["free_course_settlements"]) == 1
        )
        assert (
            pg["free_course_attempts"][0]["id"]
            == events("primary_schema")[0]["attempt"]
        )
        assert pg["free_course_settlements"][0]["outcome_json"]["value"] == value
        assert not pg["free_course_plans"] and not pg["free_course_scene_versions"]
        # Preserve the scheduler's historical pending repair flag: no actual second dispatch occurred.
        assert pg["free_course_operations"][0]["state"] == "running"
        assert pg["free_course_steps"][0]["retry_purpose"] == "format_repair"
        diagnosis = json.loads(
            (cli.OUTPUT / "planning-failure-diagnosis.json").read_bytes()
        )
        assert diagnosis["uncovered_objective_ids"] == missing
        assert diagnosis["request_sha256"] == call["request_sha256"]
        assert diagnosis["response_sha256"] == hashlib.sha256(response_raw).hexdigest()
        result = dict(
            state=batch["state"],
            reason=batch["reason"],
            requests=len(calls),
            generation_requests=1,
            review_requests=0,
            http_200=1,
            complete=sum(a["state"] == "complete" for a in attempts),
            unknown=sum(a["state"] == "unknown" for a in attempts),
            reported_input=usage["input_tokens"],
            reported_output=usage["output_tokens"],
            workflow_requests=29 + len(calls),
            workflow_reported_input=136424 + usage["input_tokens"],
            workflow_reported_output=30410 + usage["output_tokens"],
            json_schema_valid=True,
            local_planning_validation_passed=False,
            primary_valid=0,
            uncovered_objective_ids=missing,
            generated_plans=0,
            generated_scenes=0,
            scene_reviews_unrun=2,
            scene_v5_exercised=False,
            review_protocol_exercised_live=False,
            scene_quality_observed=False,
            standard_assistant_reports=0,
            local_recheck_pass=False,
            T038_completed=False,
            route_reassessment_required=True,
            actual_fee=None,
        )
        validate_summary(result)
        return result
    finally:
        db.close()


if __name__ == "__main__":
    result = check()
    expected = json.loads((cli.BASE / "results.json").read_bytes())
    if result != expected:
        raise ValueError("SAVED_RESULT_CHANGED")
    manifest = json.loads((cli.BASE / "results-manifest.json").read_bytes())
    for name, sha in manifest["private_sha256"].items():
        if hashlib.sha256((cli.OUTPUT / name).read_bytes()).hexdigest() != sha:
            raise ValueError("PRIVATE_EVIDENCE_CHANGED")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2)
