"""Read-only stopped r04 audit; never treats counterfactual envelope edits as a pass."""

# ruff: noqa: E402
import hashlib
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from copy import deepcopy

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_p15_full_diagnostic_r04 as cli
from acceptance_support.p15_diagnostic_ledger import digest
from isolated_diagnostics.p15_sol_compatibility_proposal import validate_envelope
from isolated_diagnostics.p15_full_review_r04 import assess


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
    original_sha = digest(response)
    try:
        validate_envelope(request, response, source)
    except ValueError as exc:
        actual = str(exc)
    else:
        raise ValueError("ACTUAL_PROTOCOL_REJECTION_MISSING")
    shadow = deepcopy(response)
    shadow["instructions"] = request["input"][0]["content"]
    try:
        validate_envelope(request, shadow, source)
    except ValueError as exc:
        second = str(exc)
    else:
        raise ValueError("SECOND_PROTOCOL_REJECTION_MISSING")
    reasons = [r for r in response["output"] if r["type"] == "reasoning"]
    if (
        "instructions" in response
        or len(reasons) != 1
        or not isinstance(reasons[0].get("summary"), list)
        or len(reasons[0]["summary"]) != 1
    ):
        raise ValueError("OBSERVED_VARIANT_CHANGED")
    for r in shadow["output"]:
        if r["type"] == "reasoning":
            r["summary"] = []
    result = validate_envelope(request, shadow, source)
    if digest(response) != original_sha:
        raise ValueError("RAW_RESPONSE_MODIFIED")
    return dict(
        actual_rejection=actual,
        additional_counterfactual_rejection=second,
        instructions_field_present=False,
        reasoning_summary_items=1,
        counterfactual_only_verdict=result["verdict"],
        final_json_verdict=final_value(response)["verdict"],
        actual_protocol_pass=False,
        summary_text_disclosed=False,
        reported_input_tokens=response["usage"]["input_tokens"],
        reported_output_tokens_including_reasoning=response["usage"]["output_tokens"],
        reported_reasoning_tokens=response["usage"]["output_tokens_details"][
            "reasoning_tokens"
        ],
    )


