"""Frozen T037 contracts; one new PG database per file, real Docker, no Provider env."""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET

from run_catalog_db_tests import ROOT

PLAN = ROOT / "docs/acceptance/phase-1-dsl-v1/safety-protocol.json"


def isolated_environment(database):
    source = (
        "import sys,json;sys.path.insert(0,'scripts');"
        "from run_catalog_db_tests import test_environment;"
        "print(json.dumps(test_environment(sys.argv[1])))"
    )
    safe = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL"))
    }
    child = subprocess.Popen(
        [sys.executable, "-c", source, database],
        cwd=ROOT,
        env=safe,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        payload, _ = child.communicate(timeout=20)
        if child.returncode:
            raise RuntimeError("Dedicated database initialization failed")
        # Credentials stay exclusively in captured process memory and child environment.
        return json.loads(payload)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.communicate(timeout=5)
        raise RuntimeError("Dedicated database initialization timed out") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"r[0-9]{2}", args.run_id):
        raise ValueError("Dedicated numbered run required")
    plan = json.loads(PLAN.read_text())
    for path, digest in plan["code_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    output = ROOT / "local-materials/phase-1-t037" / ("safety-" + args.run_id)
    output.mkdir(parents=True, exist_ok=False)
    (output / "safety-protocol.json").write_bytes(PLAN.read_bytes())
    groups = []
    for index, filename in enumerate(plan["test_files"]):
        # The existing migration refusal intentionally accepts only its historical
        # T025 test namespace. This is still a brand-new T037-dedicated database.
        prefix = (
            "t025_t037" if filename.endswith("test_animation_dsl_review.py") else "t037"
        )
        database = f"edumind_catalog_phase1_{prefix}_{args.run_id}_{index:02}"
        env = isolated_environment(database)
        env.update(EDUMIND_PRODUCT_MODE="dynamic", EDUMIND_DOCKER_TESTS="1")
        xml = output / f"group-{index:02}.xml"
        with (output / f"group-{index:02}.log").open("wb") as log:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT / "backend",
                env=env,
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=60,
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-rs",
                    filename,
                    "--junitxml=" + str(xml),
                ],
                cwd=ROOT / "backend",
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=1200,
                check=False,
            )
        suites = ET.parse(xml).getroot()
        counts = {
            key: sum(int(suite.get(key, "0")) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        groups.append(
            {
                "file": filename,
                "database": database,
                "counts": counts,
                "exit_code": result.returncode,
            }
        )
        print(filename, counts, flush=True)
    counts = {
        key: sum(group["counts"][key] for group in groups)
        for key in ("tests", "failures", "errors", "skipped")
    }
    report = {
        "protocol_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
        "provider_requests": 0,
        "counts": counts,
        "groups": groups,
        "passed": all(group["exit_code"] == 0 for group in groups)
        and counts["skipped"] == 0,
        "full_t037_complete": False,
    }
    (output / "safety-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
