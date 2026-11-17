"""Explicit isolated PG integration run, or strictly offline evidence verification."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/acceptance/phase-1.5-integration-t035/results.json"
GROUPS = [
    ("test_p15_free_course_integration.py", "t020"),
    ("test_free_course_scheduler.py", "t014"),
    ("test_free_course_recovery.py", "t015"),
    ("test_free_course_revision.py", "t016"),
    ("test_free_course_feedback.py", "t017"),
    ("test_free_course_answers.py", "t018"),
    ("test_free_course_evidence.py", "t019"),
    ("test_free_course_api.py", "t020"),
    ("test_free_course_tutor_context.py", "t043"),
    ("test_free_course_tutor_scheduler.py", "t043"),
    ("test_free_course_tutor_api.py", "t020"),
    ("test_free_course_records_api.py", "t020"),
    ("test_mastery_revision_api.py", "t020"),
    ("test_free_course_compatibility.py", "t021"),
    ("test_provider_connections_api.py", "t006"),
    ("test_model_preferences.py", "t006"),
    ("test_catalog_mode.py", "t006"),
    ("test_legacy_archives.py", "t006"),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def integrity():
    expected = {}
    for name in [
        "docs/ADR/0024-approval-20261021.json",
        "docs/ADR/0025-approval-20261021.json",
        "docs/ADR/0026-approval-20261022.json",
        "docs/design/phase-1.5-ui-approval-20261022.json",
        "docs/ADR/0027-approval-20261022.json",
        "docs/ADR/0028-approval-20261023.json",
    ]:
        a = json.loads((ROOT / name).read_text())
        expected[a["proposal_manifest"]] = a["proposal_manifest_sha256"]
        expected.update({f["path"]: f["sha256"] for f in a["files"]})
    historical = json.loads(
        (
            ROOT
            / "docs/acceptance/phase-1.5-compatibility-t021/baseline-integrity.json"
        ).read_text()
    )["sha256"]
    for path, value in {**expected, **historical}.items():
        assert sha(ROOT / path) == value, path
    return {"approved": len(expected), "historical": len(historical)}


def counts(xml):
    suites = ET.parse(xml).getroot()
    return {
        k: sum(int(suite.get(k, "0")) for suite in suites)
        for k in ["tests", "failures", "errors", "skipped"]
    }


def check():
    # No Docker, database, subprocess, imports of application settings, .env or network.
    data = json.loads(EVIDENCE.read_text())
    assert (
        data["real_provider_calls"] == 0 and data["production_mode"] == "catalog_only"
    )
    assert data["test_mode"] == "isolated dynamic fixtures only"
    assert data["transport"] == "synthetic FakeAdapter; real ASGI HTTP and PostgreSQL"
    assert data["integrity"] == integrity()
    assert [(g["test"], g["prefix"]) for g in data["groups"]] == GROUPS
    for group in data["groups"]:
        assert group["exit_code"] == 0 and group["counts"]["tests"] > 0
        assert all(group["counts"][k] == 0 for k in ["failures", "errors", "skipped"])
        assert group["database"].startswith(
            "edumind_catalog_p15_" + group["prefix"] + "_t035_"
        )
        for kind in ["xml", "log"]:
            path = Path(group[kind])
            assert path.is_relative_to(Path("/tmp/edumind-p15-t035-" + data["run_id"]))
            assert sha(path) == group[kind + "_sha256"], str(path)
        assert counts(Path(group["xml"])) == group["counts"]
        cases = ET.parse(group["xml"]).getroot().findall(".//testcase")
        assert len(cases) == group["counts"]["tests"] and not any(
            c.findall("failure") or c.findall("error") or c.findall("skipped")
            for c in cases
        )
    assert data["passed"] == sum(g["counts"]["tests"] for g in data["groups"])
    print(
        f"PASS offline exact evidence: {data['passed']} tests, {len(GROUPS)} fresh databases, Provider0/catalog_only, no calls made by --check"
    )


def run(run_id, output):
    if not re.fullmatch(r"r[0-9]{2}", run_id):
        raise ValueError("Numbered run required")
    if output != Path("/tmp/edumind-p15-t035-" + run_id):
        raise ValueError("Exact task-specific output path required")
    output.mkdir(exist_ok=False)
    import run_catalog_db_tests

    run_catalog_db_tests.CONTAINER = "edumind-phase1-t037-pg"
    result = {
        "run_id": run_id,
        "real_provider_calls": 0,
        "production_mode": "catalog_only",
        "test_mode": "isolated dynamic fixtures only",
        "transport": "synthetic FakeAdapter; real ASGI HTTP and PostgreSQL",
        "integrity": integrity(),
        "groups": [],
    }
    for i, (name, prefix) in enumerate(GROUPS):
        database = f"edumind_catalog_p15_{prefix}_t035_{run_id}_{i}"
        env = run_catalog_db_tests.test_environment(database)
        env = {
            k: v
            for k, v in env.items()
            if not k.startswith(
                ("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "EDUMIND_REVIEW_CANDIDATE")
            )
        }
        env["EDUMIND_PRODUCT_MODE"] = "catalog_only"
        # Some legacy HTTP modules have no migration fixture; initialize every fresh DB.
        migration = output / f"migration-{i}.log"
        with migration.open("w") as stream:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT / "backend",
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=90,
            )
        log = output / f"group-{i}.log"
        xml = output / f"group-{i}.xml"
        with log.open("w") as stream:
            process = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    f"backend/tests/{name}",
                    "-q",
                    "--tb=short",
                    "--junitxml=" + str(xml),
                ],
                cwd=ROOT,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=180,
            )
        group = dict(
            test=name,
            prefix=prefix,
            database=database,
            exit_code=process.returncode,
            counts=counts(xml),
            log=str(log),
            xml=str(xml),
            log_sha256=sha(log),
            xml_sha256=sha(xml),
        )
        result["groups"].append(group)
        (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
        print(name, group["counts"], flush=True)
        if process.returncode or any(
            group["counts"][k] for k in ["failures", "errors", "skipped"]
        ):
            raise SystemExit("Failed or skipped: inspect preserved exact raw evidence")
    result["passed"] = sum(g["counts"]["tests"] for g in result["groups"])
    EVIDENCE.parent.mkdir(exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, indent=2) + "\n")
    check()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--run", metavar="rNN")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.check:
        if args.output:
            parser.error("--check does not run or write output")
        check()
    else:
        if args.output is None:
            parser.error("--run requires --output")
        run(args.run, args.output)


if __name__ == "__main__":
    main()