def check():
    package, grant, plan, slots = cli.gate()
    if not grant["approved"] or grant["decisions"] != ["A", "B", "C"]:
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

        calls = events("live_dispatch_reserved")
        target = events("scene_source_frozen")[0]
        if (
            len(calls) != 4
            or [r["provider"] for r in calls].count("generation") != 3
            or [r["provider"] for r in calls].count("review") != 1
        ):
            raise ValueError("CALL_COUNTS_CHANGED")
        if (
            events("planned_slots") != [{"slots": slots}]
            or len(events("slot_started")) != 1
            or events("slot_output")
            or events("assistant_review")
            or events("human_review")
            or events("scene_review_finished")
        ):
            raise ValueError("PHASE_PROGRESS_CHANGED")
        pg = json.loads((cli.OUTPUT / "pg-export.json").read_bytes())
        scene = pg["tables"]["free_course_scene_versions"][0]
        actual = target["payload"]["source"]["scene"]
        if (
            not pg["read_only_transaction"]
            or pg["identity"] != target["identity"]
            or scene["id"] != actual["scene_version_id"]
            or scene["content_digest"] != actual["digest"]
            or scene["content_json"] != actual["content"]
            or scene["actions_json"] != actual["actions"]
        ):
            raise ValueError("PG_SOURCE_CHANGED")
        total_in = total_out = trusted_in = trusted_out = 0
        statuses = []
        observation = None
        schema_errors = []
        for call in calls:
            ticket = call["ticket"]
            raw = (cli.OUTPUT / (ticket + "-request.json")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != call["request_sha256"]:
                raise ValueError("REQUEST_CHANGED")
            req = json.loads(raw)
            res = json.loads((cli.OUTPUT / (ticket + "-response.json")).read_bytes())
            status = json.loads((cli.OUTPUT / (ticket + "-status.json")).read_bytes())[
                "http_status"
            ]
            statuses.append(status)
            if (
                not grant["window_start_epoch"]
                <= db.execute(
                    "SELECT wall FROM attempts WHERE id=?", (ticket,)
                ).fetchone()[0]
                < grant["window_deadline_epoch"]
            ):
                raise ValueError("REQUEST_OUTSIDE_WINDOW")
            total_in += res["usage"]["input_tokens"]
            total_out += res["usage"]["output_tokens"]
            schema_errors.append(
                len(
                    list(
                        Draft202012Validator(
                            req["text"]["format"]["schema"]
                        ).iter_errors(final_value(res))
                    )
                )
            )
            if call["provider"] == "review":
                observation = protocol_observation(req, res, target["payload"])
            else:
                trusted_in += res["usage"]["input_tokens"]
                trusted_out += res["usage"]["output_tokens"]
        primary = events("primary_schema")
        blind = json.loads((cli.OUTPUT / "D01-known-blind-review.json").read_bytes())
        if (
            blind["review_type"] != "delegated_assistant"
            or blind["independent_human_truth"] is not False
            or blind["model_opinion_seen_before_review"] is not False
            or blind["formal_quality_pass"] is not False
            or blind["source_sha256"] != target["payload"]["source_sha256"]
        ):
            raise ValueError("BLIND_REVIEW_CHANGED")
        attempts = db.execute("SELECT state FROM attempts").fetchall()
        if sorted(r[0] for r in attempts) != [
            "complete",
            "complete",
            "complete",
            "unknown",
        ]:
            raise ValueError("UNKNOWN_NOT_PRESERVED")
        op_created = datetime.fromisoformat(
            pg["tables"]["free_course_operations"][0]["created_at"]
        )
        timing = {}
        for event in pg["tables"]["free_course_events"]:
            if event["event_type"] in ["first_scene_ready", "done"]:
                timing[event["event_type"]] = (
                    datetime.fromisoformat(event["created_at"]) - op_created
                ).total_seconds()
        result = dict(
            batch_id=cli.BATCH,
            package_sha256=package,
            state=state,
            stop_reason=reason,
            requests=4,
            generation_requests=3,
            review_requests=1,
            http_statuses=statuses,
            reported_all_input_tokens=total_in,
            reported_all_output_tokens=total_out,
            protocol_trusted_input_tokens=trusted_in,
            protocol_trusted_output_tokens=trusted_out,
            unknown_attempts=1,
            prior_requests=10,
            workflow_requests=14,
            workflow_reported_input_tokens=29006 + total_in,
            workflow_reported_output_tokens=11851 + total_out,
            primary_schema_valid=[r["valid"] for r in primary],
            static_schema_errors_by_call=schema_errors,
            source_sha256=target["payload"]["source_sha256"],
            observation=observation,
            generated_scene_ready=1,
            partial_generation_timing_seconds=timing,
            operation_state=pg["tables"]["free_course_operations"][0]["state"],
            first_slot="failed_protocol",
            remaining_unrun=33,
            model_final_json_verdict=observation["final_json_verdict"],
            actual_contract_pass=False,
            actual_fee_micros=None,
            independent_human_truth=False,
            standard_assistant_reviews=0,
            blind_review_saved=True,
            formal_quality_pass=False,
            T038_completed=False,
            assessment=assess(slots, [], [], primary),
        )
        validate_summary(result)
        return result
    finally:
        db.close()


def validate_summary(s):
    if (
        s["state"] != "stopped"
        or s["stop_reason"] != "UNKNOWN_SEND"
        or s["actual_contract_pass"] is not False
        or s["formal_quality_pass"] is not False
        or s["T038_completed"] is not False
        or s["independent_human_truth"] is not False
    ):
        raise ValueError("FALSE_SUCCESS")
    if (
        s["unknown_attempts"] != 1
        or s["actual_fee_micros"] is not None
        or s["remaining_unrun"] != 33
        or s["standard_assistant_reviews"] != 0
    ):
        raise ValueError("FAILED_OR_UNRUN_EVIDENCE_HIDDEN")
    if (
        s["workflow_requests"] != 10 + s["requests"]
        or s["workflow_reported_input_tokens"] != 29006 + s["reported_all_input_tokens"]
        or s["workflow_reported_output_tokens"]
        != 11851 + s["reported_all_output_tokens"]
    ):
        raise ValueError("HISTORY_OR_USAGE_CHANGED")
    if s["http_statuses"] != [200] * 4 or s["primary_schema_valid"] != [True, False]:
        raise ValueError("RESPONSE_OR_FIRST_PASS_CHANGED")


if __name__ == "__main__":
    try:
        print(json.dumps(check(), ensure_ascii=False, indent=2))
        sys.exit(2)
    except (ValueError, KeyError, sqlite3.Error) as exc:
        print(type(exc).__name__ + ": " + str(exc))
        sys.exit(1)
