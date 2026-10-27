"""Read-only r05 stop evidence audit. Never repairs a response or restarts a batch."""

# ruff: noqa: E402
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_p15_full_diagnostic_r05 as cli
from acceptance_support.p15_diagnostic_ledger import digest
from isolated_diagnostics import p15_review_observability as compat
from isolated_diagnostics.p15_full_observation_r05 import audit_records
from isolated_diagnostics.p15_full_review_r05 import assess, course_inventory


def final_value(response):
    return json.loads(
        next(
            c["text"]
            for item in response["output"]
            if item["type"] == "message"
            for c in item["content"]
            if c["type"] == "output_text"
        )
    )


def protocol_observation(request, response, source):
    """Validate original bytes under the approved policy, without adding reasoning items."""
    before = digest(response)
    try:
        compat.ReviewObservationAdapter.validate_scene(request, response, source)
    except ValueError as exc:
        rejection = str(exc)
    else:
        raise ValueError("EXPECTED_PROTOCOL_REJECTION_MISSING")
    if (
        rejection != "REASONING_ITEM_MISSING"
        or any(item["type"] == "reasoning" for item in response["output"])
        or response["usage"]["output_tokens_details"]["reasoning_tokens"] <= 0
    ):
        raise ValueError("OBSERVED_VARIANT_CHANGED")
    opinion = final_value(response)
    Draft202012Validator(compat.schema()).validate(opinion)
    # Final JSON can be source-correct even when the complete response protocol fails.
    compat.scene.original.validate_opinion(source, opinion)
    if digest(response) != before:
        raise ValueError("RAW_RESPONSE_MODIFIED")
    return dict(
        actual_rejection=rejection,
        actual_protocol_pass=False,
        reported_reasoning_tokens=response["usage"]["output_tokens_details"][
            "reasoning_tokens"
        ],
        reported_output_tokens_including_reasoning=response["usage"]["output_tokens"],
        output_types=[i["type"] for i in response["output"]],
        final_json_schema_and_source_valid=True,
        final_json_verdict=opinion["verdict"],
        final_json_issue_count=len(opinion["issues"]),
        counterfactual_edits=False,
    )


