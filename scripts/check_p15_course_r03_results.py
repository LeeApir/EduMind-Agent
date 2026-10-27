"""Read-only r03 evidence check: compatible protocol does not imply course quality pass."""

# ruff: noqa: E402
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
import run_p15_course_recheck_r03 as cli
from acceptance_support.p15_diagnostic_ledger import digest
from isolated_diagnostics.p15_sol_compatibility_proposal import validate_envelope
from app.services.free_scene_validation import clean_markdown

BASE = cli.BASE
OUTPUT = cli.OUTPUT


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


def verify_index(index, output):
    for name, sha in index["sha256"].items():
        path = (output / name).resolve()
        if (
            path.parent != output.resolve()
            or hashlib.sha256(path.read_bytes()).hexdigest() != sha
        ):
            raise ValueError("PRIVATE_EVIDENCE_CHANGED")


def check():
    package, grant, _, _ = cli.gate()
    if (
        not grant["approved"]
        or package != "2ad4e67a437e2f5b34feedc084d712161162e55160679d8d25c403fb22b613f2"
    ):
        raise ValueError("EXACT_APPROVAL_REQUIRED")
    index = json.loads((BASE / "evidence-index.json").read_bytes())
    verify_index(index, OUTPUT)
    wal = OUTPUT / "ledger.sqlite-wal"
    if wal.exists() and wal.stat().st_size:
        raise ValueError("NONEMPTY_WAL_REFUSED")
    db = sqlite3.connect(
        (OUTPUT / "ledger.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True
    )
    db.row_factory = sqlite3.Row
    try:
        batch = db.execute("SELECT * FROM batches WHERE id=?", (cli.BATCH,)).fetchone()
        if batch["package"] != package or batch["approval"] != digest(grant):
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
        if (
            len(calls) != 3
            or [c["provider"] for c in calls].count("generation") != 2
            or [c["provider"] for c in calls].count("review") != 1
        ):
            raise ValueError("CALL_HISTORY_CHANGED")
        target = events("scene_source_frozen")[0]
        payload = target["payload"]
        pg = json.loads((OUTPUT / "pg-export.json").read_bytes())
        scene = pg["tables"]["free_course_scene_versions"][0]
        source = payload["source"]["scene"]
        if (
            pg["identity"] != target["identity"]
            or not pg["read_only_transaction"]
            or scene["id"] != source["scene_version_id"]
            or scene["content_digest"] != source["digest"]
            or scene["content_json"] != source["content"]
            or scene["actions_json"] != source["actions"]
        ):
            raise ValueError("PG_SOURCE_CHANGED")
        raw_scene = None
        observed = None
        input_tokens = output_tokens = 0
        statuses = []
        for c in calls:
            ticket = c["ticket"]
            raw = (OUTPUT / (ticket + "-request.json")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != c["request_sha256"]:
                raise ValueError("REQUEST_CHANGED")
            req = json.loads(raw)
            res = json.loads((OUTPUT / (ticket + "-response.json")).read_bytes())
            status = json.loads((OUTPUT / (ticket + "-status.json")).read_bytes())[
                "http_status"
            ]
            statuses.append(status)
            if status != 200:
                raise ValueError("HTTP_STATUS_CHANGED")
            value = final_value(res)
            Draft202012Validator(req["text"]["format"]["schema"]).validate(value)
            usage = res["usage"]
            if usage["input_tokens"] + usage["output_tokens"] != usage["total_tokens"]:
                raise ValueError("USAGE_INVALID")
            input_tokens += usage["input_tokens"]
            output_tokens += usage["output_tokens"]
            if c["provider"] == "review":
                observed = validate_envelope(req, res, payload)
            elif c["stage"] == "free_scene_generation":
                raw_scene = value
        if raw_scene is None or observed is None:
            raise ValueError("MISSING_EXACT_RESULT")
        before = raw_scene["blocks"][0]["markdown"]
        after = source["content"]["blocks"][0]["markdown"]
        if (
            clean_markdown(before) != after
            or "int scores[6]" not in before
            or "int scores\\[6\\]" not in after
        ):
            raise ValueError("ROOT_CAUSE_NOT_REPRODUCED")
        report = json.loads((OUTPUT / "assistant-course-review.json").read_bytes())
        blind = json.loads((OUTPUT / "blind-assistant-review.json").read_bytes())
        if (
            report["review_type"] != "delegated_assistant"
            or report["independent_human_truth"] is not False
            or report["source_sha256"] != payload["source_sha256"]
            or blind["source_sha256"] != payload["source_sha256"]
            or blind["model_opinion_seen_before_this_report"] is not False
            or report["formal_quality_pass"] is not False
            or report["standard_review_imported"] is not False
            or len(events("delegated_assistant_course_review")) != 1
            or events("human_review")
            or events("assistant_review")
        ):
            raise ValueError("REVIEW_PROVENANCE_CHANGED")
        attempts = db.execute(
            "SELECT state,wall FROM attempts WHERE batch=?", (cli.BATCH,)
        ).fetchall()
        if any(
            r["state"] != "complete"
            or not grant["window_start_epoch"]
            <= r["wall"]
            < grant["window_deadline_epoch"]
            for r in attempts
        ):
            raise ValueError("REQUEST_WINDOW_OR_STATE_CHANGED")
        summary = dict(
            batch_id=cli.BATCH,
            package_sha256=package,
            state=batch["state"],
            stop_reason=batch["reason"],
            requests=3,
            generation_requests=2,
            review_requests=1,
            http_statuses=statuses,
            input_tokens=input_tokens,
            output_tokens_including_reasoning=output_tokens,
            prior_requests=7,
            workflow_requests=10,
            workflow_input_tokens=19355 + input_tokens,
            workflow_output_tokens=8306 + output_tokens,
            protocol_pass=True,
            sol_reported_reasoning_tokens=observed["reported_reasoning_tokens"],
            sol_known_suffix_observed=observed["observed_known_suffix"],
            model_verdict=observed["verdict"],
            source_sha256=payload["source_sha256"],
            root_cause="local_markdown_sanitization_changes_fenced_code",
            delegated_assistant_review_recorded=True,
            legacy_standard_review_imported=False,
            independent_human_truth=False,
            course_quality_pass=False,
            T038_completed=False,
            actual_fee_micros=None,
            unknown_requests=0,
            production_admission=False,
            bounded_output_verified=False,
            raw_generated_code_executed=False,
        )
        validate_summary(summary)
        return summary
    finally:
        db.close()


def validate_summary(s):
    if (
        s["state"] != "stopped"
        or s["stop_reason"] != "threshold_unreachable"
        or s["course_quality_pass"] is not False
        or s["T038_completed"] is not False
        or s["production_admission"] is not False
        or s["independent_human_truth"] is not False
        or s["legacy_standard_review_imported"] is not False
    ):
        raise ValueError("FALSE_SUCCESS_OR_PROVENANCE")
    if (
        s["requests"] != s["generation_requests"] + s["review_requests"]
        or s["workflow_requests"] != 7 + s["requests"]
        or s["actual_fee_micros"] is not None
        or s["workflow_input_tokens"] != 19355 + s["input_tokens"]
        or s["workflow_output_tokens"] != 8306 + s["output_tokens_including_reasoning"]
    ):
        raise ValueError("HISTORY_OR_USAGE_CHANGED")


if __name__ == "__main__":
    try:
        print(json.dumps(check(), ensure_ascii=False, indent=2))
        sys.exit(2)  # Expected content-quality stop, not an execution exception.
    except (ValueError, KeyError, sqlite3.Error) as exc:
        print(type(exc).__name__ + ": " + str(exc))
        sys.exit(1)
