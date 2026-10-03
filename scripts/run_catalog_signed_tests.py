"""Validate an actual signed release in a fresh, dedicated database; never deploy."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from run_catalog_db_tests import ROOT, test_environment


def main():
    # New DB per run prevents a previously withdrawn immutable version from being reused.
    database = "edumind_catalog_signed_" + uuid4().hex[:12]
    output = Path(os.environ["EDUMIND_CATALOG_SIGNED_RESULT"]).resolve()
    if output.exists():
        raise ValueError("Never overwrite an existing acceptance result")
    env = test_environment(database)
    env.update(
        EDUMIND_PRODUCT_MODE="catalog_only", EDUMIND_CATALOG_SIGNED_RESULT=str(output)
    )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        check=True,
    )
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_catalog_signed_release.py",
            "tests/test_catalog_release_preflight.py",
        ],
        cwd=ROOT / "backend",
        env=env,
    )
    result = (
        json.loads(output.read_text())
        if output.exists()
        else {
            "checks": [],
            "provider_requests": 0,
            "database": database,
        }
    )
    result.update(pytest_exit_code=run.returncode, production_published=False)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    raise SystemExit(run.returncode)


if __name__ == "__main__":
    main()
