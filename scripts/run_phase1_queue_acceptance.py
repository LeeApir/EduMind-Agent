"""Run frozen T036 fault contracts in a fresh test database, never overwrite evidence."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs/acceptance/phase-1-queue-v1/protocol.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"r[0-9]{2}", args.run_id):
        raise ValueError("A dedicated numbered acceptance run is required")
    plan = json.loads(PROTOCOL.read_text())
    for name, expected in plan["code_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen queue acceptance source changed: " + name)
    output = ROOT / "local-materials/phase-1-t036" / args.run_id
    output.mkdir(parents=True, exist_ok=False)
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL"))
    }
    environment.update(EDUMIND_RUN_QUEUE_BROKER_TESTS="1", EDUMIND_DOCKER_TESTS="1")
    report = {
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "run_id": args.run_id,
        "provider_requests": 0,
        "passed": False,
        "complete_phase_acceptance": False,
    }
    with (output / "fault-tests.log").open("wb") as log:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/run_queue_storage_tests.py",
                "edumind_catalog_phase1_t036_" + args.run_id,
                *plan["fault_test_files"],
                "--junitxml=" + str(output / "fault-tests.xml"),
            ],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=1200,
            check=False,
        )
    report["exit_code"] = result.returncode
    if (output / "fault-tests.xml").exists():
        suites = ET.parse(output / "fault-tests.xml").getroot()
        report["counts"] = {
            key: sum(int(suite.get(key, "0")) for suite in suites)
            for key in ("tests", "failures", "errors", "skipped")
        }
        report["passed"] = result.returncode == 0 and report["counts"]["skipped"] == 0
    (output / "fault-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
