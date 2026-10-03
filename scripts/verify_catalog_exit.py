"""Read-only catalog exit audit: reuse immutable evidence, never run services or models."""

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__" and Path(sys.prefix) != ROOT / "backend/.venv":
    python = ROOT / "backend/.venv/bin/python"
    if not python.exists():
        raise SystemExit("Backend locked dependencies are required")
    os.execv(str(python), [str(python), __file__, *sys.argv[1:]])

sys.path.insert(0, str(ROOT / "backend"))
from verify_catalog_acceptance import main as verify_engineering  # noqa: E402
from verify_catalog_release import trusted_release, verify  # noqa: E402


def read(path):
    return json.loads((ROOT / path).read_text())


def sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def completed_commits(task):
    marker = task["commit_lookup"]
    commits = git(
        "log", "--format=%H", "--fixed-strings", "--grep=" + marker
    ).splitlines()
    assert commits, "Missing completion commit: " + task["id"]
    for commit in commits:
        assert marker in git("show", "-s", "--format=%B", commit).splitlines()
        state = json.loads(git("show", commit + ":task.json"))
        assert (
            next(t for t in state["tasks"] if t["id"] == task["id"])["status"] == "done"
        )
    return commits


def verify_exit(pending_output=None):
    tasks = read("task.json")
    by_id = {t["id"]: t for t in tasks["tasks"]}
    assert len(by_id) == len(tasks["tasks"]) == 46
    current = by_id["MVP-0.3-T034"]
    assert current["status"] in {"in_progress", "done"}
    assert current["depends_on"] == ["MVP-0.3-T032", "MVP-0.3-T045", "MVP-0.3-T046"]
    assert all(by_id[dep]["status"] == "done" for dep in current["depends_on"])
    assert by_id["MVP-0.3-T033"]["status"] == "blocked"
    assert all(
        t["status"] == "done"
        for t in tasks["tasks"]
        if t["id"] not in {"MVP-0.3-T033", "MVP-0.3-T034"}
    )
    commits = {
        t["id"]: completed_commits(t) for t in tasks["tasks"] if t["status"] == "done"
    }
    for task in tasks["tasks"]:
        if task["status"] == "done":
            assert all(by_id[dep]["status"] == "done" for dep in task["depends_on"])

    protocol_path = "docs/acceptance/mvp-0.3-catalog-exit-protocol-20261003.json"
    plan = read(protocol_path)
    t033 = by_id["MVP-0.3-T033"]
    assert (
        hashlib.sha256(
            json.dumps(t033, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        == plan["t033_task_sha256"]
    )
    for name, digest in plan["protected_hashes"].items():
        assert sha(name) == digest, "Changed old T033/source evidence: " + name
    baseline = json.loads(git("show", plan["baseline_commit"] + ":task.json"))
    assert t033 == next(t for t in baseline["tasks"] if t["id"] == t033["id"])

    # This invokes only the frozen offline verifier, not its benchmark executors.
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        verify_engineering()
    engineering_metrics = json.loads(stream.getvalue().splitlines()[0])
    package_dir = ROOT / "data/course_catalog/linear-v1"
    digest, approval_path = trusted_release(
        package_dir, ROOT / "data/course_catalog/release-allowlist.json"
    )
    approval = verify(package_dir, digest, approval_path)
    assert approval["publishable"] and approval["reviewer"] == "Lee"
    authority = read("docs/acceptance/mvp-0.3-catalog-human-signoff-20261003.json")
    assert approval["manifest_digest"] == authority["manifest_digest"] == digest
    assert approval["reviewed_at"] == authority["recorded_at"]
    signed_verification = read(
        "docs/acceptance/mvp-0.3-catalog-signed-verification-20261003.json"
    )
    assert (
        sha(signed_verification["protocol"]) == signed_verification["protocol_sha256"]
    )
    assert sha(signed_verification["result"]) == signed_verification["result_sha256"]
    signed_plan = read(signed_verification["protocol"])
    for name, expected in signed_plan["code_hashes"].items():
        assert sha(name) == expected, "Changed signed-release code: " + name
    signed_result = read(signed_verification["result"])
    assert signed_result["passed"] and signed_result["pytest_exit_code"] == 0
    assert signed_result["manifest_digest"] == digest
    assert signed_result["approval"] == read(str(approval_path.relative_to(ROOT)))
    assert (
        signed_result["provider_requests"] == 0
        and signed_result["external_attempts"] == []
    )
    assert signed_verification["cumulative_requests"] == 2033
    assert len(signed_result["nodes"]) == 10
    assert sum(n["resource_count"] for n in signed_result["nodes"]) == 30
    assert sum(n["correct_count"] for n in signed_result["nodes"]) == 30
    assert len(signed_result["media"]) == 4
    ledger = read("docs/acceptance/mvp-0.3-t033-ledger-v27-qwen-repeat-20261002.json")
    assert ledger["call_limit"] == 2500
    assert ledger["frozen_maximum_cumulative_attempts_this_run"] == 2033
    assert ledger["halted"] == "CONCRETE_DEFECT_MISSED"

    links = []
    for name in [
        "README.md",
        "docs/DEPLOYMENT.md",
        "docs/ADR/README.md",
        "docs/acceptance/mvp-0.3-catalog-exit-20261003.md",
    ]:
        document = ROOT / name
        text = document.read_text()
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
            if "://" in target or target.startswith("#"):
                continue
            path = (document.parent / target.split("#", 1)[0]).resolve()
            assert path.is_file() or path == pending_output, (
                f"Missing documentation link: {name} -> {target}"
            )
            links.append({"document": name, "target": target})
    assert "catalog_only" in (ROOT / "docker-compose.yml").read_text()
    return {
        "task_id": current["id"],
        "scope": "catalog_only",
        "passed": True,
        "current_task_state": current["status"],
        "local_completion_commit": commits.get(current["id"]),
        "completed_commits": commits,
        "direct_dependencies": current["depends_on"],
        "engineering_metrics": engineering_metrics,
        "human_release": approval,
        "signed_result_sha256": sha(signed_verification["result"]),
        "protected_files_verified": len(plan["protected_hashes"]),
        "documentation_links": links,
        "t033_unchanged": True,
        "provider_requests": 0,
        "cumulative_requests": 2033,
        "request_limit": 2500,
        "new_database_browser_worker_runs": 0,
        "new_benchmark_runs": 0,
        "production_published": False,
        "phase1_started": False,
        "evidence_scope": "Frozen local working tree, not a clean-checkout or public deployment test",
        "exit_protocol_sha256": sha(protocol_path),
        "verifier_sha256": sha("scripts/verify_catalog_exit.py"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and args.output.exists():
        raise ValueError("Do not overwrite prior evidence")
    report = verify_exit(args.output.resolve() if args.output else None)
    if args.output:
        with args.output.open("x") as destination:
            destination.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "task_id",
                    "passed",
                    "current_task_state",
                    "local_completion_commit",
                    "protected_files_verified",
                    "provider_requests",
                    "cumulative_requests",
                    "new_benchmark_runs",
                    "production_published",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
