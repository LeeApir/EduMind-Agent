"""Queue migration/tests in a new isolated DB, synthetic dynamic fixtures, no Provider env."""

import json
import os
import re
import subprocess
import sys

from run_catalog_db_tests import ROOT, test_environment


def main() -> None:
    database = sys.argv[1]
    if not re.fullmatch(r"edumind_catalog_phase1_t0(?:19|20)_[a-z0-9_]{1,15}", database):
        raise ValueError("Dedicated queue database required")
    env = test_environment(database)
    env = {
        k: v
        for k, v in env.items()
        if not k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "EDUMIND_ANIMATION_BROKER"))
    }
    if os.getenv("EDUMIND_RUN_QUEUE_BROKER_TESTS") == "1":
        info = json.loads(
            subprocess.run(
                ["docker", "inspect", "edumind-phase1-queue-test-redis"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )[0]
        if info["Config"]["Labels"].get("edumind.test-only") != "phase1-queue":
            raise ValueError("Dedicated queue test broker label required")
        binding = info["NetworkSettings"]["Ports"]["6379/tcp"][0]
        if binding["HostIp"] != "127.0.0.1" or binding["HostPort"] != "15579":
            raise ValueError("Dedicated queue test broker loopback binding required")
        env["EDUMIND_TEST_QUEUE_BROKER"] = (
            "redis://publisher:synthetic_queue_test_only_password@127.0.0.1:15579/0"
        )
    # Legacy synthetic fixture targets are not catalog publications. This mode is
    # confined to the test subprocess; actual server/compose keep catalog_only.
    env["EDUMIND_PRODUCT_MODE"] = "dynamic"
    env["EDUMIND_ANIMATION_DISPATCH"] = "pg_poll"
    for command in [
        ["-m", "alembic", "upgrade", "head"],
        ["-m", "alembic", "downgrade", "0020_model_preferences"],
        ["-m", "alembic", "upgrade", "head"],
        ["-m", "pytest", "-q", "-rs", *sys.argv[2:]],
    ]:
        subprocess.run([sys.executable, *command], cwd=ROOT / "backend", env=env, check=True)
    print("Dedicated queue migration roundtrip/PG tests passed; Provider0")


if __name__ == "__main__":
    main()
