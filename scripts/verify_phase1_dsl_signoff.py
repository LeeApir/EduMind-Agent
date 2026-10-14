"""Read-only audit of the actual T037 media and independently recorded human signoff."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "local-materials/phase-1-t037"
APPROVAL = ROOT / "docs/acceptance/phase-1-dsl-v1/human-review-20261014.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    approval = json.loads(APPROVAL.read_text())
    assert approval["status"] == "approved" and approval["reviewer"] == "Lee"
    assert approval["user_confirmation"] == "核对确认完成"
    run, safety = BASE / "matrix-r06", BASE / "safety-r07"
    manifest_path = run / "human-review/manifest.json"
    assert digest(manifest_path) == approval["review_manifest_sha256"]
    manifest = json.loads(manifest_path.read_text())
    automatic = json.loads((run / "automatic-evidence.json").read_text())
    report = json.loads((run / "matrix-result.json").read_text())
    assert (
        digest(run / "automatic-evidence.json") == approval["automatic_evidence_sha256"]
    )
    assert (
        automatic["automatic_acceptance_passed"] and report["automatic_matrix_passed"]
    )
    assert report["provider_requests"] == automatic["provider_requests"] == 0
    for name, directory in (("matrix", run), ("safety", safety)):
        protocol = directory / (name + "-protocol.json")
        result = json.loads((directory / (name + "-result.json")).read_text())
        assert digest(protocol) == result["protocol_sha256"]
        for path, expected in json.loads(protocol.read_text())["code_sha256"].items():
            blob = subprocess.run(
                ["git", "show", approval["reviewed_code_commit"] + ":" + path],
                cwd=ROOT,
                check=True,
                capture_output=True,
            ).stdout
            assert hashlib.sha256(blob).hexdigest() == expected, path
    assert automatic["evidence_sha256"]["matrix_result"] == digest(
        run / "matrix-result.json"
    )
    assert automatic["evidence_sha256"]["safety_result"] == digest(
        safety / "safety-result.json"
    )
    assert automatic["safety_tests"] == {
        "tests": 295,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
    }
    for group in ("dsl_slots", "template_slots", "cache_slots"):
        assert len(report[group]) == 100 and all(row["ok"] for row in report[group])
    assert len(manifest["cases"]) == 20
    for case in manifest["cases"]:
        assert (
            case["dimensions"] == {"width": 1280, "height": 720} and case["fps"] == 15
        )
        for key in ("mp4", "srt", "vtt", "dsl_file"):
            filename = case["dsl"] if key == "dsl_file" else case[key]
            assert digest(manifest_path.parent / filename) == case[key + "_sha256"]
        assert len(case["frames"]) == 11
        for frame in case["frames"]:
            assert abs(frame["presented_seconds"] - frame["seconds"]) <= 1 / 15 + 1e-6
            assert digest(manifest_path.parent / frame["image"]) == frame["sha256"]
    assert (
        digest(manifest_path.parent / "index.html") == automatic["review_page_sha256"]
    )
    print(
        "T037 signoff verified: human Lee;20 actual720p videos/220 frames;295 safety/300 matrix;Provider0"
    )


if __name__ == "__main__":
    main()
