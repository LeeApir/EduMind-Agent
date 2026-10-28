"""Read-only audit of the stopped formal d03; never sends or repairs responses."""

# ruff: noqa: E402
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_p15_d02_formal_d03 as cli
from acceptance_support.p15_diagnostic_ledger import digest
from app.agents import free_course_planning as planner
from app.agents import free_scene_generation as generator
from app.services.free_course_snapshots import SnapshotError


def schema_findings(value):
    return [
        dict(path=list(e.absolute_path), validator=e.validator, message=e.message)
        for e in Draft202012Validator(generator.SCHEMA).iter_errors(value)
    ]


def check():
    package, grant, plan, slots = cli.gate()
    assert grant["approved"] and grant["planning_v2_patch_scope_approved"]
    assert grant["adr0040_A_B_scope_extension_approved"]
    db = sqlite3.connect((cli.OUTPUT / "ledger.sqlite").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("BEGIN")
        batch = db.execute("SELECT * FROM batches WHERE id=?", (cli.BATCH,)).fetchone()
        assert (batch["package"], batch["approval"]) == (package, digest(grant))
        assert (batch["state"], batch["reason"]) == ("stopped", "threshold_unreachable")

        def events(kind):
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT body FROM receipts WHERE batch=? AND kind=? ORDER BY seq",
                    (cli.BATCH, kind),
                )
            ]

        assert events("planned_slots") == [dict(slots=slots)]
        calls, primary, settled = (
            events(k)
            for k in ("live_dispatch_reserved", "primary_schema", "settled_observation")
        )
        attempts = db.execute(
            "SELECT * FROM attempts WHERE batch=?", (cli.BATCH,)
        ).fetchall()
        assert len(calls) == len(primary) == len(settled) == len(attempts) == 3
        assert all(a["state"] == "complete" for a in attempts)
        assert [v["valid"] for v in primary] == [True, True, False]
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
            len(pg["free_course_attempts"]) == len(pg["free_course_settlements"]) == 3
        )
        assert (
            len(pg["free_course_plans"]) == len(pg["free_course_scene_versions"]) == 1
        )
        assert pg["free_course_operations"][0]["state"] == "running"
        assert (
            sum(
                s.get("retry_purpose") == "format_repair"
                for s in pg["free_course_steps"]
            )
            == 1
        )
        snapshots = {a["id"]: a["input_snapshot"] for a in pg["free_course_attempts"]}
        findings, source_proofs, inputs, outputs = [], [], 0, 0
        for index, (call, observation, verdict) in enumerate(
            zip(calls, settled, primary, strict=True)
        ):
            ticket = call["ticket"]
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
            req_bytes = (cli.OUTPUT / (ticket + "-request.json")).read_bytes()
            res_bytes = (cli.OUTPUT / (ticket + "-response.json")).read_bytes()
            req_sha, res_sha = (
                hashlib.sha256(b).hexdigest() for b in (req_bytes, res_bytes)
            )
            assert req_sha == call["request_sha256"]
            assert res_sha == observation["proof_sha256"]
            req, res = json.loads(req_bytes), json.loads(res_bytes)
            assert (
                req["model"] == res["model"] == plan["providers"]["generation"]["model"]
            )
            assert req["reasoning"] == dict(effort="none")
            assert res["status"] == "completed" and res["store"] is False
            assert (
                json.loads((cli.OUTPUT / (ticket + "-status.json")).read_bytes())[
                    "http_status"
                ]
                == 200
            )
            usage = res["usage"]
            assert (
                usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
            )
            attempt = next(a for a in attempts if a["id"] == ticket)
            assert (attempt["input_used"], attempt["output_used"]) == (
                usage["input_tokens"],
                usage["output_tokens"],
            )
            inputs += usage["input_tokens"]
            outputs += usage["output_tokens"]
            raw = json.loads(res["output"][0]["content"][0]["text"])
            before = digest(raw)
            snapshot = snapshots[verdict["attempt"]]
            packed = json.loads(req["input"][-1]["content"])
            if index == 0:
                assert packed["prompt_version"] == "free-course-plan-v2"
                planner.validate_response(raw, snapshot)
                objectives = {o["id"] for o in raw["plan"]["objectives"]}
                coverage = {
                    o for s in raw["plan"]["scenes"] for o in s["objective_ids"]
                }
                assert len(raw["plan"]["scenes"]) == 2 and objectives == coverage
            else:
                assert packed["prompt_version"] == "free-scene-generation-v5"
                errors = schema_findings(raw)
                if index == 1:
                    assert not errors
                    generator.validate_response(raw, snapshot)
                else:
                    assert errors == [
                        dict(
                            path=[],
                            validator="required",
                            message="'actions' is a required property",
                        )
                    ]
                    assert "actions" in req["text"]["format"]["schema"]["required"]
                    try:
                        generator.validate_response(raw, snapshot)
                    except SnapshotError as exc:
                        assert str(exc) == "SCHEMA_INVALID"
                    else:
                        raise AssertionError("ORIGINAL_FAILURE_DISAPPEARED")
                    findings = errors
            assert digest(raw) == before
            source_proofs.append(dict(request_sha256=req_sha, response_sha256=res_sha))
        assert (inputs, outputs) == (13766, 5136)
        return dict(
            state=batch["state"],
            reason=batch["reason"],
            requests=3,
            generation_requests=3,
            review_requests=0,
            complete=3,
            unknown=0,
            primary_valid=[True, True, False],
            reported_input=inputs,
            reported_output=outputs,
            workflow_requests=33,
            workflow_reported_input=138390 + inputs,
            workflow_reported_output=31075 + outputs,
            generated_plans=1,
            persisted_scene_versions=1,
            raw_scene_responses=2,
            schema_findings=findings,
            source_proofs=source_proofs,
            standard_assistant_reports=0,
            review_protocol_exercised_live=False,
            local_recheck_pass=False,
            T038_completed=False,
            actual_fee=None,
        )
    finally:
        db.close()


if __name__ == "__main__":
    result = check()
    assert result == json.loads((cli.BASE / "results.json").read_bytes())
    manifest = json.loads((cli.BASE / "results-manifest.json").read_bytes())
    for name, sha in manifest["private_sha256"].items():
        assert hashlib.sha256((cli.OUTPUT / name).read_bytes()).hexdigest() == sha
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2)
