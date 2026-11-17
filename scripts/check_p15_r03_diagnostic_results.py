"""T038 r03 read-only stopped input-count mismatch audit. No credentials or transport."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path(
    "docs/acceptance/phase-1.5-development-diagnostic-results-r03/results.json"
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def check(root=ROOT, report_path=REPORT):
    report = json.loads((root / report_path).read_text())
    assert report["task_id"] == "PHASE-1.5-T038"
    assert report["verdict"] == "blocked_not_admitted"
    package_path = root / report["package_manifest"]
    assert sha(package_path) == report["package_sha256"]
    package = json.loads(package_path.read_text())
    for name, expected in package["sha256"].items():
        assert sha(root / name) == expected, name
    approval = json.loads((root / report["approval_registry"]).read_text())
    assert approval["scope"] == report["task_id"]
    assert approval["package_sha256"] == report["package_sha256"]
    assert approval["batch_id"] == package["batch_id"] == report["batch_id"]
    assert approval["limits"] == package["limits"]
    assert approval["human_message"] == "批准该准确 r03 包执行 T038"
    assert approval["fee_cap_waiver"] is True
    assert approval["reviewer"] and approval["received_at"] and approval["evidence_ref"]
    assert sha(root / report["approval_registry"]) == report["approval_registry_sha256"]
    paths = {}
    for item in report["raw_evidence"]:
        path = Path(item["path"])
        assert path.is_absolute() and path.is_file()
        assert sha(path) == item["sha256"], item["role"]
        assert item["role"] not in paths
        paths[item["role"]] = path
    # immutable=1 must never silently ignore a later WAL or rollback journal.
    assert not Path(str(paths["ledger_snapshot"]) + "-wal").exists()
    assert not Path(str(paths["ledger_snapshot"]) + "-journal").exists()
    with sqlite3.connect(
        "file:" + str(paths["ledger_snapshot"]) + "?mode=ro&immutable=1", uri=True
    ) as db:
        db.row_factory = sqlite3.Row
        batches = db.execute("SELECT * FROM batches").fetchall()
        assert len(batches) == 1
        batch = batches[0]
        assert batch["id"] == report["batch_id"]
        assert batch["package"] == report["package_sha256"]
        assert batch["approval"] == digest(approval)
        assert json.loads(batch["limits_json"]) == package["limits"]
        assert (batch["state"], batch["reason"]) == (
            "stopped",
            "provider_contract_failure",
        )
        attempts = db.execute("SELECT * FROM attempts").fetchall()
        receipts = db.execute(
            "SELECT kind,attempt,body FROM receipts ORDER BY seq"
        ).fetchall()
    assert len(attempts) == report["http_attempts"] == 2
    model = [a for a in attempts if a["id"].endswith("-model")]
    counts = [a for a in attempts if a["id"].endswith("-count")]
    assert (
        len(model)
        == report["model_requests"]
        == len(counts)
        == report["token_count_requests"]
        == 1
    )
    assert model[0]["state"] == "unknown" and counts[0]["state"] == "complete"
    assert (
        model[0]["input_used"]
        is model[0]["output_used"]
        is model[0]["fee_used"]
        is None
    )
    assert report["model_usage_actual"] is report["actual_relay_fee"] is None
    assert report["unknown_reservation"] == {
        "input_tokens": model[0]["input_max"],
        "output_tokens": model[0]["output_max"],
        "reference_fee_micros_usd_upper": model[0]["fee_max"],
    }
    assert sum(r["kind"] == "sent" for r in receipts) == 2
    assert not any(r["kind"] in ["human_review", "batch_completed"] for r in receipts)
    assert sum(r["kind"] == "slot_started" for r in receipts) == 1
    outputs = [json.loads(r["body"]) for r in receipts if r["kind"] == "slot_output"]
    assert len(outputs) == 1 and outputs[0]["sha256"] == sha(paths["slot_output"])
    planned = [
        json.loads(r["body"])["slots"] for r in receipts if r["kind"] == "planned_slots"
    ]
    assert planned == [package["slots"]]
    slots = report["slots"]
    assert [s["slot_id"] for s in slots] == [s["slot_id"] for s in package["slots"]]
    assert len(slots) == 34 and slots[0]["state"] == "failed_unknown"
    assert all(s["state"] == "unrun" for s in slots[1:])
    assert report["supported_courses"] == {
        "planned": 12,
        "completed": 0,
        "failed_unknown": 1,
        "unrun": 11,
    }
    assert report["negative_controls"] == {"planned": 2, "unrun": 2}
    assert report["review_probes"] == {"planned": 20, "unrun": 20}
    assert report["quality_evaluated"] is False and report["human_quality_reviews"] == 0
    assert (
        report["natural_quality_rates"]
        is report["review_precision"]
        is report["review_recall"]
        is None
    )
    slot = json.loads(paths["slot_output"].read_text())
    assert slot["engineering_pass"] is False and slot["operation_state"] == "failed"
    assert slot["reason"] == "OUTCOME_UNKNOWN"
    assert len(slot["tables"]["free_course_attempts"]) == 1
    assert not slot["tables"]["free_course_settlements"]
    assert not slot["tables"]["free_course_plans"]
    assert not slot["tables"]["free_course_scene_generation_results"]
    counter = json.loads(paths["count_response"].read_text())
    assert counter["object"] == "response.input_tokens"
    assert counter["input_tokens"] == report["preflight_input_tokens"] == 1677
    response = json.loads(paths["model_response"].read_text())
    assert response["model"] == "gpt-6-luna" and response["status"] == "completed"
    assert response["error"] is None
    usage = response["usage"]
    reported = {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "total_tokens": usage["total_tokens"],
    }
    assert (
        reported
        == report["provider_reported_usage"]
        == {"input_tokens": 6507, "output_tokens": 480, "total_tokens": 6987}
    )
    assert counter["input_tokens"] != usage["input_tokens"]
    assert (
        report["candidate_published"] is False
        and report["scene_contents_generated"] == 0
    )
    assert report["mismatch"] == {
        "input_delta": 4830,
        "equality_gate_satisfied": False,
        "reported_within_reserved_caps": True,
    }
    assert (
        usage["input_tokens"] <= model[0]["input_max"]
        and usage["output_tokens"] <= model[0]["output_max"]
    )
    assert (
        report["http_status"] is None
        and report["unadmitted_candidate_returned"] is True
    )
    body = json.loads(paths["request_body"].read_text())
    assert body["model"] == "gpt-6-luna" and body["reasoning"] == {"effort": "none"}
    assert body["text"]["format"]["strict"] is True
    wire_schema = body["text"]["format"]["schema"]
    expected = json.loads(
        (package_path.parent / "free_course_plan_generation.wire.json").read_text()
    )
    assert wire_schema == expected and "allOf" not in wire_schema
    projection = json.loads(paths["projection_audit"].read_text())
    assert projection["version"] == "p15-strict-wire-v1"
    assert projection["stage"] == "free_course_plan_generation"
    assert projection["wire_schema_sha256"] == digest(wire_schema)
    guidance = (
        package_path.parent / "free_course_plan_generation.guidance.txt"
    ).read_text()
    assert body["input"][1] == {"role": "system", "content": guidance}
    assert (
        projection["guidance_sha256"] == hashlib.sha256(guidance.encode()).hexdigest()
    )
    previous = json.loads((root / report["previous_result"]).read_text())
    assert (
        previous["verdict"] == "blocked_not_admitted"
        and previous["batch_id"] == "p15-development-r02"
    )
    assert (
        report["cumulative_http_attempts"]
        == previous["http_attempts"] + report["http_attempts"]
        == 4
    )
    assert (
        report["cumulative_model_requests"]
        == previous["model_requests"] + report["model_requests"]
        == 2
    )
    assert report["cumulative_unknown_reservation"] == {
        "input_tokens": 64000,
        "output_tokens": 16000,
    }
    assert (
        report["production_mode"] == "catalog_only"
        and report["automatic_retry"] is False
    )
    assert report["T039_started"] is False and report["H_accessed"] is False
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    check()
    print(
        "VERIFIED BLOCKED r03: 2 HTTP / 1 generation; input count 1677 != reported 6507."
    )
    print(
        "Full unknown reservation retained; cumulative 4 HTTP / 2 generation; no retry."
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()
