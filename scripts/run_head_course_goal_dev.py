"""Reproduce only T108 local development lifecycle; no workers, Provider or .env."""

import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/tmp/edumind-t108")


def environment(database_name="edumind_catalog_p15_t108_dev"):
    import run_catalog_db_tests as database

    database.CONTAINER = "edumind-phase1-t037-pg"
    raw = database.test_environment(database_name)
    env = {
        k: raw[k]
        for k in (
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "TMPDIR",
            "EDUMIND_DATABASE_URL",
            "EDUMIND_TEST_DATABASE_URL",
        )
        if k in raw
    }
    env.update(
        PYTHONPATH=str(ROOT / "backend") + ":" + str(ROOT),
        EDUMIND_PRODUCT_MODE="dynamic",
        EDUMIND_HEAD_GOAL_DEVELOPMENT="1",
        EDUMIND_API_PROXY_TARGET="http://127.0.0.1:8178",
    )
    WORK.mkdir(exist_ok=True)
    WORK.chmod(0o700)
    path = WORK / "env.json"
    path.write_text(json.dumps(env))
    path.chmod(0o600)
    return env


def main():
    global WORK
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--profile", choices=["t108", "fixed"], default="t108")
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--start", action="store_true")
    p.add_argument("--test", action="store_true")
    p.add_argument("--check-migration", action="store_true")
    a = p.parse_args()
    if not any((a.prepare, a.start, a.test, a.check_migration)):
        p.error("Choose action")
    if a.profile == "fixed":
        if a.check_migration or a.test:
            p.error("Use the T111 checks listed in its execution package")
        WORK = Path("/tmp/edumind-t111-live")
    env = environment(
        "edumind_catalog_p15_t108_t111_live"
        if a.profile == "fixed"
        else "edumind_catalog_p15_t108_dev"
    )
    python = str(ROOT / "backend/.venv/bin/python")
    if a.prepare:
        subprocess.run(
            [python, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            env=env,
            check=True,
        )
    if a.start:
        for port in (8178, 5198):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    p.error(f"Port {port} already in use")
        for name, cmd, cwd in [
            (
                "api",
                [python, str(ROOT / "scripts/head_course_goal.py"), "--serve"],
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
                    "5198",
                    "--strictPort",
                ],
                ROOT / "web",
            ),
        ]:
            with (WORK / f"{name}.log").open("a") as log:
                proc = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            (WORK / f"{name}.pid").write_text(str(proc.pid))
        print(
            f"{a.profile} development entry http://127.0.0.1:5198; API8178; zero Provider/worker"
        )
    if a.check_migration:
        import run_catalog_db_tests as database

        database.CONTAINER = "edumind-phase1-t037-pg"
        raw = database.test_environment("edumind_catalog_p15_t108_migration")
        migration_env = dict(
            env,
            EDUMIND_DATABASE_URL=raw["EDUMIND_DATABASE_URL"],
            EDUMIND_TEST_DATABASE_URL=raw["EDUMIND_TEST_DATABASE_URL"],
        )
        for revision in ("head", "0049_head_course_replay", "head"):
            command = (
                "downgrade" if revision == "0049_head_course_replay" else "upgrade"
            )
            subprocess.run(
                [python, "-m", "alembic", command, revision],
                cwd=ROOT / "backend",
                env=migration_env,
                check=True,
                capture_output=True,
            )
        refusal = subprocess.run(
            [python, "-m", "alembic", "downgrade", "0049_head_course_replay"],
            cwd=ROOT / "backend",
            env=env,
            text=True,
            capture_output=True,
        )
        if (
            refusal.returncode == 0
            or "New generation audit exists" not in refusal.stderr
        ):
            raise RuntimeError("Audit downgrade was not refused")
        (WORK / "migration-refusal.txt").write_text(refusal.stdout + refusal.stderr)
        (WORK / "migration-result.json").write_text(
            json.dumps(
                dict(
                    empty_upgrade_down_upgrade=True,
                    audit_downgrade_refused=True,
                    provider_calls=0,
                )
            )
            + "\n"
        )
        print("Migration empty roundtrip and existing new audit refusal passed.")
    if a.test:
        subprocess.run(
            [python, "-m", "pytest", "-q", "tests/test_head_course_goal.py"],
            cwd=ROOT / "backend",
            env=env,
            check=True,
        )


if __name__ == "__main__":
    main()
