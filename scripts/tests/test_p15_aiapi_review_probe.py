"""Offline regression tests for review scoring and no silent sample exclusion."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "review_probe", ROOT / "scripts/run_p15_aiapi_review_probe.py"
)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    cases, gold = m.read("cases.json"), m.read("gold.json")
    schema = m.read("request.json")["text"]["format"]["schema"]
    by_id = {c["case_id"]: c["text"] for c in cases}
    rows = [
        {
            "case_id": g["case_id"],
            "verdict": "error" if g["has_error"] else "no_error",
            "evidence": by_id[g["case_id"]][:20] if g["has_error"] else "",
            "reason": "合成计分器测试理由。",
        }
        for g in gold
    ]
    return cases, gold, schema, rows


def evaluate(rows, cases, gold, schema):
    return m.score(json.dumps({"reviews": rows}), cases, gold, schema)


def test_matching_gold():
    cases, gold, schema, rows = fixture()
    r = evaluate(rows, cases, gold, schema)
    assert (r["tp"], r["tn"], r["fp"], r["fn"], r["unknown"]) == (6, 6, 0, 0, 0)


def test_false_positive_and_miss_counted():
    cases, gold, schema, rows = fixture()
    rows[0].update(
        verdict="error",
        evidence=next(c["text"] for c in cases if c["case_id"] == rows[0]["case_id"])[
            :20
        ],
    )
    rows[1].update(verdict="no_error", evidence="")
    r = evaluate(rows, cases, gold, schema)
    assert r["fp"] == r["fn"] == 1
    assert r["detection_fraction_all_errors"][1] == 6


def test_duplicate_does_not_shrink_denominator():
    cases, gold, schema, rows = fixture()
    rows[0] = rows[1]
    r = evaluate(rows, cases, gold, schema)
    assert not r["format_valid"] and r["unknown"] == 12 and r["evaluated"] == 0


def test_fabricated_evidence_is_unknown():
    cases, gold, schema, rows = fixture()
    rows[1]["evidence"] = "并不存在的引用证据"
    r = evaluate(rows, cases, gold, schema)
    assert r["unknown"] == 1 and r["tp"] == 5


def test_fenced_json_not_recovered():
    cases, gold, schema, rows = fixture()
    r = m.score(
        "```json\n" + json.dumps({"reviews": rows}) + "\n```", cases, gold, schema
    )
    assert not r["format_valid"] and r["unknown"] == 12


def test_uncertain_not_counted_as_correct():
    cases, gold, schema, rows = fixture()
    rows[1].update(verdict="uncertain", evidence="")
    r = evaluate(rows, cases, gold, schema)
    assert r["tp"] == 5 and r["uncertain"] == 1
    assert r["detection_fraction_all_errors"] == [5, 6]
