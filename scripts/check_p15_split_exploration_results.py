"""Read-only results: durable terminal state takes precedence over legacy CLI text."""

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
from app.agents import free_scene_generation as scene
from app.services.free_scene_validation import check_scene
from jsonschema import Draft202012Validator
from run_p15_split_exploration import BASE, OUTPUT, BATCH, gate


def inspect_slot(value):
    settlements = {
        v["attempt_id"]: v for v in value["tables"]["free_course_settlements"]
    }
    findings = []
    for attempt in sorted(
        value["tables"]["free_course_attempts"], key=lambda v: v["sent_at"]
    ):
        if attempt["request_json"]["request"]["stage"] != "free_scene_generation":
            continue
        raw = settlements[attempt["id"]]["outcome_json"]["value"]
        inputs = attempt["input_snapshot"]
        target = next(
            s for s in inputs["plan"]["scenes"] if s["scene_id"] == inputs["scene_id"]
        )
        allowed = set(target["forms"]) | {"text"}
        actual = {b["kind"] for b in raw["blocks"]}
        stripped = deepcopy(raw)
        anchors = {
            b["anchor_id"] for b in stripped["blocks"] if b["kind"] not in allowed
        }
        stripped["blocks"] = [b for b in stripped["blocks"] if b["kind"] in allowed]
        stripped["actions"] = [
            a for a in stripped["actions"] if a["anchor_id"] not in anchors
        ]
        try:
            scene.validate_response(stripped, inputs)
            counterfactual_pass = check_scene(stripped, inputs)["state"] == "accepted"
        except ValueError:
            counterfactual_pass = False
        findings.append(
            {
                "attempt_id": attempt["id"],
                "purpose": attempt["purpose"],
                "json_schema_errors": len(
                    list(Draft202012Validator(scene.SCHEMA).iter_errors(raw))
                ),
                "planned_forms": target["forms"],
                "actual_forms": sorted(actual),
                "extra_forms": sorted(actual - allowed),
                "counterfactual_remove_extra_blocks_admitted": counterfactual_pass,
                "counterfactual_applied_to_course": False,
            }
        )
    return {
        "engineering_pass": value["engineering_pass"],
        "operation_state": value["operation_state"],
        "scene_attempts": findings,
    }


def inspect(output=OUTPUT):
    package, *_ = gate()
    output = Path(output)
    wal = output / "ledger.sqlite-wal"
    if wal.exists() and wal.stat().st_size:
        raise ValueError("UNSETTLED_WAL_REQUIRES_EXPLICIT_READONLY_SNAPSHOT")
    db = sqlite3.connect(
        (output / "ledger.sqlite").as_uri() + "?mode=ro&immutable=1", uri=True
    )
    try:
        row = db.execute(
            "SELECT state,reason,package FROM batches WHERE id=?", (BATCH,)
        ).fetchone()
        if row is None or row[2] != package:
            raise ValueError("BATCH_PACKAGE_MISMATCH")

        def events(kind):
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT body FROM receipts WHERE kind=? AND batch=? ORDER BY seq",
                    (kind, BATCH),
                )
            ]

        dispatch = events("live_dispatch_reserved")
        usage = events("unbounded_usage_observed")
        proofs = {v["proof_sha256"] for v in events("settled_observation")}
        slots = []
        for record in events("slot_output"):
            path = output / (record["slot_id"] + ".json")
            if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
                raise ValueError("OUTPUT_CHANGED")
            slots.append(
                {
                    "slot_id": record["slot_id"],
                    "output_sha256": record["sha256"],
                    **inspect_slot(json.loads(path.read_bytes())),
                }
            )
        for c in dispatch:
            ticket = c["ticket"]
            path = output / f"{ticket}-request.json"
            if hashlib.sha256(path.read_bytes()).hexdigest() != c["request_sha256"]:
                raise ValueError("REQUEST_CHANGED")
            response = (output / f"{ticket}-response.json").read_bytes()
            if hashlib.sha256(response).hexdigest() not in proofs:
                raise ValueError("RESPONSE_CHANGED")
            payload = json.loads(response)
            status = json.loads((output / f"{ticket}-status.json").read_bytes())
            observed = [v for v in usage if v["ticket"] == ticket]
            if (
                status != {"http_status": 200}
                or len(observed) != 1
                or observed[0]["input_tokens"] != payload["usage"]["input_tokens"]
                or observed[0]["output_tokens"] != payload["usage"]["output_tokens"]
            ):
                raise ValueError("RESPONSE_USAGE_OR_STATUS_CHANGED")
        return {
            "batch_id": BATCH,
            "package_sha256": package,
            "durable_state": row[0],
            "durable_stop_reason": row[1],
            "model_calls": len(dispatch),
            "generation_calls": sum(c["provider"] == "generation" for c in dispatch),
            "review_calls": sum(c["provider"] == "review" for c in dispatch),
            "reported_input_tokens": sum(v["input_tokens"] for v in usage),
            "reported_output_tokens": sum(v["output_tokens"] for v in usage),
            "scene_opinions": len(events("scene_review_finished")),
            "human_reviews": len(events("human_review")),
            "slots": slots,
            "T038_completed": False,
            "actual_invoice_usd": None,
            "assistant_review_is_independent_human_review": False,
            "legacy_cli_human_review_required_is_not_success_evidence": True,
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.parse_args()
    result = inspect()
    frozen = json.loads((BASE / "results.json").read_bytes())
    if result != frozen:
        raise ValueError("RESULTS_DIFFER_FROM_DURABLE_EVIDENCE")
    print(json.dumps(result, ensure_ascii=False))
    return (
        0
        if all(s["engineering_pass"] for s in result["slots"])
        and result["durable_state"] != "stopped"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
