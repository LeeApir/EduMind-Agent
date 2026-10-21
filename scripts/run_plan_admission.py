"""Freeze/check the new run offline; activate/run require exact frozen-package activation."""

# ruff: noqa: E402
import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.five_hour_runtime import (
    private_directory,
    read_json,
    require,
    write_once,
)
from acceptance_support.luna_admission_gate import env_metadata
from acceptance_support.plan_admission_live import (
    DATABASE,
    execute,
    live_gateway,
    verify_database,
)
from acceptance_support.plan_admission_run import (
    Ledger,
    RUN_ID,
    check_assessment,
    schedule,
)
from acceptance_support.qwen_review_budget import canonical, sha
from prepare_plan_admission import BASE as PARENT, check as check_parent
from run_five_hour_acceptance import load_keys

PACKAGE = ROOT / "docs/acceptance/phase-1-plan-admission-execution-r02"
APPROVAL = ROOT / "docs/acceptance/phase-1-plan-admission-authorization-r01"
PRIVATE = ROOT / "local-materials/phase-1-plan-admission-execution-r02"
PARENT_HASH = "b99c08f657b084c849b36163339fe0526f484b40d7f76a991d8e99cca7653303"


def read(path):
    return read_json(path)


def slots():
    return schedule(read(PARENT / "index.json"))


def verify_authorization():
    require(
        sha((PARENT / "manifest.json").read_bytes()) == PARENT_HASH, "PARENT_CHANGED"
    )
    check_parent()  # Historical pending fields stay immutable; receipt below supplies current authority.
    a, h = (
        read(APPROVAL / "approval.json"),
        read(APPROVAL / "human-check-20261021.json"),
    )
    require(
        a["parent_manifest_sha256"] == PARENT_HASH
        and h["parent_manifest_sha256"] == PARENT_HASH
        and h["approval_sha256"] == sha((APPROVAL / "approval.json").read_bytes())
        and a["budget"]["executable_request_max"] == 59
        and a["timing"]["global_deadline_seconds"] == 18000
        and a["first_failure"]["stop"] is True
        and a["automatic_retries"] == 0
        and a["fallbacks"] == 0
        and h["signed_by"] == "Lee"
        and h["changes_reported"] is False,
        "APPROVAL_CHANGED",
    )
    expected = [x for x in read(PARENT / "index.json")["materials"] if "prelabel" in x]
    require(len(h["materials"]) == len(expected) == 16, "ALL_LABELS_REQUIRED")
    for x, y in zip(expected, h["materials"], strict=True):
        require(
            y["id"] == x["id"]
            and y["lane"] == x["lane"]
            and y["independent_signoff"] == "confirmed_Lee"
            and y["material_sha256"] == x["sha256"]
            and y["prelabel_sha256"] == sha(canonical(x["prelabel"])),
            "LABEL_SIGNATURE_CHANGED",
        )


