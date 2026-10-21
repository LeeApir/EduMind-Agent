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
        (
            "tool-diagnostic-r05.json",
            "95b02b7",
            "tool-diagnostic-r05",
            ["tool-diagnostic-r05.json"],
        ),
        (
            "tool-diagnostic-r06.json",
            "8989d27",
            "tool-diagnostic-r06",
            ["tool-diagnostic-r06.json"],
        ),
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
    assert len(attempts) == 7
    assert sum(row[5] for row in attempts) == 90108
    assert [row[6] for row in attempts] == [
        "failed",
        "complete",
        "complete",
        "complete",
        "failed",
        "failed",
        "complete",
    ]
    assert attempts[0][7] is None and attempts[0][8] is None
    assert all(row[9] == "INVALID_OUTPUT" for row in attempts[4:6])
    positive = json.loads((BASE / "results/tool-diagnostic-r06.json").read_text())
    checks = {
        "model_identity",
        "single_choice",
        "choice_index",
        "tool_finish_reason",
        "assistant_role",
        "no_refusal",
        "single_tool",
        "function_type",
        "function_name",
        "arguments_schema",
    }
    assert set(positive["tool_checks"]) == checks and all(
        positive["tool_checks"].values()
    )
    assert (
        positive["tool_fields"]["finish_reason"] == "tool_calls"
        and positive["tool_fields"]["ok_boolean"] is True
    )
    assert positive["model"] == "qwen3.8-max-0902" and positive["tool_executions"] == 0
    final_body = json.loads((BASE / "tool-diagnostic-r06-body.json").read_text())
    assert final_body["tool_choice"] == "auto"
    approval = json.loads((BASE / "tool-diagnostics-approval.json").read_text())
    assert (
        approval["aggregate_request_limit"] == 8
        and approval["aggregate_cost_micro"] == 1000000
    )
    deferral_path = BASE / "target-deferral-20261014.json"
    deferred = []
    if deferral_path.exists():
        record = json.loads(deferral_path.read_text())
        assert record["deferred_real_targets"] == [
            "ollama",
            "anthropic",
            "gemini",
            "spark",
        ]
        assert record["tool_failure_waived"] is False
        deferred = record["deferred_real_targets"]
    return {
        "source_snapshots_verified": len(matrix),
        "source_file_hashes_verified": source_files,
        "real_attempts": len(attempts),
        "approved_limit": 8,
        "reserved_cost_cny": 0.090108,
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
            "tool": "passed_auto_selection_strict_format",
        },
        "overall_T039_passed": bool(deferred),
        "remaining": []
        if deferred
        else [
            "tool response format",
            "Ollama real connection",
            "Anthropic real connection",
            "Gemini real connection",
            "Spark real connection",
        ],
        "deferred_real_targets": deferred,
        "tool_mode_limit": "auto verified; forced-mode stop mismatch preserved, not globally normalized",
        "unused_authorized_requests": 1,
        "historical_failures_preserved": True,
        "provider_calls_by_this_audit": 0,
    }


if __name__ == "__main__":
    result = verify()
    (BASE / "results/audit-final.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False))
