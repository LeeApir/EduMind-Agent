"""Reproduce only T108 local development lifecycle; no workers, Provider or .env."""

import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[1]
WORK = Path("/tmp/edumind-t108")


def environment(database_name="edumind_catalog_p15_t108_dev", api_port=8178):
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
        EDUMIND_API_PROXY_TARGET=f"http://127.0.0.1:{api_port}",
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
    p.add_argument(
        "--profile",
        choices=["t108", "fixed", "archive", "direct", "aiapi", "empty", "empty-r02", "stack", "trial-replay", "queue"],
        default="t108",
    )
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
    database_name, api_port, web_port = "edumind_catalog_p15_t108_dev", 8178, 5198
    if a.profile == "fixed":
        database_name = "edumind_catalog_p15_t108_t111_live"
    elif a.profile == "archive":
        if a.check_migration or a.test:
            p.error("Use the T112 checks listed in its delivery record")
        WORK = Path("/tmp/edumind-t112")
        database_name, api_port, web_port = "edumind_catalog_p15_t108_t112", 8182, 5202
    elif a.profile == "direct":
        if a.check_migration or a.test:
            p.error("Use the T114 checks listed in its execution package")
        WORK = Path("/tmp/edumind-t114")
        database_name, api_port, web_port = "edumind_catalog_p15_t108_t114", 8184, 5204
    elif a.profile == "empty":
        if a.check_migration or a.test:
            p.error("Use the T118 checks listed in its execution package")
        WORK = Path("/tmp/edumind-t118")
        database_name, api_port, web_port = "edumind_catalog_p15_t108_t118", 8188, 5208
    elif a.profile == "empty-r02":
        if a.check_migration or a.test:
            p.error("Use the T118 checks listed in its execution package")
        WORK = Path("/tmp/edumind-t118-r02")
        database_name, api_port, web_port = (
            "edumind_catalog_p15_t108_t118_r02",
            8190,
            5210,
        )
    elif a.profile == "stack":
        if a.check_migration or a.test:
            p.error("Use the targeted T119 checks")
        from app.services.stack_course_publication import DATABASE

        WORK = Path("/tmp/edumind-t119")
        database_name, api_port, web_port = DATABASE, 8192, 5212
    elif a.profile == "queue":
        if a.check_migration or a.test:
            p.error("Use the targeted T121 checks")
        from app.services.course_trial_publication import QUEUE

        WORK = Path("/tmp/edumind-t121")
        database_name, api_port, web_port = QUEUE.database, 8194, 5214
    elif a.profile == "trial-replay":
        if a.check_migration or a.test:
            p.error("Use the targeted T120 checks")
        from app.services.course_trial_replay import DATABASE

        WORK = Path("/tmp/edumind-t120")
        database_name, api_port, web_port = DATABASE, 8193, 5213
    elif a.profile == "aiapi":
        if a.check_migration or a.test:
            p.error("Use the targeted AIAPI batch checks")
        WORK = Path("/tmp/edumind-head-aiapi-content-r01")
        database_name, api_port, web_port = (
            "edumind_catalog_p15_t108_aiapi_content",
            8186,
            5206,
        )
    env = environment(database_name, api_port)
    if a.profile in ("direct", "empty", "empty-r02"):
        env["EDUMIND_HEAD_DEEPSEEK_DEVELOPMENT"] = "1"
        (WORK / "env.json").write_text(json.dumps(env))
    python = str(ROOT / "backend/.venv/bin/python")
    if a.prepare:
        subprocess.run(
            [python, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            env=env,
            check=True,
        )
    if a.start:
        for port in (api_port, web_port):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    p.error(f"Port {port} already in use")
        for name, cmd, cwd in [
            (
                "api",
                [
                    python,
                    "-c",
                    (
                        "from scripts.head_course_goal import serve; "
                        f"serve({api_port}, stack_only={a.profile == 'stack'}, "
                        f"replay_only={a.profile == 'trial-replay'}, queue_only={a.profile == 'queue'})"
                    ),
                ],
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
                    str(web_port),
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
            f"{a.profile} development entry http://127.0.0.1:{web_port}; API{api_port}; zero Provider/worker"
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
