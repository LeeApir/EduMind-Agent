"""Dedicated PG + Mock regressions. No credentials printed or stored."""
import os
import subprocess
import sys
from urllib.parse import quote
from uuid import uuid4

CONTAINER = "edumind-phase1-t037-pg"
GROUPS = {
    "t020": ["tests/test_free_scene_last_repair_pg.py", "tests/test_free_scene_consistency_pg.py", "tests/test_free_scene_markdown_pg.py", "tests/test_free_scene_semantics_pg.py", "tests/test_free_scene_answer_contract_pg.py", "tests/test_free_scene_form_contract_pg.py"],
    "t010": ["tests/test_free_scene_generation.py"],
    "t011": ["tests/test_free_scene_validation.py"],
    "t013": ["tests/test_free_scene_availability.py"],
    "t014": ["tests/test_free_course_scheduler.py"],
    "t017": ["tests/test_free_course_feedback.py"],
}

assert subprocess.run(
    ["docker", "inspect", "--format", '{{index .Config.Labels "edumind.test-only"}}', CONTAINER],
    capture_output=True, text=True, check=True,
).stdout.strip() == "phase1-dsl"
pw = subprocess.run(
    ["docker", "exec", CONTAINER, "printenv", "POSTGRES_PASSWORD"],
    capture_output=True, text=True, check=True,
).stdout.strip()
for group in sys.argv[1:] or GROUPS:
    assert group in GROUPS
    database = "edumind_catalog_p15_" + group + "_last_semantics_" + uuid4().hex[:8]
    subprocess.run(["docker", "exec", CONTAINER, "createdb", "-U", "edumind_test", database], check=True)
    url = "postgresql+asyncpg://edumind_test:" + quote(pw, safe="") + "@127.0.0.1:15437/" + database
    result = subprocess.run(
        [".venv/bin/python", "-m", "pytest", *GROUPS[group], "-q",
         "--junitxml=/tmp/edumind-t064-" + group + ".xml"],
        cwd="backend", env={**os.environ, "EDUMIND_TEST_DATABASE_URL": url},
    )
    if result.returncode:
        sys.exit(result.returncode)
