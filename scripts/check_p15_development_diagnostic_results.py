"""T038 read-only exact stopped-batch audit. Never loads settings, credentials or transport."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path(
    "docs/acceptance/phase-1.5-development-diagnostic-results-r02/results.json"
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
    assert approval["human_message"] == "批准该准确包执行 T038"
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
    counter = json.loads(paths["count_response"].read_text())
    assert counter["object"] == "response.input_tokens"
    assert counter["input_tokens"] == report["preflight_input_tokens"] == 635
    response = json.loads(paths["model_response"].read_text())
    assert "model" not in response and "usage" not in response
    error = response["error"]
    assert (
        error["code"] == "invalid_json_schema"
        and error["param"] == "text.format.schema"
    )
    assert "'allOf' is not permitted" in error["message"]
    body = json.loads(paths["request_body"].read_text())
    assert body["model"] == "gpt-6-luna" and body["reasoning"] == {"effort": "none"}
    assert "allOf" in body["text"]["format"]["schema"]
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
        "VERIFIED BLOCKED: 2 real HTTP / 1 generation; invalid_json_schema; no usage proof."
    )
    print(
        "Full unknown reservation retained; 33 slots unrun; no quality admission or retry."
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()
