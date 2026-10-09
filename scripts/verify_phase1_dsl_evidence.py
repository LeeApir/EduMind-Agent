"""Validate T037 actual automatic evidence; human media review stays a separate gate."""

import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "local-materials/phase-1-t037"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    run = Path(sys.argv[1]).resolve()
    assert run.parent == BASE.resolve()
    report = json.loads((run / "matrix-result.json").read_text())
    plan = json.loads((run / "matrix-protocol.json").read_text())
    safety_path = Path(sys.argv[2]).resolve() / "safety-result.json"
    assert safety_path.parent.parent == BASE.resolve()
    safety = json.loads(safety_path.read_text())
    assert safety["passed"] and safety["counts"] == {
        "tests": 288,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    assert not (run / "visual-failure.json").exists(), (
        "Failed visual evidence cannot qualify"
    )
    assert report["automatic_matrix_passed"] and report["human_review"] == "pending"
    safety_plan = json.loads((safety_path.parent / "safety-protocol.json").read_text())
    assert (
        digest(safety_path.parent / "safety-protocol.json") == safety["protocol_sha256"]
    )
    for name, expected in safety_plan["code_sha256"].items():
        assert digest(ROOT / name) == expected, name
    assert report["provider_requests"] == safety["provider_requests"] == 0
    assert digest(run / "matrix-protocol.json") == report["protocol_sha256"]
    assert (run / "matrix-protocol.json").read_bytes() == (
        ROOT / "docs/acceptance/phase-1-dsl-v1/matrix-protocol.json"
    ).read_bytes()
    for name, expected in plan["code_sha256"].items():
        assert digest(ROOT / name) == expected, name
    for group in ("dsl_slots", "template_slots", "cache_slots"):
        actual = report[group]
        assert len(actual) == 100 and len({row["id"] for row in actual}) == 100
        assert all(
            {k: row[k] for k in frozen} == frozen
            for row, frozen in zip(actual, plan[group], strict=True)
        )
        assert all(
            row["ok"] and row["mp4_sha256"] and row["srt_sha256"] for row in actual
        )
    assert Counter(row["template_id"] for row in report["template_slots"]) == {
        "linked-list-insertion": 50,
        "linked-list-deletion": 50,
    }
    assert Counter(row["source"] for row in report["cache_slots"]) == {
        "dsl": 50,
        "template": 50,
    }
    assert Counter(row["case_index"] for row in report["dsl_slots"]) == dict.fromkeys(
        range(20), 5
    )
    for group in ("dsl_slots", "template_slots"):
        cold = [row for row in report[group] if row["cold"]]
        assert len(cold) == 20
        p95 = sorted(row["ready_seconds"] for row in cold)[math.ceil(0.95 * 20) - 1]
        assert p95 <= 90
        if group == "dsl_slots":
            assert p95 == report["dsl_uncached_p95_seconds"]
    for source in ("dsl", "template"):
        rows = [row for row in report["cache_slots"] if row["source"] == source]
        assert len(rows) == 50 and all(row["ready_seconds"] <= 2 for row in rows)
        assert (
            sorted(row["ready_seconds"] for row in rows)[47]
            == report[source + "_cache_p95_seconds"]
        )
    review = run / "human-review/manifest.json"
    manifest = json.loads(review.read_text())
    assert manifest["human_review"] == "pending" and len(manifest["cases"]) == 20
    assert manifest["matrix_result_sha256"] == digest(run / "matrix-result.json")
    assert manifest["protocol_sha256"] == report["protocol_sha256"]
    for case in manifest["cases"]:
        for key in ("mp4", "srt", "vtt", "dsl_file"):
            name = case["dsl"] if key == "dsl_file" else case[key]
            assert digest(review.parent / name) == case[key + "_sha256"]
        assert len(case["frames"]) == 11
        for frame in case["frames"]:
            assert digest(review.parent / frame["image"]) == frame["sha256"]
    result = {
        "task_id": "PHASE-1-T037",
        "automatic_acceptance_passed": True,
        "full_task_complete": False,
        "human_review": "pending",
        "provider_requests": 0,
        "safety_tests": safety["counts"],
        "dsl_legal": {"passed": 100, "denominator": 100},
        "template_legal": {"passed": 100, "denominator": 100},
        "cache": {"passed": 100, "denominator": 100, "dsl": 50, "template": 50},
        "dsl_uncached_p95_seconds_upper_bound": report["dsl_uncached_p95_seconds"],
        "dsl_cache_p95_seconds_upper_bound": report["dsl_cache_p95_seconds"],
        "template_cache_p95_seconds_upper_bound": report["template_cache_p95_seconds"],
        "timing_qualification": "client monotonic upper bound includes playing and subsequent MP4/SRT export verification",
        "review_manifest_sha256": digest(review),
        "review_page_sha256": digest(review.parent / "index.html"),
        "unique_actual_dsl_media": 20,
        "step_frames": 220,
        "hardware": plan["hardware"],
        "evidence_sha256": {
            "matrix_result": digest(run / "matrix-result.json"),
            "matrix_protocol": digest(run / "matrix-protocol.json"),
            "safety_result": digest(safety_path),
        },
    }
    destination = run / "automatic-evidence.json"
    assert not destination.exists(), "Never overwrite complete evidence"
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
