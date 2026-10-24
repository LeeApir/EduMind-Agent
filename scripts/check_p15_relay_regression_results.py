"""Read-only verification of the stopped relay regression; verified blocked exits 2."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-relay-regression-r01-results"
PACKAGE = "2c379b62b70dbc0d99e9534558e5c3e67edd6403f698c39582997ae1bb8fc9c2"
BATCH = "p15-relay-regression-r01"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def check(base=BASE, root=ROOT):
    result = read(base / "results.json")
    packet = root / "docs/acceptance/phase-1.5-relay-regression-r01"
    assert sha(packet / "manifest.json") == PACKAGE == result["package_sha256"]
    manifest = read(packet / "manifest.json")
    for name, expected in manifest["sha256"].items():
        path = root / name
        assert path.resolve().is_relative_to(root.resolve()) and sha(path) == expected
    assert (
        result["batch_id"] == BATCH and result["status"] == "blocked_candidate_rejected"
    )
    assert result["http_requests"] == 1 and result["model_requests"] == 0
    assert result["count_http_status"] == 404 and result["model_request_sent"] is False
    assert (
        result["old_three_generation_checks"] == "unobserved_not_passed_not_reproduced"
    )
    assert result["actual_invoice"] is None and result["actual_vendor_currency"] is None
    assert (
        result["future_requests_authorized"] == 0 and result["T038_completed"] is False
    )
    assert result["course_diagnostic_preparation_unlocked"] is False
    assert (
        result["candidate_disposition"]
        == "stop_using_current_relay_configuration_per_user_rule"
    )
    assert result["local_unknown_reservation"] == dict(
        input_tokens=4096, output_tokens=16, planning_fee_micros_usd=8208
    )
    assert (
        result["cumulative_http_requests"] == 7
        and result["cumulative_model_requests"] == 3
    )
    assert result["cumulative_unknown_token_holds"] == dict(
        input_tokens=100096, output_tokens=16032
    )
    approvals = {}
    for kind, expected in result["approvals_sha256"].items():
        path = packet / (kind + "-approval.json")
        assert sha(path) == expected
        grant = read(path)
        assert grant["kind"] == kind and grant["scope"] == "PHASE-1.5-T038"
        assert grant["batch_id"] == BATCH and grant["package_sha256"] == PACKAGE
        assert (
            grant["limits"] == manifest["limits"] and grant["fee_cap_waiver"] is False
        )
        assert all(
            grant[k] is True
            for k in (
                "unknown_vendor_currency_and_rates_accepted",
                "unverified_upstream_bounds_risk_accepted",
                "local_usd_allowance_is_not_invoice_cap_accepted",
                "fail_then_discard_no_retry",
                "root_to_v1_mapping_accepted",
                "no_course_admission",
            )
        )
        approvals[kind] = grant
    assert set(approvals) == {"contract", "execution"}
    assert approvals["contract"]["decisions"] == ["A", "B", "C"]
    snapshot = Path(result["snapshot"])
    expected_names = {
        "request.json",
        "summary.json",
        "assessment.json",
        "ledger.sqlite",
        "S1-count-dispatch.json",
        "S1-count-status.json",
        "S1-count-response.json",
    }
    assert set(result["snapshot_sha256"]) == expected_names
    assert {p.name for p in snapshot.iterdir()} == expected_names
    for name, expected in result["snapshot_sha256"].items():
        assert sha(snapshot / name) == expected
    for name, expected in result["source_original_sha256"].items():
        assert (
            Path(name).name == name
            and sha(Path(result["source_original"]) / name) == expected
        )
    assert sha(snapshot / "request.json") == manifest["cases"][0]["body_sha256"]
    dispatch = read(snapshot / "S1-count-dispatch.json")
    assert dispatch["body_sha256"] == manifest["cases"][0]["body_sha256"]
    assert (
        dispatch["method"] == "POST" and dispatch["path"] == "/responses/input_tokens"
    )
    assert read(snapshot / "S1-count-status.json")["http_status"] == 404
    summary, assessment = [
        read(snapshot / name) for name in ("summary.json", "assessment.json")
    ]
    assert (
        summary["http_dispatch_markers"] == 1 and summary["model_dispatch_markers"] == 0
    )
    assert summary["safe_failure_code"] == "HTTP_STATUS_UNVERIFIED"
    assert summary["status"] == "blocked" and summary["verified_cases"] == []
    assert summary["local_accounting"] == dict(
        requests=2, input_tokens=4096, output_tokens=16, fee_micros=8208
    )
    assert assessment["outcome"] == "candidate_rejected_stop_using"
    assert assessment["local_fee_units_are_unvalidated_planning_allowance"] is True
    assert (
        assessment["actual_invoice"] is None
        and assessment["further_calls_authorized"] is False
    )
    db = sqlite3.connect(
        "file:" + str(snapshot / "ledger.sqlite") + "?mode=ro&immutable=1", uri=True
    )
    db.row_factory = sqlite3.Row
    try:
        batch = db.execute("SELECT * FROM batches").fetchall()
        assert (
            len(batch) == 1
            and batch[0]["id"] == BATCH
            and batch[0]["package"] == PACKAGE
        )
        assert (
            batch[0]["state"] == "stopped"
            and batch[0]["reason"] == "provider_contract_failure"
        )
        approval_digest = hashlib.sha256(
            json.dumps(
                approvals["execution"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        ).hexdigest()
        assert batch[0]["approval"] == approval_digest
        attempts = {r["id"]: dict(r) for r in db.execute("SELECT * FROM attempts")}
        assert set(attempts) == {"S1-model", "S1-count"}
        for row in attempts.values():
            assert row["state"] == "unknown"
            assert all(
                row[k] is None for k in ("input_used", "output_used", "fee_used")
            )
        assert tuple(
            attempts["S1-model"][k] for k in ("input_max", "output_max", "fee_max")
        ) == (4096, 16, 8208)
        sent = db.execute("SELECT attempt FROM receipts WHERE kind='sent'").fetchall()
        assert [row[0] for row in sent] == ["S1-count"]
    finally:
        db.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    try:
        check()
    except Exception:
        raise SystemExit(
            "INVALID_OR_INCOMPLETE_RELAY_EVIDENCE; no network performed"
        ) from None
    print(
        "VERIFIED BLOCKED: count HTTP404; 1 HTTP/0 generation; candidate rejected; no retry."
    )
    raise SystemExit(2)