def freeze():
    require(not (PACKAGE / "manifest.json").exists(), "FROZEN_PACKAGE_CANNOT_REWRITE")
    verify_authorization()
    validations = [
        read(PACKAGE / p) for p in ("offline-tests.json", "pg-integration.json")
    ]
    require(
        all(v["exit"] == 0 and v["provider_calls"] == 0 for v in validations),
        "ACTUAL_OFFLINE_VALIDATION_REQUIRED",
    )
    environment = read(PACKAGE / "environment-check.json")
    require(
        environment
        == dict(
            database=DATABASE,
            head="0033_learning_shared_budget",
            empty=True,
            provider_calls=0,
        ),
        "ISOLATION_PREFLIGHT_REQUIRED",
    )
    files = [ROOT / p for p in read(PARENT / "manifest.json")["files"]]
    files.extend(
        [
            ROOT / "scripts/run_plan_admission.py",
            ROOT / "scripts/acceptance_support/plan_admission_run.py",
            ROOT / "scripts/acceptance_support/plan_admission_live.py",
            ROOT / "scripts/tests/test_plan_admission_execution.py",
        ]
    )
    files.extend(p for p in PACKAGE.rglob("*") if p.is_file())
    files.extend(p for p in APPROVAL.iterdir() if p.is_file())
    files.append(ROOT / ".gitattributes")
    files.extend(
        p
        for p in (
            ROOT / "docs/acceptance/phase-1-plan-admission-execution-r01"
        ).iterdir()
        if p.is_file()
    )
    manifest = dict(
        kind="PLAN_ADMISSION_EXECUTION_FROZEN_NOT_ACTIVATED",
        run_id=RUN_ID,
        parent_manifest_sha256=PARENT_HASH,
        branch=subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        slots=slots(),
        requests_max=59,
        wall_seconds=18000,
        first_failure_stop=True,
        automatic_retries=0,
        fallbacks=0,
        database=DATABASE,
        env_metadata=env_metadata(ROOT / ".env"),
        files={
            str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(set(files))
        },
        activation_required=True,
        provider_calls=0,
        T040="blocked",
        holdout="sealed_not_used",
    )
    write_once(PACKAGE / "manifest.json", manifest)


def verify():
    verify_authorization()
    m = read(PACKAGE / "manifest.json")
    require(
        m["kind"] == "PLAN_ADMISSION_EXECUTION_FROZEN_NOT_ACTIVATED"
        and m["slots"] == slots()
        and m["requests_max"] == 59
        and m["wall_seconds"] == 18000
        and m["first_failure_stop"] is True
        and m["automatic_retries"] == m["fallbacks"] == 0
        and m["database"] == DATABASE,
        "EXECUTION_CONTRACT_CHANGED",
    )
    require(
        m["branch"]
        == subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True
        ).strip(),
        "BRANCH_CHANGED",
    )
    require(
        m["env_metadata"] == env_metadata(ROOT / ".env"), "CREDENTIAL_METADATA_CHANGED"
    )
    for name, h in m["files"].items():
        p = ROOT / name
        require(
            p.resolve().is_relative_to(ROOT)
            and p.is_file()
            and not p.is_symlink()
            and sha(p.read_bytes()) == h,
            "FROZEN_FILE_CHANGED",
        )
    return sha((PACKAGE / "manifest.json").read_bytes())


def activated(manifest_hash):
    # Created only after explicit approval to start this concrete frozen executor.
    a = read(PACKAGE / "activation.json")
    require(
        a
        == dict(
            manifest_sha256=manifest_hash,
            decision="activate_plan_admission_execution_r02",
            reviewer="Lee",
            source_user_message=a.get("source_user_message"),
        )
        and bool(a["source_user_message"]),
        "EXACT_ACTIVATION_REQUIRED",
    )


def isolated_environment():
    import run_catalog_db_tests as isolated

    isolated.CONTAINER = "edumind-phase1-t037-pg"
    return isolated.test_environment(DATABASE)


def case_directory(spec):
    return private_directory(PRIVATE / spec["slot_id"].replace(":", "_"))


def verify_artifacts(directory, result):
    for name, h in result["artifact_hashes"].items():
        p = directory / name
        require(
            p.resolve().is_relative_to(directory.resolve())
            and not p.is_symlink()
            and sha(p.read_bytes()) == h,
            "RESULT_ARTIFACT_CHANGED",
        )


