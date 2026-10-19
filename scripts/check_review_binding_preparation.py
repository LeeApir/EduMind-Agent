"""T070 zero-call readiness check; never starts real acceptance or opens dynamic mode."""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/acceptance/phase-1-review-binding-preparation-t070"


def check():
    manifest = json.loads((PACKAGE / "manifest.json").read_bytes())
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        if (
            path.is_symlink()
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise ValueError("frozen source/evidence changed: " + relative)
    sys.path.insert(0, str(ROOT / "backend"))
    from app.services.learning_policy import POLICY, active_policy_digest
    from app.agents.hybrid_resource_review import UNIT_CHECKS

    if (
        POLICY != manifest["policy"]
        or active_policy_digest() != manifest["policy_digest"]
    ):
        raise ValueError("active policy differs from preparation")
    if sorted(UNIT_CHECKS) != manifest["unit_check_ids"] or len(UNIT_CHECKS) != 6:
        raise ValueError("unit checks changed")
    tasks = {t["id"]: t for t in json.loads((ROOT / "task.json").read_bytes())["tasks"]}
    for number in range(56, 70):
        key = f"PHASE-1-T{number:03}"
        if tasks[key]["status"] != "done":
            raise ValueError("prerequisite unfinished: " + key)
        result = subprocess.check_output(
            [
                "git",
                "log",
                "--fixed-strings",
                f"--grep=Task-Completed: {key}",
                "--format=%H",
            ],
            cwd=ROOT,
            text=True,
        )
        if not result.strip():
            raise ValueError("missing independent completion: " + key)
    task070 = tasks["PHASE-1-T070"]["status"]
    if task070 not in {"in_progress", "done"}:
        raise ValueError("integration task not active/completed")
    if task070 == "done":
        complete = subprocess.check_output(
            [
                "git",
                "log",
                "--fixed-strings",
                "--grep=Task-Completed: PHASE-1-T070",
                "--format=%H",
            ],
            cwd=ROOT,
            text=True,
        )
        if not complete.strip():
            raise ValueError("T070 done without completion commit")
    for task_id, frozen in manifest["task_contracts"].items():
        if {k: tasks[task_id][k] for k in frozen} != frozen:
            raise ValueError("task contract changed: " + task_id)
    if tasks["PHASE-1-T040"]["status"] != "blocked":
        raise ValueError("T040 gate changed")
    if (
        manifest["real_provider_calls_authorized"] != 0
        or manifest["real_acceptance_ready"] is not False
    ):
        raise ValueError("zero-call preparation cannot authorize model tests")
    if manifest["quality_thresholds"] != {
        "schema_first_percent": 98,
        "automatic_formal_success_percent": 95,
        "severe_error_recall_percent": 90,
        "human_counts_as_automatic": False,
    }:
        raise ValueError("quality gates weakened")
    labels = json.loads((PACKAGE / "labels.json").read_bytes())
    if any(
        item["real_model_result"] is not None
        or item["independent_semantic_label"] != "pending"
        for item in labels["diagnostic_design_cases"]
    ):
        raise ValueError("invented model or human label")
    from offline_c_evidence import check_report

    offline = check_report(PACKAGE / "offline-c/report.json")
    if not offline["execution_complete"] or offline["publication_qualified"]:
        raise ValueError("offline evidence boundary changed")
    verification = json.loads((PACKAGE / "verification.json").read_bytes())
    if (
        verification["backend"]["passed"] != 226
        or verification["backend"]["skipped"] != 0
    ):
        raise ValueError("missing actual integrated PG evidence")
    if (
        verification["browser"]["api_kind"] != "route mocks"
        or verification["real_provider_calls"] != 0
    ):
        raise ValueError("mock/actual evidence mixed")
    return {
        "preparation_valid": True,
        "frozen_files": len(manifest["files"]),
        "policy_digest": manifest["policy_digest"],
        "real_acceptance_ready": False,
        "real_calls_authorized": 0,
        "T040": "blocked",
        "default": "catalog_only",
        "offline_fixed_cases": offline,
        "remaining_real_gates": manifest["remaining_real_gates"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    try:
        print(json.dumps(check(), ensure_ascii=False, indent=2))
    except (
        OSError,
        ValueError,
        KeyError,
        AssertionError,
        subprocess.SubprocessError,
    ) as error:
        parser.exit(1, f"Preparation rejected: {error}\n")


if __name__ == "__main__":
    main()