def verify_public_manifest(root, manifest):
    for name, sha in manifest["sha256"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("RESULT_PATH_OUTSIDE_ROOT")
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise ValueError("PUBLIC_RESULT_CHANGED")


def validate_summary(s):
    if any(
        s[k] is not False
        for k in (
            "actual_contract_pass",
            "formal_quality_pass",
            "T038_completed",
            "independent_human_truth",
            "all_observed_content_quality_pass",
        )
    ):
        raise ValueError("FALSE_SUCCESS")
    expected = dict(
        state="stopped",
        stop_reason="UNKNOWN_SEND",
        requests=10,
        generation_requests=7,
        review_requests=3,
        unknown_attempts=1,
        prior_requests=14,
        workflow_requests=24,
        remaining_unrun=31,
        standard_assistant_reviews=2,
        slot_outputs=2,
        started_slots=3,
        reported_all_input_tokens=33184,
        reported_all_output_tokens=10317,
        protocol_trusted_input_tokens=29750,
        protocol_trusted_output_tokens=9891,
        workflow_reported_input_tokens=115074,
        workflow_reported_output_tokens=25275,
        failed_slot="D02-known",
        natural_severe_errors_observed=1,
        successful_review_observations=2,
        generated_scene_ready=4,
    )
    if any(s[k] != value for k, value in expected.items()):
        raise ValueError("COUNTS_OR_FAILURE_CHANGED")
    if (
        s["actual_fee_micros"] is not None
        or s["http_statuses"] != [200] * 10
        or s["primary_schema_valid"] != [True] * 7
        or s["static_schema_errors_by_call"] != [0] * 10
        or s["observation"]["actual_rejection"] != "REASONING_ITEM_MISSING"
        or s["observation"]["actual_protocol_pass"] is not False
        or s["standard_assessment"]["development_admitted"] is not False
    ):
        raise ValueError("UNKNOWN_OR_PROTOCOL_FAILURE_HIDDEN")


def check():
    package, grant, _, slots = cli.gate()
    if grant.get("approved") is not True or grant["package_sha256"] != package:
        raise ValueError("EXACT_APPROVAL_REQUIRED")
    index = json.loads((cli.BASE / "evidence-index.json").read_bytes())
    for name, sha in index["sha256"].items():
        path = (cli.OUTPUT / name).resolve()
        if (
            path.parent != cli.OUTPUT.resolve()
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise ValueError("PRIVATE_EVIDENCE_CHANGED")
    wal = cli.OUTPUT / "ledger.sqlite-wal"
    if wal.exists() and wal.stat().st_size:
        raise ValueError("NONEMPTY_WAL_REFUSED")
    db = sqlite3.connect(
        (cli.OUTPUT / "ledger.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True
    )
    try:
        state, reason, pinned, authority = db.execute(
            "SELECT state,reason,package,approval FROM batches WHERE id=?", (cli.BATCH,)
        ).fetchone()
        if pinned != package or authority != digest(grant):
            raise ValueError("BATCH_AUTHORITY_CHANGED")

        def events(kind):
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT body FROM receipts WHERE batch=? AND kind=? ORDER BY seq",
                    (cli.BATCH, kind),
                )
            ]

        if events("planned_slots") != [{"slots": slots}] or events("human_review"):
            raise ValueError("SLOTS_OR_HUMAN_PROVENANCE_CHANGED")
        calls = events("live_dispatch_reserved")
        attempts = db.execute(
            "SELECT state,input_used,output_used FROM attempts"
        ).fetchall()
        if sorted(r[0] for r in attempts) != ["complete"] * 9 + ["unknown"]:
            raise ValueError("UNKNOWN_NOT_PRESERVED")
        statuses, schema_errors, total_in, total_out = [], [], 0, 0
        observation = None
        for call in calls:
            ticket = call["ticket"]
            raw = (cli.OUTPUT / (ticket + "-request.json")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != call["request_sha256"]:
                raise ValueError("REQUEST_CHANGED")
            request = json.loads(raw)
            response = json.loads(
                (cli.OUTPUT / (ticket + "-response.json")).read_bytes()
            )
            statuses.append(
                json.loads((cli.OUTPUT / (ticket + "-status.json")).read_bytes())[
                    "http_status"
                ]
            )
            wall = db.execute(
                "SELECT wall FROM attempts WHERE id=?", (ticket,)
            ).fetchone()[0]
            if not grant["window_start_epoch"] <= wall < grant["window_deadline_epoch"]:
                raise ValueError("REQUEST_OUTSIDE_WINDOW")
            usage = response["usage"]
            if usage["input_tokens"] + usage["output_tokens"] != usage["total_tokens"]:
                raise ValueError("USAGE_INVALID")
            total_in += usage["input_tokens"]
            total_out += usage["output_tokens"]
            schema_errors.append(
                len(
                    list(
                        Draft202012Validator(
                            request["text"]["format"]["schema"]
                        ).iter_errors(final_value(response))
                    )
                )
            )
            if call == calls[-1]:
                source = json.loads(request["input"][-1]["content"])
                observation = protocol_observation(request, response, source)
        settled = [
            (attempt, json.loads(body))
            for attempt, body in db.execute(
                "SELECT attempt,body FROM receipts WHERE batch=? AND kind='settled_observation'",
                (cli.BATCH,),
            )
        ]
        observed = audit_records(
            output=cli.OUTPUT,
            calls=calls,
            settlements=settled,
            observations=events("review_protocol_observation"),
            slots=slots,
        )
        pg = json.loads((cli.OUTPUT / "pg-export.json").read_bytes())
        if not pg["read_only_transaction"] or len(pg["courses"]) != 3:
            raise ValueError("READ_ONLY_PG_EXPORT_REQUIRED")
        targets = events("scene_source_frozen")
        timing, ready = {}, 0
        for course in pg["courses"]:
            tables = course["tables"]
            identity = course["identity"]
            rows = tables["free_course_scene_versions"]
            ready += len(rows)
            if tables["free_course_operations"][0]["state"] != "succeeded":
                raise ValueError("PG_OPERATION_CHANGED")
            created = datetime.fromisoformat(
                tables["free_course_operations"][0]["created_at"]
            )
            timing[identity["slot_id"]] = {
                e["event_type"]: (
                    datetime.fromisoformat(e["created_at"]) - created
                ).total_seconds()
                for e in tables["free_course_events"]
                if e["event_type"] in ("first_scene_ready", "done")
            }
            for target in [t for t in targets if t["identity"] == identity]:
                scene = target["payload"]["source"]["scene"]
                row = next(r for r in rows if r["id"] == scene["scene_version_id"])
                if (
                    row["content_digest"] != scene["digest"]
                    or row["content_json"] != scene["content"]
                    or row["actions_json"] != scene["actions"]
                ):
                    raise ValueError("PG_SOURCE_CHANGED")
        outputs = events("slot_output")
        values = []
        for output in outputs:
            raw = (cli.OUTPUT / (output["slot_id"] + ".json")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != output["sha256"]:
                raise ValueError("OUTPUT_CHANGED")
            values.append({"slot_id": output["slot_id"], **json.loads(raw)})
        reports = events("assistant_review")
        if [r["slot_id"] for r in reports] != ["D01-known", "D01-unknown"]:
            raise ValueError("STANDARD_REVIEW_CHANGED")
        from types import SimpleNamespace

        for slot in ("D01-known", "D01-unknown", "D02-known"):
            blind = json.loads(
                (cli.OUTPUT / (slot + "-blind-review.json")).read_bytes()
            )
            if (
                blind["review_type"] != "delegated_assistant"
                or blind["independent_human_truth"] is not False
                or blind["model_opinion_seen_before_review"] is not False
            ):
                raise ValueError("BLIND_PROVENANCE_CHANGED")
            selected = [
                t for t in targets if t["identity"]["slot_id"] == slot + ":scene-review"
            ]
            copy = {**blind, "items": blind["blind_items"]}
            course_inventory(
                SimpleNamespace(sources=lambda identity: selected), None, copy
            )
            if slot == "D02-known":
                if (
                    blind["natural_severe_errors"] != 1
                    or blind["answer_checks"][0]["verdict"] != "fail"
                    or blind["answer_checks"][0]["safe_for_exact_scoring"] is not False
                ):
                    raise ValueError("OBSERVED_ANSWER_FAILURE_HIDDEN")
        primary = events("primary_schema")
        standard = assess(slots, values, reports, primary)
        if (
            json.loads((cli.OUTPUT / "standard-assessment.json").read_bytes())
            != standard
        ):
            raise ValueError("STANDARD_ASSESSMENT_CHANGED")
        result = dict(
            batch_id=cli.BATCH,
            package_sha256=package,
            state=state,
            stop_reason=reason,
            requests=len(calls),
            generation_requests=sum(c["provider"] == "generation" for c in calls),
            review_requests=sum(c["provider"] == "review" for c in calls),
            http_statuses=statuses,
            reported_all_input_tokens=total_in,
            reported_all_output_tokens=total_out,
            protocol_trusted_input_tokens=sum(r[1] or 0 for r in attempts),
            protocol_trusted_output_tokens=sum(r[2] or 0 for r in attempts),
            unknown_attempts=sum(r[0] == "unknown" for r in attempts),
            prior_requests=14,
            workflow_requests=14 + len(calls),
            workflow_reported_input_tokens=81890 + total_in,
            workflow_reported_output_tokens=14958 + total_out,
            primary_schema_valid=[r["valid"] for r in primary],
            static_schema_errors_by_call=schema_errors,
            observation=observation,
            successful_review_observations=observed,
            generated_scene_ready=ready,
            pg_generation_timing_seconds=timing,
            started_slots=len(events("slot_started")),
            slot_outputs=len(outputs),
            standard_assistant_reviews=len(reports),
            failed_slot="D02-known",
            remaining_unrun=34 - len(events("slot_started")),
            natural_severe_errors_observed=1,
            out_of_band_blind_review_saved=True,
            standard_assessment=standard,
            standard_assessment_scope="Two imported reviews only; excludes stopped-slot blind failure",
            all_observed_content_quality_pass=False,
            actual_contract_pass=False,
            formal_quality_pass=False,
            T038_completed=False,
            actual_fee_micros=None,
            independent_human_truth=False,
            real_calls_after_stop=0,
        )
        validate_summary(result)
        return result
    finally:
        db.close()


if __name__ == "__main__":
    verify_public_manifest(
        ROOT, json.loads((cli.BASE / "results-manifest.json").read_bytes())
    )
    result = check()
    saved = json.loads((cli.BASE / "results.json").read_bytes())
    validate_summary(saved)
    if result != saved:
        raise ValueError("SAVED_RESULT_CHANGED")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2)
