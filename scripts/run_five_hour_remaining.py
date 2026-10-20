"""Explicit continuation of six unrun cases; never reopen the stopped parent ledger."""

# ruff: noqa: E402
import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import run_five_hour_acceptance as parent
import acceptance_support.five_hour_runtime as kernel
from acceptance_support.five_hour_runtime import (
    read_json,
    require,
    write_once,
    private_directory,
)
from acceptance_support.qwen_review_budget import canonical, sha

ORDER = ["R03", "R04", "A01", "A02", "A03", "A04"]
PACKAGE = ROOT / "docs/acceptance/phase-1-five-hour-remaining-six-r01"
PRIVATE = ROOT / "local-materials/phase-1-five-hour-remaining-six-r01"
OLD_PACKAGE, OLD_PRIVATE = parent.PACKAGE, parent.PRIVATE


def verify():
    original, original_hash = parent.verify_package()
    stopped = read_json(OLD_PACKAGE / "terminal.json")
    require(
        sha((OLD_PRIVATE / "run.sqlite").read_bytes()) == stopped["ledger_sha256"],
        "PARENT_LEDGER_CHANGED",
    )
    old = kernel.RunLedger(OLD_PRIVATE / "run.sqlite", original_hash)
    parent.verify_prior_results(old)
    snapshot = old.snapshot()
    require(
        snapshot["run"][3] == "REQUIRED_CORE_CONDITION_UNREACHABLE"
        and len(snapshot["calls"]) == 10
        and [c[0] for c in snapshot["cases"] if c[1] == "pending"] == ORDER,
        "PARENT_UNRUN_SCOPE_CHANGED",
    )
    m = read_json(PACKAGE / "manifest.json")
    for name, expected in m["files"].items():
        path = ROOT / name
        require(
            path.resolve().is_relative_to(ROOT)
            and not path.is_symlink()
            and sha(path.read_bytes()) == expected,
            "CONTINUATION_FREEZE_CHANGED",
        )
    require(
        m["parent_execution_root"] == original_hash
        and m["order"] == ORDER
        and m["requests_max"] == 50
        and m["normal_requests"] == 34
        and m["shared_extra_requests"] == 16
        and m["preparation_t0_epoch"] == original["preparation_t0_epoch"],
        "CONTINUATION_SCOPE_CHANGED",
    )
    return m, sha(canonical(m)), original


def authorize():
    m, digest, original = verify()
    a = read_json(PACKAGE / "run-approval.json")
    require(
        a
        == dict(
            manifest_sha256=digest,
            source_user_message="继续剩余6项",
            reviewer="Lee",
            decision="continue_six_unrun_cases_without_reopening_parent",
            requests_max=50,
            previous_requests=10,
            combined_max=60,
            fees="uncapped",
            reset_clock=False,
        ),
        "EXPLICIT_CONTINUATION_APPROVAL_REQUIRED",
    )
    return m, digest, original


def configure():
    """A new process selects a new case table/directory, not a different model or policy.

    The kernel creates exactly these six pending rows. No old case is copied as a
    fabricated pass; no stopped ledger method is altered. Original verification
    always happens BEFORE this process-local selection. The shared evaluation
    run_id stays five-hour-r01 for the same sixteen-item logical set; the new root,
    ledger and artifact paths identify this independent continuation.
    """
    kernel.ORDER = list(ORDER)
    parent.ORDER = list(ORDER)
    parent.PRIVATE = PRIVATE


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command",
        choices=["check", "init", "run", "assess", "report", "stop", "browser"],
    )
    p.add_argument("--case", choices=ORDER)
    p.add_argument("--evaluation", type=Path)
    args = p.parse_args()
    if args.command == "check":
        m, digest, original = verify()
        print(
            json.dumps(
                dict(
                    manifest_sha256=digest,
                    order=ORDER,
                    parent_requests=10,
                    new_max=50,
                    normal=34,
                    original_halt_retained=True,
                    hard_deadline=original["hard_deadline"],
                    calls_in_this_command=0,
                )
            )
        )
        return
    m, digest, original = authorize()
    configure()
    if args.command == "browser":
        require(
            args.case is not None and args.case.startswith("A"),
            "GENERATED_CASE_REQUIRED",
        )
        import serve_five_hour_results as browser

        browser.PRIVATE = PRIVATE
        browser.authorize = lambda: (m, digest)
        sys.argv = ["serve_five_hour_results.py", "--case", args.case]
        browser.main()
        return
    private_directory(PRIVATE)
    with (PRIVATE / "process.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == "init":
            require(
                time.time() < m["preparation_t0_epoch"] + 16200,
                "ORIGINAL_DEADLINE_EXPIRED",
            )
            require(
                not (PRIVATE / "run.sqlite").exists(), "CONTINUATION_ALREADY_STARTED"
            )
            env = parent.isolated_environment()
            asyncio.run(
                parent.verify_database(env["EDUMIND_DATABASE_URL"], require_empty=True)
            )
            parent.load_keys(original["env_metadata"])
            write_once(PRIVATE / "credential-binding.json", original["env_metadata"])
            ledger = kernel.RunLedger(
                PRIVATE / "run.sqlite", digest, t0=m["preparation_t0_epoch"]
            )
            require(
                [r[0] for r in ledger.snapshot()["cases"]] == ORDER,
                "ONLY_SIX_PENDING_ROWS_REQUIRED",
            )
        else:
            ledger = kernel.RunLedger(PRIVATE / "run.sqlite", digest)
        if args.command == "run":
            require(args.case is not None, "CASE_REQUIRED")
            parent.verify_prior_results(ledger)
            env = parent.isolated_environment()
            url = env["EDUMIND_DATABASE_URL"]
            asyncio.run(parent.verify_database(url))
            keys = parent.load_keys(read_json(PRIVATE / "credential-binding.json"))
            ledger.start_case(args.case)
            directory = private_directory(PRIVATE / args.case)
            os.environ["EDUMIND_PRODUCT_MODE"] = "dynamic"
            try:
                result = asyncio.run(
                    parent.execute_case(args.case, ledger, directory, url, keys)
                )
                print(json.dumps(result))
            finally:
                os.environ.pop("EDUMIND_PRODUCT_MODE", None)
        elif args.command == "assess":
            require(
                args.case is not None and args.evaluation is not None,
                "ASSESSMENT_REQUIRED",
            )
            parent.apply_assessment(ledger, args.case, read_json(args.evaluation))
        elif args.command == "stop":
            ledger.stop("EXPLICIT_CONTINUATION_STOP")
        print(json.dumps(ledger.snapshot()))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Continuation failed closed; parent halt and all evidence retained.",
            file=sys.stderr,
        )
        sys.exit(1)
