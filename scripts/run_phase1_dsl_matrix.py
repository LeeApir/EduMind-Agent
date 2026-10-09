"""Execute fixed queue matrix in a fresh dedicated database and media namespace."""

import argparse
import hashlib
import json
import re
import subprocess
import sys

from run_catalog_db_tests import ROOT
from run_phase1_dsl_safety import isolated_environment

PLAN = ROOT / "docs/acceptance/phase-1-dsl-v1/matrix-protocol.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"r[0-9]{2}", args.run_id):
        raise ValueError("Dedicated numbered run required")
    plan = json.loads(PLAN.read_text())
    for name, digest in plan["code_sha256"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Frozen source changed: " + name)
    output = ROOT / "local-materials/phase-1-t037" / ("matrix-" + args.run_id)
    output.mkdir(parents=True, exist_ok=False)
    (output / "matrix-protocol.json").write_bytes(PLAN.read_bytes())
    env = isolated_environment("edumind_catalog_phase1_t037_matrix_" + args.run_id)
    env = {
        k: v
        for k, v in env.items()
        if not k.startswith(
            ("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "EDUMIND_ANIMATION_BROKER")
        )
    }
    info = json.loads(
        subprocess.run(
            ["docker", "inspect", "edumind-phase1-queue-test-redis"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
    )[0]
    if info["Config"]["Labels"].get("edumind.test-only") != "phase1-queue":
        raise ValueError("Dedicated broker required")
    binding = info["NetworkSettings"]["Ports"]["6379/tcp"][0]
    if binding != {"HostIp": "127.0.0.1", "HostPort": "15579"}:
        raise ValueError("Fixed test loopback broker required")
    env.update(
        EDUMIND_PRODUCT_MODE="dynamic",
        EDUMIND_ANIMATION_DISPATCH="celery",
        EDUMIND_ANIMATION_BROKER_URL=(
            "redis://publisher:synthetic_queue_test_only_password@127.0.0.1:15579/0"
        ),
        EDUMIND_QUEUE_MATRIX_OUTPUT=str(output),
    )
    with (output / "runner.log").open("wb") as log:
        for command in (
            ["-m", "alembic", "upgrade", "head"],
            ["-m", "tests.dsl_acceptance_matrix"],
        ):
            subprocess.run(
                [sys.executable, *command],
                cwd=ROOT / "backend",
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=2400,
            )
    print("Fixed queue matrix completed; evidence: " + str(output))


if __name__ == "__main__":
    main()