async def run_slot(ledger, spec, manifest_hash, keys, *, database_url=None):
    directory = case_directory(spec)
    case = read(ROOT / spec["material"])
    c = dict(ledger=ledger, spec=spec, directory=directory, call_ids=[], calls=[])
    ledger.start(spec["slot_id"])
    transports = []
    try:
        gateway, transports = live_gateway(c, keys=keys)
        result = await execute(spec, case, gateway, database_url=database_url)
        evidence = dict(
            material=case,
            result=result,
            calls=c["calls"],
            review_sources=c.get("review_sources", {}),
        )
        evidence["parsed_calls"] = [
            read(directory / f"{n:02}-parsed.json") for n in c["call_ids"]
        ]
        evidence["logical_requests"] = [
            read(directory / f"{n:02}-logical.json") for n in c["call_ids"]
        ]
        evidence["artifact_hashes"] = {
            p.name: sha(p.read_bytes()) for p in directory.iterdir() if p.is_file()
        }
        write_once(directory / "result.json", evidence)
        ledger.finish(spec["slot_id"], sha(canonical(evidence)))
        # Known technical/route/label failures stop before human gate. Semantic pass never automatic.
        label = next(
            (
                x.get("prelabel")
                for x in read(PARENT / "index.json")["materials"]
                if x["id"] == spec["case_id"] and x["lane"] == spec["lane"]
            ),
            None,
        )
        if label:
            if spec["lane"] == "plan_review":
                check = result["plan_check"]
                verdict = check["model_result"]["verdict"]
                route = check["server_assessment"]["route"]
                good = verdict in label["model_verdicts"] and (
                    route in ("needs_human", "reject")
                    if label["server_route"] == "needs_human_or_reject"
                    else route == label["server_route"]
                )
            else:
                good = (
                    result["review"]["result"]["verdict"] == label["expected_verdict"]
                    and result["review"]["local_routing"]["verdict"]
                    == label["expected_verdict"]
                )
            if not good:
                ledger.stop("FROZEN_LABEL_OR_ROUTE_MISMATCH")
        if spec["lane"] == "full_pipeline" and result["course_state"] != "completed":
            ledger.stop("FULL_PIPELINE_NOT_AUTOMATICALLY_COMPLETED")
    except BaseException:
        ledger.stop("FIRST_EXECUTION_FAILURE")
        if not (directory / "failure-summary.json").exists():
            write_once(
                directory / "failure-summary.json",
                dict(
                    kind="execution_failed",
                    call_ids=c["call_ids"],
                    artifact_hashes={
                        p.name: sha(p.read_bytes())
                        for p in directory.iterdir()
                        if p.is_file()
                    },
                    detail="No retry. Inspect private receipts and isolated DB; untrusted exception text withheld.",
                ),
            )
        raise
    finally:
        for transport in transports:
            await transport.aclose()


def assess(ledger, spec, value, manifest_hash):
    directory = case_directory(spec)
    result = read(directory / "result.json")
    state = next(x for x in ledger.snapshot()["cases"] if x[0] == spec["slot_id"])
    require(
        state[2] == "awaiting_human" and state[4] == sha(canonical(result)),
        "RESULT_BINDING_CHANGED",
    )
    verify_artifacts(directory, result)
    passed = check_assessment(
        value,
        schema=read(PARENT / "evaluation.schema.json"),
        spec=spec,
        manifest_hash=manifest_hash,
        evidence=result,
    )
    digest = write_once(directory / "evaluation.json", value)
    ledger.assess(spec["slot_id"], digest, passed)


