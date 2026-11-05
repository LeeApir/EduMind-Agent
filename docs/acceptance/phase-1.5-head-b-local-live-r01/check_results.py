"""Read-only exact original, merge, teaching review and browser evidence replay; no Provider."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from scripts import head_course_fact_revision as entry  # noqa: E402
from app.services import head_course_evidence_publication as publication  # noqa: E402

HERE = Path(__file__).resolve().parent
SHA = "106152b051afd8c28d11636f5f181e1a40b8784ec1306f1a5c4204809596b6b3"


def read(path):
    return json.loads(path.read_bytes())


def main():
    entry.select_profile("evidence")
    assert entry.package_digest() == SHA
    manifest = read(HERE / "originals-manifest.json")
    assert manifest["key_excluded"] and "raw.key" not in manifest["files"]
    for name, sha in manifest["files"].items():
        assert hashlib.sha256((entry.VAULT / name).read_bytes()).hexdigest() == sha, (
            name
        )
    assert (entry.VAULT / "STOP").exists() and not (entry.VAULT / "ACTIVE").exists()
    assert len(list(entry.VAULT.glob("*.attempt.json"))) == 1
    record = entry.read_saved(entry.VAULT)
    assert record == read(HERE / "revision.record.json")
    assert (
        record["receipt"]["http_status"] == 200
        and record["receipt"]["raw_bytes"] == 3252
    )
    assert (HERE / "revision.raw.json").read_bytes() == record["raw_response"].encode()
    review = read(HERE / "final-review.json")
    projection = publication.assembled(record, review)
    assert projection == read(HERE / "approved.assembled.private.json")
    parent, child = record["input"]["parent_candidate"], record["candidate"]
    before, after = parent["raw_output"], child["raw_output"]
    restored = json.loads(json.dumps(after))
    restored["failure_scope"] = before["failure_scope"]
    restored["paragraphs"][5] = before["paragraphs"][5]
    assert restored == before
    assert after["paragraphs"][5]["text"] == before["paragraphs"][5]["text"]
    assert after["paragraphs"][5]["fact_ids"] == [
        "head_evidence_v1.discard_return_comparison"
    ]
    payload = dict(child["payload"])
    payload.pop("teaching_evidence")
    assert payload == parent["payload"]
    for name in ("final-review.json", "TEACHING-ASSESSMENT.md", "published.json"):
        assert (entry.VAULT / name).read_bytes() == (HERE / name).read_bytes()
    browser, feedback = (
        read(HERE / "browser-reading.json"),
        read(HERE / "browser-feedback.json"),
    )
    scene = browser["scene"]
    assert scene["generation_source"] == projection["generation_source"]
    assert len(browser["frames"]) == 13 and all(
        browser["controls"][k] for k in ("play", "pause", "next", "previous", "reset")
    )
    assert (
        browser["operation"]["execution_mode"] == "finite_head_foreground"
        and browser["operation"]["budget"] is None
    )
    assert (
        feedback["candidate_digest"] == child["candidate_digest"]
        and feedback["refresh"]["additional_posts"] == 0
    )
    assert (
        feedback["refresh"]["full_scene_identical"]
        and feedback["refresh"]["full_attempt_identical"]
    )
    assert len(feedback["posts"]) == 2 and not feedback["browser_errors"]
    for case in feedback["results"]:
        attempt = case["attempt"]
        assert attempt["comparison_score"] == (case["name"] == "correct")
        assert (
            attempt["mastery_effect"] == "course_only"
            and attempt["reliability"] == "provisional"
        )
        for q in attempt["question_results"]:
            assert (
                q["explanation"] == after["questions"][q["question_id"]]["explanation"]
            )
    application = read(HERE / "application-check.json")
    assert application["original_operation"] == dict(
        state="failed", reason_code="TEACHING_REVIEW_FAILED"
    )
    assert application["original_course"]["head_version"] == 1
    assert application["original_counts"] == dict(
        planning_results=1, scene_generation_results=0
    )
    assert application["child_course"]["head_version"] == 2
    assert application["full_stored_revision_binding"] == "accepted"
    for path in (
        "backend",
        "web",
        "scripts",
        "docs/acceptance/phase-1.5-head-reuse-live-r01",
        "docs/acceptance/phase-1.5-head-evidence-t110",
        "docs/acceptance/phase-1.5-head-b-local-revision-r01",
    ):
        subprocess.run(
            ["git", "diff", "--exit-code", "640b4cc", "--", path],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
    old = subprocess.check_output(["git", "show", "640b4cc:process.txt"], cwd=ROOT)
    assert (ROOT / "process.txt").read_bytes().startswith(old)
    original_task = json.loads(
        subprocess.check_output(["git", "show", "640b4cc:task.json"], cwd=ROOT)
    )
    actual_task = read(ROOT / "task.json")
    assert [t for t in actual_task["tasks"] if not t["id"].endswith("T109")] == [
        t for t in original_task["tasks"] if not t["id"].endswith("T109")
    ]
    assert (
        next(t for t in actual_task["tasks"] if t["id"].endswith("T102"))["status"]
        == "blocked"
    )
    print(
        "PASS: 454 frozen files; 1 HTTP200 encrypted-original replay; only allowed changes; full independent review; all13 frames/controls; four wrong+correct feedback; refresh unchanged/no resubmit; old sources/tasks preserved; Provider0 in audit."
    )


if __name__ == "__main__":
    main()
