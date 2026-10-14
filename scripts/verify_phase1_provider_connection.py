"""Read-only source/manifest/result/SQLite audit. No Provider config, key or network."""

import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1-provider-connection-v1"


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def verify():
    matrix = [
        ("run-r01.json", "5014173", "r01", ["r01.json"]),
        ("diagnostic-r02.json", "16f46ec", "diagnostic-r02", ["diagnostic-r02.json"]),
        (
            "checks-r03.json",
            "2308846",
            "checks-r03",
            ["checks-r03-structured.json", "checks-r03-stream.json"],
        ),
        ("tool-r04.json", "fa9f467", "tool-r04", ["tool-r04.json"]),
    ]
    attempts = []
    source_files = 0
    for name, commit, folder, results in matrix:
        assert re.fullmatch(r"[a-f0-9]{7,40}", commit)
        manifest = json.loads((BASE / name).read_text())
        for path, expected in manifest["files"].items():
            assert not Path(path).is_absolute() and ".." not in Path(path).parts
            blob = subprocess.run(
                ["git", "show", commit + ":" + path],
                cwd=ROOT,
                capture_output=True,
                check=True,
            ).stdout
            assert digest(blob) == expected, (commit, path)
            source_files += 1
        db = sqlite3.connect(
            f"file:{ROOT / 'local-materials/phase-1-t039' / folder / 'budget.sqlite'}?mode=ro",
            uri=True,
        )
        try:
            binding = db.execute(
                "SELECT freeze,approval FROM run WHERE id=1"
            ).fetchone()
            rows = db.execute(
                "SELECT number,slot,stage,target,request_sha256,cost_micro,state,input_tokens,output_tokens,error_code FROM attempts ORDER BY number"
            ).fetchall()
        finally:
            db.close()
        assert binding[0] == digest(canonical(manifest))
        docs = [
            json.loads((BASE / "results" / result).read_text()) for result in results
        ]
        latest = docs[-1]
        assert latest["budget"]["manifest_sha256"] == binding[0]
        assert latest["budget"]["attempts"] == [list(row) for row in rows]
        for number, slot, _, target, wire, *_ in rows:
            frozen_slot = next(s for s in manifest["slots"] if s["id"] == slot)
            assert (
                target in frozen_slot["targets"] and wire == frozen_slot["input_sha256"]
            )
        assert len(rows) <= manifest["bounds"]["requests"]
        assert sum(row[5] for row in rows) <= manifest["bounds"]["cost_micro"]
        assert all(
            d["persistent_secret_absent"] and d["connection_revoked"] for d in docs
        )
        if folder == "r01":
            assert sum(o["outbound_sends"] for o in latest["observations"]) == len(rows)
        else:
            assert sum(d["outbound_sends"] for d in docs) == len(rows)
            assert all(d["fallbacks"] == d["retries"] == 0 for d in docs)
        attempts.extend(rows)
    assert len(attempts) == 5
    assert sum(row[5] for row in attempts) == 61212
    assert attempts[0][6] == "failed" and attempts[-1][9] == "INVALID_OUTPUT"
    assert all(row[6] == "complete" for row in attempts[1:-1])
    return {
        "source_snapshots_verified": 4,
        "source_file_hashes_verified": source_files,
        "real_attempts": 5,
        "approved_limit": 5,
        "reserved_cost_cny": 0.061212,
        "known_input_tokens": sum(row[7] or 0 for row in attempts),
        "known_output_tokens": sum(row[8] or 0 for row in attempts),
        "attempts_with_unknown_usage": sum(
            row[7] is None or row[8] is None for row in attempts
        ),
        "actual_bill_cny": None,
        "mock_substituted": False,
        "primary": {
            "text": "passed_diagnostic",
            "structured": "passed",
            "stream": "passed",
            "tool": "failed_strict_format",
        },
        "overall_T039_passed": False,
        "remaining": [
            "tool response format",
            "Ollama real connection",
            "Anthropic real connection",
            "Gemini real connection",
            "Spark real connection",
        ],
        "historical_failures_preserved": True,
        "provider_calls_by_this_audit": 0,
    }


if __name__ == "__main__":
    result = verify()
    (BASE / "results/audit-final.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False))
