"""Reopen T107's fixed local PG/API/Vue development workspace; never read .env."""

import argparse
import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/tmp/edumind-t107")


def environment():
    import run_catalog_db_tests as database

    database.CONTAINER = "edumind-phase1-t037-pg"
    raw = database.test_environment("edumind_catalog_p15_t107_dev")
    env = {
        key: raw[key]
        for key in (
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "TMPDIR",
            "EDUMIND_DATABASE_URL",
            "EDUMIND_TEST_DATABASE_URL",
        )
        if key in raw
    }
    env.update(
        PYTHONPATH=str(ROOT / "backend"),
        EDUMIND_PRODUCT_MODE="dynamic",
        EDUMIND_API_PROXY_TARGET="http://127.0.0.1:8177",
    )
    WORK.mkdir(exist_ok=True)
    WORK.chmod(0o700)
    path = WORK / "env.json"
    path.write_text(json.dumps(env))
    path.chmod(0o600)
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Check test-only PG and apply migration, no model/owner creation",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start actual loopback app and Vue; leave them running for evaluation",
    )
    parser.add_argument(
        "--import-owner",
        type=UUID,
        help="Import both fixed courses for an existing browser owner",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Actual PG/API and browser regression using disposable anonymous owners",
    )
    parser.add_argument(
        "--check-migration",
        action="store_true",
        help="Verify isolated empty roundtrip and refusal to discard replay audit",
    )
    args = parser.parse_args()
    if not any(
        (args.prepare, args.start, args.import_owner, args.test, args.check_migration)
    ):
        parser.error("Choose at least one action")
    env = environment()
    python = str(ROOT / "backend/.venv/bin/python")
    if args.prepare:
        subprocess.run(
            [python, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            env=env,
            check=True,
        )
    if args.start:
        import socket

        for port in (8177, 5197):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    parser.error(
                        f"Port {port} is already in use; keep existing service or stop it explicitly"
                    )
        for name, command, cwd in [
            (
                "api",
                [python, str(ROOT / "scripts/head_course_replay.py"), "--serve"],
                ROOT,
            ),
            (
                "web",
                [
                    shutil.which("pnpm"),
                    "dev",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5197",
                    "--strictPort",
                ],
                ROOT / "web",
            ),
        ]:
            with (WORK / f"{name}.log").open("a") as log:
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            (WORK / f"{name}.pid").write_text(str(process.pid))
        print(
            "Development application: http://127.0.0.1:5197 (API 8177); no Provider/worker"
        )
    if args.import_owner:
        for slot in ("C01", "C02"):
            subprocess.run(
                [
                    python,
                    str(ROOT / "scripts/head_course_replay.py"),
                    "--import-case",
                    slot,
                    "--owner",
                    str(args.import_owner),
                ],
                env=env,
                check=True,
            )
    if args.test:
        for command, cwd, log in [
            (
                [python, "-m", "pytest", "-q", "tests/test_head_course_replay.py"],
                ROOT / "backend",
                "pg-tests.log",
            ),
            (
                [
                    python,
                    str(ROOT / "scripts/check_head_course_replay_browser.py"),
                    "--output",
                    str(WORK / "browser"),
                ],
                ROOT,
                "browser-run.log",
            ),
        ]:
            with (WORK / log).open("w") as handle:
                subprocess.run(
                    command,
                    cwd=cwd,
                    env=env,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    check=True,
                )
        print("PASS actual PG/API/browser. Evidence: /tmp/edumind-t107")
    if args.check_migration:
        sys.path.insert(0, str(ROOT / "backend"))
        from sqlalchemy import text
        from app.core.database import create_database_engine
        import run_catalog_db_tests as database

        async def snapshot():
            engine = create_database_engine(env["EDUMIND_DATABASE_URL"])
            try:
                async with engine.connect() as db:
                    row = (
                        await db.execute(
                            text(
                                "SELECT count(*),md5(coalesce(string_agg(id::text||response_digest||"
                                "origin_type||sent_attempts::text,',' ORDER BY id),'')) "
                                "FROM free_course_scene_generation_results"
                            )
                        )
                    ).one()
                    return dict(rows=row[0], digest=row[1])
            finally:
                await engine.dispose()

        before = asyncio.run(snapshot())
        result = subprocess.run(
            [python, "-m", "alembic", "downgrade", "0048_free_course_tutor_events"],
            cwd=ROOT / "backend",
            env=env,
            capture_output=True,
            text=True,
        )
        (WORK / "migration-refusal.log").write_text(result.stdout + result.stderr)
        assert (
            result.returncode != 0
            and "Replay audit exists; retain origin" in result.stderr
        )
        after = asyncio.run(snapshot())
        assert before == after
        empty_database = database.test_environment("edumind_catalog_p15_t107_migration")
        empty = {
            **env,
            **{
                key: empty_database[key]
                for key in ("EDUMIND_DATABASE_URL", "EDUMIND_TEST_DATABASE_URL")
            },
        }
        for command in [
            ["upgrade", "head"],
            ["downgrade", "0048_free_course_tutor_events"],
            ["upgrade", "head"],
        ]:
            subprocess.run(
                [python, "-m", "alembic", *command],
                cwd=ROOT / "backend",
                env=empty,
                check=True,
            )
        (WORK / "migration-results.json").write_text(
            json.dumps(
                dict(
                    empty_upgrade_downgrade_upgrade=True,
                    replay_data_downgrade_refused=True,
                    before=before,
                    after=after,
                ),
                indent=2,
            )
            + "\n"
        )
        print("PASS migration roundtrip and preservation of replay audit")


if __name__ == "__main__":
    main()
