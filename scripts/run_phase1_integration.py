"""Replay T038 on a clean frozen checkout with isolated PG/Redis and no Provider."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

from run_phase1_dsl_safety import isolated_environment

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/acceptance/phase-1-integration/protocol.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    assert re.fullmatch(r"r[0-9]{2}", args.run_id)
    assert not git("status", "--porcelain"), "Clean source checkout required"
    plan = json.loads(PLAN.read_text())
    assert plan["provider_requests_authorized"] == 0
    output = ROOT / "local-materials/phase-1-t038" / args.run_id
    output.mkdir(parents=True, exist_ok=False)
    guard = output / "guard"
    guard.mkdir()
    # Every Python child (including Uvicorn/Celery) inherits the loopback-only audit.
    (guard / "sitecustomize.py").write_text(
        "import ipaddress,os,sys\n"
        "def guard(event,args):\n"
        ' if event in ("socket.connect","socket.sendto"):\n'
        '  address=args[1] if event=="socket.connect" else args[-1]\n'
        "  if isinstance(address,tuple):\n"
        "   try: local=ipaddress.ip_address(address[0]).is_loopback\n"
        '   except ValueError: local=address[0]=="localhost"\n'
        "   if not local:\n"
        '    with open(os.environ["T038_NETWORK_AUDIT"],"a") as f: f.write("blocked\\n")\n'
        '    raise RuntimeError("T038 forbids non-loopback network")\n'
        "sys.addaudithook(guard)\n"
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("EDUMIND_")}
    env.update(
        EDUMIND_CATALOG_TEST_PG_CONTAINER="edumind-phase1-t037-pg",
        PYTHONPATH=str(guard),
        T038_NETWORK_AUDIT=str(output / "network-audit.txt"),
    )
    os.environ.update(env)
    for key in list(os.environ):
        if key.startswith("EDUMIND_") and key not in env:
            del os.environ[key]
    redis = json.loads(
        subprocess.check_output(
            ["docker", "inspect", "edumind-phase1-queue-test-redis"], text=True
        )
    )[0]
    assert redis["Config"]["Labels"].get("edumind.test-only") == "phase1-queue"
    assert redis["NetworkSettings"]["Ports"]["6379/tcp"] == [
        {"HostIp": "127.0.0.1", "HostPort": "15579"}
    ]
    pinned = tomllib.loads((ROOT / "backend/pyproject.toml").read_text())
    versions = {}
    for requirement in (
        pinned["project"]["dependencies"] + pinned["dependency-groups"]["dev"]
    ):
        name, version = requirement.split("==")
        name = name.split("[")[0]
        versions[name] = importlib.metadata.version(name)
        assert versions[name] == version, name
    report = {
        "source_commit": git("rev-parse", "HEAD"),
        "clean_before": True,
        "protocol_sha256": sha(PLAN),
        "provider_requests": 0,
        "dependency_method": "cached locked installations; no new network install",
        "python_versions": versions,
        "lock_sha256": {
            p: sha(ROOT / p) for p in ("backend/uv.lock", "web/pnpm-lock.yaml")
        },
        "commands": [],
        "backend": [],
        "passed": False,
    }

    def save():
        (output / "result.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )

    def run(name, command, *, cwd=ROOT, environment=None, timeout=1200):
        with (output / (name + ".log")).open("wb") as log:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=environment or env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        item = {"name": name, "command": command, "exit_code": result.returncode}
        report["commands"].append(item)
        save()
        print(name, "exit", result.returncode, flush=True)
        return result.returncode

    save()
    for name, command, directory in [
        ("backend-mypy", [sys.executable, "-m", "mypy", "app"], ROOT / "backend"),
        (
            "backend-ruff",
            [sys.executable, "-m", "ruff", "check", "app", "tests"],
            ROOT / "backend",
        ),
        ("web-dependencies", ["pnpm", "list", "--depth", "0", "--json"], ROOT / "web"),
        ("web-unit", ["pnpm", "test", "--run"], ROOT / "web"),
        ("web-typecheck", ["pnpm", "typecheck"], ROOT / "web"),
        ("web-lint", ["pnpm", "lint"], ROOT / "web"),
        ("web-build", ["pnpm", "build"], ROOT / "web"),
    ]:
        run(name, command, cwd=directory)
    # Direct frontend pins must match the lock-installed cache as well.
    frontend = json.loads((output / "web-dependencies.log").read_text())[0]
    expected = json.loads((ROOT / "web/package.json").read_text())
    for category in ("dependencies", "devDependencies"):
        assert all(
            frontend[category][name]["version"] == version
            for name, version in expected[category].items()
        )
    # Destructive policy revocation and migration tests never share a DB across files.
    for index, filename in enumerate(plan["backend_files"]):
        prefix = (
            "t025_t038" if filename.endswith("test_animation_dsl_review.py") else "t038"
        )
        database = f"edumind_catalog_phase1_{prefix}_{args.run_id}_{index:03}"
        child_env = isolated_environment(database)
        child_env.update(
            EDUMIND_PRODUCT_MODE="dynamic",
            EDUMIND_DOCKER_TESTS="1",
            EDUMIND_ANIMATION_DISPATCH="pg_poll",
            EDUMIND_TEST_QUEUE_BROKER=(
                "redis://publisher:synthetic_queue_test_only_password@127.0.0.1:15579/0"
            ),
        )
        label = f"backend-{index:03}"
        assert (
            run(
                label + "-migration",
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT / "backend",
                environment=child_env,
            )
            == 0
        )
        xml = output / (label + ".xml")
        code = run(
            label,
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-rs",
                filename,
                "--junitxml=" + str(xml),
            ],
            cwd=ROOT / "backend",
            environment=child_env,
        )
        counts = {
            key: sum(int(s.get(key, "0")) for s in ET.parse(xml).getroot())
            for key in ("tests", "failures", "errors", "skipped")
        }
        report["backend"].append(
            {
                "file": filename,
                "database": database,
                "counts": counts,
                "exit_code": code,
            }
        )
        save()
        print(filename, counts, flush=True)
    run("mock-core-browser", [sys.executable, "web/tests/e2e/run.py"])
    run(
        "mock-settings-path-browser",
        [
            sys.executable,
            "web/tests/e2e/phase1_mock_integration.py",
            "--output",
            str(output / "mock-ui"),
        ],
    )
    child_env = isolated_environment(
        f"edumind_catalog_phase1_t038_{args.run_id}_catalog"
    )
    cache = output / "catalog-cache"
    child_env.update(
        EDUMIND_PRODUCT_MODE="catalog_only",
        EDUMIND_ANIMATION_DISPATCH="pg_poll",
        EDUMIND_KNOWLEDGE_GRAPH_VERSION="phase-1.1.0",
        EDUMIND_CATALOG_PROTOCOL=str(PLAN),
        EDUMIND_CATALOG_RESULT=str(output / "catalog-result.json"),
        EDUMIND_ANIMATION_CACHE_ROOT=str(cache),
        EDUMIND_CATALOG_QUALITY_CACHE=str(cache),
        EDUMIND_RENDER_LOCK_ROOT=str(output / "render-locks"),
    )
    assert (
        run(
            "catalog-migration",
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            environment=child_env,
        )
        == 0
    )
    run(
        "catalog-real-browser",
        [sys.executable, "web/tests/e2e/phase1_catalog_integration.py"],
        environment=child_env,
    )
    # T038 independently repeats the frozen 100 physical SSE disconnects.
    matrix_output = output / "queue-matrix"
    matrix_output.mkdir()
    matrix_env = isolated_environment(f"edumind_catalog_phase1_t038_{args.run_id}_sse")
    matrix_env.update(
        EDUMIND_PRODUCT_MODE="catalog_only",
        EDUMIND_ANIMATION_BROKER_URL=(
            "redis://publisher:synthetic_queue_test_only_password@127.0.0.1:15579/0"
        ),
        EDUMIND_QUEUE_MATRIX_OUTPUT=str(matrix_output),
        EDUMIND_QUEUE_MATRIX_PROTOCOL=str(PLAN.with_name("sse-protocol.json")),
    )
    assert (
        run(
            "sse-migration",
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            environment=matrix_env,
        )
        == 0
    )
    run(
        "sse-template-matrix",
        [sys.executable, "-m", "tests.queue_acceptance_matrix"],
        cwd=ROOT / "backend",
        environment=matrix_env,
        timeout=2400,
    )
    matrix = json.loads((matrix_output / "matrix-result.json").read_text())
    report["sse_counts"] = {
        "total": len(matrix["sse_slots"]),
        "ok": sum(row["ok"] for row in matrix["sse_slots"]),
    }
    report["sse_matrix_passed"] = matrix.get("matrix_passed", False)
    paths = ROOT / "local-materials/phase-1-t033/latency.json"
    report["path_metrics"] = json.loads(paths.read_text())
    report["backend_counts"] = {
        key: sum(item["counts"][key] for item in report["backend"])
        for key in ("tests", "failures", "errors", "skipped")
    }
    report["clean_after"] = not git("status", "--porcelain")
    audit = output / "network-audit.txt"
    report["external_attempts"] = (
        len(audit.read_text().splitlines()) if audit.exists() else 0
    )
    report["passed"] = (
        all(item["exit_code"] == 0 for item in report["commands"])
        and all(
            report["backend_counts"][k] == 0 for k in ("failures", "errors", "skipped")
        )
        and report["clean_after"]
        and report["external_attempts"] == 0
        and report["sse_matrix_passed"]
        and report["sse_counts"]["total"] == 100
        and report["sse_counts"]["ok"] >= 99
    )
    save()
    print(
        json.dumps(
            {k: report[k] for k in ("source_commit", "backend_counts", "passed")}
        )
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
