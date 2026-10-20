"""Prepare and verify only allowlisted isolated PostgreSQL; zero Provider calls."""

import argparse
import asyncio
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", required=True)
    parser.parse_args()
    from run_five_hour_acceptance import isolated_environment, verify_database, DATABASE
    import run_catalog_db_tests as isolated

    env = isolated_environment()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=env,
        check=True,
        capture_output=True,
    )
    asyncio.run(verify_database(env["EDUMIND_DATABASE_URL"], require_empty=True))
    # The real-run DB remains empty. All scripted candidate rows live in a different DB.
    checks_db = f"edumind_catalog_fh_check_{int(time.time())}"
    checks = isolated.test_environment(checks_db)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env=checks,
        check=True,
        capture_output=True,
    )
    checks["EDUMIND_FIVE_HOUR_TEST_URL"] = checks["EDUMIND_DATABASE_URL"]
    checks["PYTHONPATH"] = str(ROOT / "backend")
    # Run only affected controls and existing publication/ownership/HTTP boundaries.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "scripts/tests/test_five_hour_execution.py",
            "scripts/tests/test_five_hour_materials.py",
            "backend/tests/test_hybrid_learning_publication.py",
            "backend/tests/test_teaching_node_operations.py",
        ],
        cwd=ROOT,
        env=checks,
        text=True,
        capture_output=True,
    )
    evidence_dir = ROOT / "docs/acceptance/phase-1-five-hour-execution-r01"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output_path = evidence_dir / ("offline-checks-" + str(int(time.time())) + ".json")
    # Database DSNs and credentials must never be part of the persisted pytest log.
    output = result.stdout + result.stderr
    for secret in [checks["EDUMIND_DATABASE_URL"], env["EDUMIND_DATABASE_URL"]]:
        output = output.replace(secret, "[REDACTED_TEST_DATABASE_URL]")
    output = re.sub(
        r"postgresql(?:\+asyncpg)?://[^\s'\"<>]+",
        "[REDACTED_TEST_DATABASE_URL]",
        output,
    )
    output_path.write_text(
        json.dumps(
            {
                "output": output,
                "sha256_of_redacted_utf8_output": hashlib.sha256(
                    output.encode()
                ).hexdigest(),
                "credential_redaction": "database URL only; output otherwise retained losslessly",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    report = dict(
        database=DATABASE,
        test_database=checks_db,
        loopback="127.0.0.1:15437",
        migration="0031_teaching_context",
        real_provider_calls=0,
        new_c_compiled_or_executed=False,
        actual_model_results=0,
        pytest_exit=result.returncode,
        pytest_evidence=str(output_path.relative_to(ROOT)),
        production_environment_mutated=False,
        public_server_started=False,
        cleanup="isolated scripted test DB retained for audit; no production database accessed",
    )
    (evidence_dir / "environment-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report))
    if result.returncode:
        sys.exit(result.returncode)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(
            "Isolated environment verification failed; no configuration values printed.",
            file=sys.stderr,
        )
        sys.exit(1)
