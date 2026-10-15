"""Run explicitly selected zero-Provider tests in a dedicated OM PostgreSQL database."""

import argparse
import subprocess
import sys
from pathlib import Path
from run_catalog_db_tests import test_environment

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--dynamic-mock-mode", action="store_true")
    parser.add_argument(
        "--roundtrip",
        action="store_true",
        help="Empty-database migration roundtrip; existing protected data will refuse downgrade",
    )
    parser.add_argument("tests", nargs="+")
    args = parser.parse_args()
    if not args.database.startswith("edumind_catalog_phase1_om"):
        parser.error("dedicated OM test database required")
    if any(not t.startswith("tests/test_") or ".." in t for t in args.tests):
        parser.error("explicit test files required")
    env = test_environment(args.database)
    env = {
        k: v
        for k, v in env.items()
        if not k.startswith(
            ("EDUMIND_CREDENTIAL", "EDUMIND_PROVIDER", "EDUMIND_REVIEWER")
        )
    }
    env["EDUMIND_PRODUCT_MODE"] = (
        "dynamic" if args.dynamic_mock_mode else "catalog_only"
    )
    commands = [["-m", "alembic", "upgrade", "head"]]
    if args.roundtrip:
        commands += [
            ["-m", "alembic", "downgrade", "0017_catalog_immutability"],
            ["-m", "alembic", "upgrade", "head"],
        ]
    commands.append(["-m", "pytest", "-q", *args.tests])
    for command in commands:
        subprocess.run(
            [sys.executable, *command], cwd=ROOT / "backend", env=env, check=True
        )
    print("Dedicated OM test run completed; no server configuration or .env loaded.")


if __name__ == "__main__":
    main()
