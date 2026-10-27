"""Read-only receipt verification; success means synthetic observations, not admission."""

import hashlib
import json
import sqlite3
from pathlib import Path

import run_p15_deepseek_flash_r01 as probe


def check(base=probe.BASE):
    meta = probe.parse((base / "results.json").read_bytes())
    _, package, plan = probe.load_package()
    assert meta["package_sha256"] == package
    snapshot = Path(meta["private_snapshot"])
    assert not snapshot.is_symlink()
    for name, sha in meta["evidence_sha256"].items():
        path = (snapshot / name).resolve()
        assert path.is_relative_to(snapshot.resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    summary = probe.parse((snapshot / "summary.json").read_bytes())
    assert summary["package_sha256"] == package
    assert summary["state"] == "two_synthetic_observations_only_unsettled"
    assert summary["safe_failure_code"] is None
    assert summary["dispatch_markers"] == ["S1", "S2"]
    assert summary["T038_completed"] is False
    assert summary["course_generation_authorized"] is False
    assert summary["review_calls"] == 0 and summary["actual_invoice_usd"] is None
    expected_accounting = {
        "requests": 2,
        "input_tokens": 8192,
        "output_tokens": 640,
        "fee_micros": 10000,
    }
    assert summary["local_accounting"] == expected_accounting
    observations = {}
    for name in ("S1", "S2"):
        request_raw = (probe.BASE / f"{name}.json").read_bytes()
        body = probe.parse(request_raw)
        dispatch = probe.parse((snapshot / f"{name}-dispatch.json").read_bytes())
        assert dispatch == {
            "url": probe.URL,
            "body_sha256": hashlib.sha256(request_raw).hexdigest(),
            "request_bytes": len(request_raw),
        }
        assert probe.parse((snapshot / f"{name}-status.json").read_bytes()) == {
            "http_status": 200
        }
        raw = (snapshot / f"{name}-response.bin").read_bytes()
        reply, events = (
            probe.parse_stream(raw) if body["stream"] else (probe.parse(raw), None)
        )
        observations[name] = {
            **probe.observe(body, reply, plan["expected"][name]),
            "events": events,
        }
    assert observations == summary["observations"] == meta["observations"]
    ledger = snapshot / "ledger.sqlite"
    assert all(not Path(str(ledger) + suffix).exists() for suffix in ("-wal", "-shm"))
    grant = probe.parse((probe.BASE / "execution-authorization.json").read_bytes())
    with sqlite3.connect(f"file:{ledger}?mode=ro&immutable=1", uri=True) as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert db.execute("SELECT package,approval,state FROM batches").fetchall() == [
            (package, probe.digest(grant), "stopped")
        ]
        assert db.execute(
            "SELECT id,state,input_max,output_max,fee_max FROM attempts ORDER BY id"
        ).fetchall() == [
            ("S1", "unknown", 4096, 128, 5000),
            ("S2", "unknown", 4096, 512, 5000),
        ]
        recorded = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT body FROM receipts WHERE kind='terminal_result'"
            )
        ]
        assert recorded == [summary]
    assert meta["actual_http_responses"] == 2
    assert meta["actual_generation_requests"] == 2
    assert meta["T038_completed"] is False
    return {
        "verified_synthetic_cases": 2,
        "course_admission": False,
        "actual_invoice_usd": None,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(check()))
    except Exception:
        raise SystemExit("RESULT_EVIDENCE_MISSING_OR_CHANGED") from None
