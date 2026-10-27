"""Offline PG/HTTPX Mock only. Requires the existing dedicated container to be ready."""
import os
import subprocess
import sys
from urllib.parse import quote

CONTAINER = "edumind-phase1-t037-pg"
DATABASE = "edumind_catalog_p15_t020_full_r05_offline"
assert subprocess.run(
    ["docker", "inspect", "--format", '{{index .Config.Labels "edumind.test-only"}}', CONTAINER],
    capture_output=True, text=True, check=True,
).stdout.strip() == "phase1-dsl"
subprocess.run(
    ["docker", "exec", CONTAINER, "pg_isready", "-U", "edumind_test", "-d", "postgres"],
    capture_output=True, check=True,
)
exists = subprocess.run(
    ["docker", "exec", CONTAINER, "psql", "-U", "edumind_test", "-d", "postgres", "-tAc",
     "SELECT 1 FROM pg_database WHERE datname='" + DATABASE + "'"],
    capture_output=True, text=True, check=True,
)
if exists.stdout.strip() != "1":
    subprocess.run(
        ["docker", "exec", CONTAINER, "createdb", "-U", "edumind_test", DATABASE], check=True,
    )
pw = subprocess.run(
    ["docker", "exec", CONTAINER, "printenv", "POSTGRES_PASSWORD"],
    capture_output=True, text=True, check=True,
).stdout.strip()
env = dict(os.environ, EDUMIND_TEST_DATABASE_URL=(
    "postgresql+asyncpg://edumind_test:" + quote(pw, safe="") + "@127.0.0.1:15437/" + DATABASE
))
sys.exit(subprocess.run(
    ["backend/.venv/bin/python", "-m", "pytest", "backend/tests/test_p15_full_diagnostic_r05.py",
     "-q", "--junitxml=/tmp/edumind-p15-full-r05-pg.xml"], env=env,
).returncode)
