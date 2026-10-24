"""Read-only verification of the terminated approved p01; no transport or credentials."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = Path("docs/acceptance/phase-1.5-compatibility-probe-p01-results/results.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def check(root=ROOT):
    report = json.loads((root / REPORT).read_text())
    manifest_path = root / report["manifest"]
    assert (
        sha(manifest_path)
        == report["manifest_sha256"]
        == "160adb246d63464c05abb6e23f110ecbc40ffe20efa3f86e8c6ee4c98065d3f4"
    )
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest["sha256"].items():
        assert sha(root / name) == expected, name
    grants = {}
    for kind, info in report["grants"].items():
        assert sha(root / info["path"]) == info["sha256"]
        grant = json.loads((root / info["path"]).read_text())
        assert grant["kind"] == kind and grant["package_sha256"] == sha(manifest_path)
        assert (
            grant["batch_id"] == manifest["batch_id"]
            and grant["limits"] == manifest["limits"]
        )
        assert grant["human_message"] == "批准 A—C 及该准确单次执行（含上述风险）"
        assert grant["evidence_ref"] and grant["reviewer"] and grant["received_at"]
        grants[kind] = grant
    assert set(grants) == {"contract", "execution"}
    assert grants["contract"]["decisions"] == ["A", "B", "C"]
    assert all(
        grants["execution"][k] is True
        for k in (
            "fee_cap_waiver",
            "unverified_upstream_bounds_risk_accepted",
            "no_course_admission",
        )
    )
    paths = {}
    for entry in report["raw_evidence"]:
        path = Path(entry["path"])
        assert (
            path.is_absolute()
            and path.stat().st_size == entry["bytes"]
            and sha(path) == entry["sha256"]
        )
        assert entry["name"] not in paths
        paths[entry["name"]] = path
    snapshot = paths["ledger.snapshot.sqlite"]
    assert (
        not Path(str(snapshot) + "-wal").exists()
        and not Path(str(snapshot) + "-journal").exists()
    )
    with sqlite3.connect(
        "file:" + str(snapshot) + "?mode=ro&immutable=1", uri=True
    ) as db:
        db.row_factory = sqlite3.Row
        batch = db.execute("SELECT * FROM batches").fetchone()
        assert batch["id"] == manifest["batch_id"] and batch["package"] == sha(
            manifest_path
        )
        assert batch["approval"] == digest(grants["execution"])
        assert (batch["state"], batch["reason"]) == (
            "stopped",
            "provider_contract_failure",
        )
        attempts = db.execute("SELECT * FROM attempts").fetchall()
        receipts = db.execute("SELECT * FROM receipts").fetchall()
    assert len(attempts) == 2
    model = next(a for a in attempts if a["id"].endswith("-model"))
    counter = next(a for a in attempts if a["id"].endswith("-count"))
    assert model["state"] == "unknown" and counter["state"] == "complete"
    assert model["input_used"] is model["output_used"] is model["fee_used"] is None
    assert (model["input_max"], model["output_max"]) == (32000, 16)
    assert sum(r["kind"] == "sent" for r in receipts) == 2
    sent = [
        json.loads(p.read_text()) for n, p in paths.items() if n.endswith("-send.json")
    ]
    assert sorted(s["path"] for s in sent) == [
        "/v1/responses",
        "/v1/responses/input_tokens",
    ]
    assert all(s["body_sha256"] == sha(paths["request.json"]) for s in sent)
    statuses = [
        json.loads(p.read_text())["http_status"]
        for n, p in paths.items()
        if n.endswith("-status.json")
    ]
    assert statuses == [200, 200]
    raw = [
        json.loads(p.read_bytes()) for n, p in paths.items() if n.endswith("-body.json")
    ]
    count = next(r for r in raw if r.get("object") == "response.input_tokens")
    response = next(r for r in raw if r.get("object") == "response")
    assert count["input_tokens"] == report["preflight_input_tokens"] == 37
    assert response["model"] == "gpt-6-luna" and response["status"] == "completed"
    assert (
        response["max_output_tokens"] is None
        and response["usage"]["input_tokens"] == 4438
    )
    assert response["usage"]["output_tokens"] == 13
    attr = response["usage"]["attribution"]
    assert (
        report["reported_attribution"]
        == {
            "instructions": attr["request_fields"]["instructions"]["input_tokens"],
            "text_format": attr["request_fields"]["text.format"]["input_tokens"],
            "items_sum": sum(v["input_tokens"] for v in attr["items"].values()),
        }
        == {"instructions": 4401, "text_format": 27, "items_sum": 10}
    )
    assert (
        report["input_delta"]
        == 4438 - 37
        == report["reported_attribution"]["instructions"]
    )
    request = json.loads(paths["request.json"].read_bytes())
    assert sha(paths["request.json"]) == sha(manifest_path.parent / "request.json")
    expected = "\n\n".join(
        m["content"] for m in request["input"] if m["role"] == "system"
    )
    assert response["instructions"].startswith(expected)
    suffix = response["instructions"][len(expected) :]
    assert len(suffix) == report["suffix_characters"] == 21336
    assert (
        hashlib.sha256(suffix.encode()).hexdigest()
        == report["suffix_sha256"]
        == "405163336914c9b2b4342e94a5f53acab1ca31f491a9fea8d3755de4c1159225"
    )
    assert json.loads(response["output"][0]["content"][0]["text"]) == {"result": "OK"}
    assert response["text"]["format"]["schema"] == request["text"]["format"]["schema"]
    issues = [
        json.loads(p.read_text())["issues"]
        for n, p in paths.items()
        if n.endswith("-rejected.json")
    ]
    assert issues == [
        ["INSTRUCTIONS_UNVERIFIED", "OUTPUT_LIMIT_UNVERIFIED", "INPUT_COUNT_MISMATCH"]
    ]
    summary = json.loads(paths["summary.json"].read_text())
    assert (
        summary["verified_protocol_usage"] is None
        and summary["actual_relay_fee"] is None
    )
    assert (
        summary["provider_reported_usage"]
        == report["provider_reported_usage"]
        == {"input_tokens": 4438, "output_tokens": 13, "total_tokens": 4451}
    )
    assert report["http_attempts"] == 2 and report["model_requests"] == 1
    assert report["T038_status"] == "blocked" and report["course_admitted"] is False
    assert report["actual_relay_fee"] is None and report["automatic_retry"] is False
    assert report["unknown_reservation"] == {"input_tokens": 32000, "output_tokens": 16}
    previous_http, previous_models, previous_input, previous_output = 0, 0, 0, 0
    for info in report["previous_results"]:
        assert sha(root / info["path"]) == info["sha256"]
        old = json.loads((root / info["path"]).read_text())
        previous_http += old["http_attempts"]
        previous_models += old["model_requests"]
        previous_input += old["unknown_reservation"]["input_tokens"]
        previous_output += old["unknown_reservation"]["output_tokens"]
    assert (previous_http, previous_models, previous_input, previous_output) == (
        4,
        2,
        64000,
        16000,
    )
    assert (
        report["cumulative_http_attempts"] == 6
        and report["cumulative_model_requests"] == 3
    )
    assert report["cumulative_unknown_reservation"] == {
        "input_tokens": 96000,
        "output_tokens": 16016,
    }
    assert report["verdict"] == "blocked_not_admitted"
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    check()
    print(
        "VERIFIED BLOCKED p01: 37 != 4438; same unrequested suffix; null output limit; no retry."
    )
    raise SystemExit(2)
