"""Reproduce isolated PostgreSQL + MockHTTP tests. Never reads Provider credentials."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_catalog_db_tests as database  # noqa: E402


def main():
    database.CONTAINER = "edumind-phase1-t037-pg"
    try:
        env = database.test_environment("edumind_catalog_qwen_review_20261017")
    except Exception:
        print("Dedicated test PostgreSQL preparation failed; no Provider calls.")
        return 2
    python = str(ROOT / "backend/.venv/bin/python")
    result = subprocess.run(
        [python, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
    )
    print("Isolated PostgreSQL migration head:", result.returncode, flush=True)
    if result.returncode:
        return result.returncode
    return subprocess.run(
        [
            python,
            "-m",
            "pytest",
            "-q",
            "scripts/tests/test_qwen_review_execution.py",
            "scripts/tests/test_qwen_review_attempt.py",
            "scripts/tests/test_qwen_review_budget.py",
            "backend/tests/test_provider_connection_gateway.py",
            "backend/tests/test_phase1_dynamic_gate.py",
        ],
        cwd=ROOT,
        env=env,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
