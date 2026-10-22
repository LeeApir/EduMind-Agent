"""Run zero-Provider migration checks only in newly named, labelled test PG databases."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import run_catalog_db_tests  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"r[0-9]{2}", args.run_id):
        raise ValueError("A fixed numbered test run is required")
    args.output.mkdir(parents=True, exist_ok=False)
    run_catalog_db_tests.CONTAINER = "edumind-phase1-t037-pg"
    groups = [
        "test_free_scene_actions.py",
        "test_free_scene_validation.py",
        "test_free_scene_generation.py",
        "test_free_course_graph_links.py",
        "test_free_course_planning.py",
        "test_free_course_snapshots.py",
        "test_free_course_migrations.py",
        "test_learning_plan_persistence.py",
        "test_learning_state_models.py",
        "test_transient_profiles.py",
        "test_catalog_publication.py",
        "test_shared_learning_plan.py",
        "test_knowledge_graph.py",
        "test_expanded_graph_repository.py",
        "test_path_rules.py",
        "test_path_versions.py",
        "test_expanded_learning_paths.py",
        "test_knowledge_graph_api.py",
        "test_paths_api.py",
    ]
    summary = []
    for i, name in enumerate(groups):
        task_prefix = {0: "t012", 1: "t011", 2: "t010", 3: "t009", 4: "t008", 5: "t007"}.get(i, "t006")
        database = f"edumind_catalog_p15_{task_prefix}_t012_{args.run_id}_{i}"
        env = run_catalog_db_tests.test_environment(database)
        env = {
            k: v
            for k, v in env.items()
            if not k.startswith(("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL"))
        }
        env["EDUMIND_PRODUCT_MODE"] = "catalog_only"
        # No actual Provider, API server or credentials file is loaded.
        log = args.output / f"group-{i}.log"
        xml = args.output / f"group-{i}.xml"
        with log.open("w") as stream:
            if i > 6:
                subprocess.run(
                    [sys.executable, "-m", "alembic", "upgrade", "head"],
                    cwd=ROOT / "backend",
                    env=env,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=60,
                )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    f"backend/tests/{name}",
                    "-q",
                    "--tb=short",
                    "--junitxml=" + str(xml),
                ],
                cwd=ROOT,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=120,
            )
        suites = ET.parse(xml).getroot()
        counts = {
            key: sum(int(suite.get(key, "0")) for suite in suites)
            for key in ["tests", "failures", "errors", "skipped"]
        }
        properties = {
            p.get("name"): p.get("value") for p in suites.findall(".//property")
        }
        record = dict(
            test=name,
            database=database,
            exit_code=result.returncode,
            counts=counts,
            properties=properties,
            log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
            xml_sha256=hashlib.sha256(xml.read_bytes()).hexdigest(),
        )
        summary.append(record)
        (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(name, counts, flush=True)
        if (
            result.returncode
            or counts["failures"]
            or counts["errors"]
            or counts["skipped"]
        ):
            raise SystemExit("Group failed or skipped; inspect local logs")
    print("PASS: all migration/legacy groups; zero skipped, zero Provider calls")


if __name__ == "__main__":
    main()
