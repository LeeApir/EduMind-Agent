"""Verify one direct generation and distinguish benign Schema echo defaults offline."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1.5-direct-relay-once-d01"


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def core_schema_matches(expected, actual):
    return isinstance(actual, dict) and all(
        actual.get(k) == v for k, v in expected.items()
    )


def check():
    m, r, auth = [
        read(BASE / f)
        for f in ("manifest.json", "results.json", "execution-authorization.json")
    ]
    assert sha(BASE / "manifest.json") == r["package_sha256"] == auth["package_sha256"]
    for name, expected in m["sha256"].items():
        path = ROOT / name
        assert path.resolve().is_relative_to(ROOT.resolve()) and sha(path) == expected
    assert r["http_requests"] == r["model_requests"] == 1 and r["http_status"] == 200
    assert r["count_call_sent"] is False and r["count_equivalence_tested"] is False
    assert r["schema_core_fields_match"] is True and r["T038_completed"] is False
    assert r["actual_invoice"] is None and r["future_requests_authorized"] == 0
    assert r["new_manifest_independently_human_reviewed"] is False
    assert auth["new_manifest_independently_human_reviewed"] is False
    assert (
        auth["authorization_basis"]
        == "latest_explicit_single_direct_generation_instruction"
    )
    assert (
        sha(BASE / "execution-authorization.json")
        == r["execution_authorization_sha256"]
    )
    snapshot = Path(r["snapshot"])
    assert {p.name for p in snapshot.iterdir()} == set(r["snapshot_sha256"])
    assert set(r["snapshot_sha256"]) == {
        "summary.json",
        "response.json",
        "status.json",
        "dispatch.json",
        "ledger.sqlite",
        "request.json",
    }
    for name, expected in r["snapshot_sha256"].items():
        assert sha(snapshot / name) == expected
    for name, expected in r["source_original_sha256"].items():
        assert (
            Path(name).name == name
            and sha(Path(r["source_original"]) / name) == expected
        )
    body, response, summary = [
        read(snapshot / f) for f in ("request.json", "response.json", "summary.json")
    ]
    assert sha(snapshot / "request.json") == m["body_sha256"]
    assert read(snapshot / "status.json")["http_status"] == 200
    assert (
        read(snapshot / "dispatch.json")["public_url"]
        == "https://www.cbbb.fun/v1/responses"
    )
    assert (
        response["object"] == "response"
        and response["status"] == "completed"
        and response["error"] is None
    )
    assert response["model"] == "gpt-6-luna"
    expected, actual = body["text"]["format"], response["text"]["format"]
    assert core_schema_matches(expected, actual)
    assert (
        set(actual) - set(expected) == {"description"} and actual["description"] is None
    )
    # Preserve the executed observer's false-positive, explicitly correct its interpretation.
    assert summary["observation"]["checks"]["schema_echo_matches"] is False
    original = "\n\n".join(v["content"] for v in body["input"] if v["role"] == "system")
    ins = response["instructions"]
    assert isinstance(ins, str) and ins.startswith(original)
    suffix = ins[len(original) :]
    assert len(suffix) == r["unrequested_suffix_chars"] == 21336
    assert (
        hashlib.sha256(suffix.encode()).hexdigest()
        == r["unrequested_suffix_sha256"]
        == "405163336914c9b2b4342e94a5f53acab1ca31f491a9fea8d3755de4c1159225"
    )
    assert body["max_output_tokens"] == 16 and response["max_output_tokens"] is None
    assert (
        {
            k: response["usage"][k]
            for k in ("input_tokens", "output_tokens", "total_tokens")
        }
        == r["provider_reported_usage"]
        == dict(input_tokens=4438, output_tokens=13, total_tokens=4451)
    )
    text = "".join(
        c["text"]
        for item in response["output"]
        if item.get("type") == "message"
        for c in item["content"]
        if c.get("type") == "output_text"
    )
    assert json.loads(text) == {"result": "OK"}
    assert summary["http_dispatch_markers"] == summary["model_dispatch_markers"] == 1
    assert (
        summary["count_call_sent"] is False
        and summary["count_equivalence_tested"] is False
    )
    assert summary["local_accounting"] == dict(
        requests=1, input_tokens=4096, output_tokens=16, fee_micros=10000
    )
    db = sqlite3.connect(
        "file:" + str(snapshot / "ledger.sqlite") + "?mode=ro&immutable=1", uri=True
    )
    try:
        assert db.execute("SELECT state,reason FROM batches").fetchall() == [
            ("stopped", "provider_contract_failure")
        ]
        assert db.execute(
            "SELECT id,state,input_max,output_max,fee_max,input_used,output_used,fee_used FROM attempts"
        ).fetchall() == [("direct-model", "unknown", 4096, 16, 10000, None, None, None)]
        assert db.execute(
            "SELECT attempt FROM receipts WHERE kind='sent'"
        ).fetchall() == [("direct-model",)]
    finally:
        db.close()
    return r


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    try:
        check()
    except Exception:
        raise SystemExit("INVALID_DIRECT_OBSERVATION_EVIDENCE; no network") from None
    print(
        "VERIFIED BLOCKED: HTTP200 fixed OK; same injected suffix, null output cap; Schema core matches; no count test or retry."
    )
    raise SystemExit(2)
