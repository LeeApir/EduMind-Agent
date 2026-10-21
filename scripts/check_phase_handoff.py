"""Read-only Phase 1 closeout provenance and Phase 1.5 activation-boundary checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "docs/acceptance/phase-1-closeout-20261021"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def read(path):
    return json.loads(path.read_bytes())


def require(value, reason):
    if not value:
        raise ValueError(reason)


def structure(phase1, active, archive_bytes, receipt):
    require(sha(archive_bytes) == receipt["final_root_sha256_before_switch"], "ARCHIVE_BYTES_CHANGED")
    tasks = {t["id"]: t for t in phase1["tasks"]}
    require(len(tasks) == len(phase1["tasks"]) == 91, "P1_TASK_COUNT")
    require(sum(t["status"] == "done" for t in tasks.values()) == 89, "P1_DONE_COUNT")
    require({t["id"] for t in tasks.values() if t["status"] == "blocked"} == {"PHASE-1-T040", "PHASE-1-T041"}, "BLOCKERS_NOT_RETIRED_AS_PASS")
    require(tasks["PHASE-1-T042"]["status"] == "done", "CLOSEOUT_NOT_DONE")
    require(all(tasks[d]["status"] == "done" for d in tasks["PHASE-1-T042"]["depends_on"]), "CLOSEOUT_DEPENDS_ON_BLOCKED_TASK")
    require(phase1["active_phase"] == "Phase 1", "ARCHIVE_PHASE")
    require(active["active_phase"] == "Phase 1.5", "NEW_PHASE")
    require(active["execution_policy"]["phase_gate"] == "Await explicit user instruction; do not start Phase 1.5 development.", "NO_AUTOMATIC_START")
    require(active["stage_scope"]["provider_requests_authorized"] == 0 and active["stage_scope"]["product_mode"] == "catalog_only", "NO_BUDGET_OR_DYNAMIC_INHERITANCE")
    require(all(t["phase"] == "Phase 1.5" and t["status"] == "todo" and t["started_at"] is None and t["completed_at"] is None for t in active["tasks"]), "NEW_TASK_ALREADY_STARTED")
    require(all(d in {t["id"] for t in active["tasks"]} for t in active["tasks"] for d in t["depends_on"]), "ARCHIVED_TASK_IS_NOT_ACTIVE_DEPENDENCY")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-commit", action="store_true", help="Only T042 marker is expected in the pending governance commit.")
    args = parser.parse_args()
    phase1 = read(ROOT / "docs/tasks/phase-1.json")
    active = read(ROOT / "task.json")
    receipt = read(BASE / "transition.json")
    structure(phase1, active, (ROOT / "docs/tasks/phase-1.json").read_bytes(), receipt)
    require(sha((ROOT / "task.json").read_bytes()) == receipt["new_active_sha256"], "NEW_ROOT_CHANGED")
    audit = read(BASE / "completed-task-audit.json")
    expected = {t["id"] for t in phase1["tasks"] if t["status"] == "done"} - {"PHASE-1-T042"}
    require({r["task_id"] for r in audit["tasks"]} == expected and len(expected) == 88, "AUDIT_NOT_ALL_ORIGINAL_DONE")
    count = 0
    for row in audit["tasks"]:
        h, tid = row["completion_commit"], row["task_id"]
        require(f"Task-Completed: {tid}" in git("show", "-s", "--format=%B", h).decode().splitlines(), "EXACT_COMPLETION_MARKER")
        subprocess.run(["git", "merge-base", "--is-ancestor", h, "HEAD"], cwd=ROOT, check=True)
        original = next(t for t in json.loads(git("show", h + ":task.json"))["tasks"] if t["id"] == tid)
        require(original["status"] == "done" and original["verification_results"] == row["verification_at_completion"], "HISTORICAL_VERIFICATION_CHANGED")
        require(f"[{tid}] VERIFIED" in git("show", h + ":process.txt").decode(), "NO_VERIFIED_LOG")
        for item in row["committed_evidence_and_tests"]:
            require(sha(git("show", h + ":" + item["path"])) == item["sha256"], "COMMIT_EVIDENCE_CHANGED")
        require(row["committed_evidence_and_tests"] or row["existing_evidence_references"], "NO_SURVIVING_EVIDENCE")
        for item in row["existing_evidence_references"]:
            p = ROOT / item["path"]
            require(p.is_file(), "EVIDENCE_PATH_MISSING")
            if sha(p.read_bytes()) != item["sha256"]:
                # Scope docs are intentionally updated; their original Git bytes remain auditable.
                require(not item["path"].startswith("local-materials/"), "LOCAL_EVIDENCE_CHANGED")
                require(sha(git("show", audit["source_commit"] + ":" + item["path"])) == item["sha256"], "NO_HISTORICAL_EVIDENCE_BYTES")
        count += 1
    seals = read(BASE / "preservation-seals.json")
    for group in ("historical_and_H_seals", "all_sqlite_seals", "json_receipt_seals", "protected_uncommitted_files"):
        for path, h in seals[group].items():
            require(sha((ROOT / path).read_bytes()) == h, "PRESERVED_FILE_CHANGED: " + path)
    # The source guard is unchanged; execution is covered by the separate targeted pytest evidence.
    require(git("show", audit["source_commit"] + ":backend/app/core/product_mode.py") == (ROOT / "backend/app/core/product_mode.py").read_bytes(), "PRODUCT_GUARD_CHANGED")
    marker = "Task-Completed: PHASE-1-T042"
    matches = git("log", "--format=%H", "--fixed-strings", "--grep=" + marker).decode().splitlines()
    if not args.before_commit:
        exact = [h for h in matches if marker in git("show", "-s", "--format=%B", h).decode().splitlines()]
        require(bool(exact), "CLOSEOUT_COMMIT_MISSING")
        h = exact[0]
        for path in ("task.json", "docs/tasks/phase-1.json", "process.txt"):
            require(git("show", h + ":" + path) == (ROOT / path).read_bytes(), "ARCHIVE_AND_SWITCH_NOT_IN_SAME_COMMIT")
    print(json.dumps(dict(original_done_verified=count,final_phase1="89 done / 2 blocked",archive_bytes="exact",active_phase="Phase 1.5",started_tasks=0,provider_requests_this_closeout=0,H="sealed",protected_user_files="unchanged",T042_commit="pending same governance commit" if args.before_commit else "verified with archive and switch")))


if __name__ == "__main__":
    main()