def verify_prior(ledger):
    for row in ledger.snapshot()["cases"]:
        if row[2] == "passed":
            spec = next(x for x in slots() if x["slot_id"] == row[0])
            directory = case_directory(spec)
            result = read(directory / "result.json")
            value = read(directory / "evaluation.json")
            require(
                row[4] == sha(canonical(result)) and row[5] == sha(canonical(value)),
                "PRIOR_ASSESSMENT_CHANGED",
            )
            verify_artifacts(directory, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "freeze",
            "check",
            "prepare-db",
            "activate",
            "run",
            "assess",
            "report",
            "stop",
        ],
    )
    parser.add_argument("--slot", choices=[x["slot_id"] for x in slots()])
    parser.add_argument("--evaluation", type=Path)
    args = parser.parse_args()
    if args.action == "prepare-db":
        verify_authorization()
        require(
            not (PRIVATE / "run.sqlite").exists(),
            "NO_DATABASE_PREPARATION_AFTER_ACTIVATION",
        )
        env = isolated_environment()
        for name in list(env):
            if name.endswith("API_KEY") or name.startswith("EDUMIND_PROVIDER"):
                env.pop(name, None)
        completed = subprocess.run(
            [
                str(ROOT / "backend/.venv/bin/python"),
                "-m",
                "alembic",
                "upgrade",
                "head",
            ],
            cwd=ROOT / "backend",
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        require(completed.returncode == 0, "ISOLATED_MIGRATION_FAILED")
        asyncio.run(verify_database(env["EDUMIND_DATABASE_URL"], empty=True))
        if not (PACKAGE / "environment-check.json").exists():
            require(
                not (PACKAGE / "manifest.json").exists(), "FROZEN_PACKAGE_CANNOT_EXTEND"
            )
            write_once(
                PACKAGE / "environment-check.json",
                dict(
                    database=DATABASE,
                    head="0033_learning_shared_budget",
                    empty=True,
                    provider_calls=0,
                ),
            )
        print(
            json.dumps(
                dict(database=DATABASE, empty=True, provider_calls=0, activated=False)
            )
        )
        return
    if args.action == "freeze":
        freeze()
    manifest_hash = verify()
    if args.action in ("check", "freeze"):
        active = (PRIVATE / "run.sqlite").exists()
        print(
            json.dumps(
                dict(
                    manifest_sha256=manifest_hash,
                    slots=29,
                    requests_max=59,
                    wall_seconds=18000,
                    labels_signed=16,
                    activated=active,
                    provider_calls=0 if not active else None,
                    execution_report="use report after activation",
                    T040="blocked",
                )
            )
        )
        return
    activated(manifest_hash)
    private_directory(PRIVATE)
    with (PRIVATE / "process.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "activate":
            require(not (PRIVATE / "run.sqlite").exists(), "NO_SECOND_ACTIVATION")
            # Check fresh isolated DB and credential availability before starting the five-hour clock.
            env = isolated_environment()
            asyncio.run(verify_database(env["EDUMIND_DATABASE_URL"], empty=True))
            load_keys(read(PACKAGE / "manifest.json")["env_metadata"])
            ledger = Ledger(
                PRIVATE / "run.sqlite", manifest_hash, slots(), activate=True
            )
        else:
            ledger = Ledger(PRIVATE / "run.sqlite", manifest_hash, slots())
        if args.action == "run":
            require(args.slot is not None, "SLOT_REQUIRED")
            verify_prior(ledger)
            spec = next(s for s in slots() if s["slot_id"] == args.slot)
            url = None
            if spec["lane"] == "full_pipeline":
                env = isolated_environment()
                url = env["EDUMIND_DATABASE_URL"]
                asyncio.run(verify_database(url, empty=True))
            keys = load_keys(read(PACKAGE / "manifest.json")["env_metadata"])
            prior_mode = os.environ.get("EDUMIND_PRODUCT_MODE")
            try:
                if spec["lane"] == "full_pipeline":
                    os.environ["EDUMIND_PRODUCT_MODE"] = "dynamic"
                asyncio.run(
                    run_slot(ledger, spec, manifest_hash, keys, database_url=url)
                )
            finally:
                if prior_mode is None:
                    os.environ.pop("EDUMIND_PRODUCT_MODE", None)
                else:
                    os.environ["EDUMIND_PRODUCT_MODE"] = prior_mode
        elif args.action == "assess":
            require(
                args.slot is not None and args.evaluation is not None,
                "SIGNED_EVALUATION_REQUIRED",
            )
            spec = next(s for s in slots() if s["slot_id"] == args.slot)
            assess(ledger, spec, read(args.evaluation), manifest_hash)
        elif args.action == "stop":
            ledger.stop("EXPLICIT_USER_STOP")
        print(json.dumps(ledger.snapshot()))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Admission command failed closed; no automatic retry, fallback, or old-run reopening.",
            file=sys.stderr,
        )
        sys.exit(1)
