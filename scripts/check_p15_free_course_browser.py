"""T036 explicit real API/browser run, with a strictly offline --check entry."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/acceptance/phase-1.5-browser-t036/results.json"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ready(url):
    limit = time.monotonic() + 30
    while time.monotonic() < limit:
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.1)
    raise RuntimeError("Dedicated local server did not start")


def check():
    data = json.loads(REPORT.read_text())
    assert (
        data["real_provider_calls"] == 0 and data["production_mode"] == "catalog_only"
    )
    assert data["api_route_mocks"] == 0 and data["database"].startswith(
        "edumind_catalog_p15_t036_"
    )
    assert (
        data["exit_code"] == 0
        and data["transport"]["real_provider_calls"] == 0
        and data["transport"]["external_network"] == "blocked"
    )
    assert data["transport"]["production_mode_changed"] is False
    root = Path("/tmp/edumind-p15-t036-" + data["run_id"])
    for name, value in data["evidence_sha256"].items():
        path = Path(name)
        assert path.is_relative_to(root)
        assert sha(path) == value, name
    browser = json.loads((root / "browser-results.json").read_text())
    assert browser["api_route_mocks"] == 0 and not browser["page_errors"]
    assert [s["width"] for s in browser["scenarios"]] == [1440, 320]
    assert all(
        s["created"] == 2
        and s["feedback"] == 1
        and s["revision"] == 1
        and s["tutor"] == 1
        and s["refresh_duplicate_writes"] == 0
        and s["partial_failure_readable"] is True
        for s in browser["scenarios"]
    )
    requests = json.loads((root / "requests.json").read_text())
    assert (
        sum(
            r["method"] == "POST"
            and r["path"] == "/api/free-courses"
            and r["status"] == 201
            for r in requests
        )
        == 4
    )
    names = [
        "settings-return",
        "first-scene",
        "complete-course",
        "attempt",
        "tutor",
        "feedback",
        "atomic-revision",
        "history",
        "restored",
        "graph",
        "profile",
        "catalog",
        "partial-failure",
        "partial-restored",
    ]
    assert {p.name for p in root.glob("*.png")} == {
        f"{name}-{width}.png" for name in names for width in [1440, 320]
    }
    print(
        "PASS offline exact T036 evidence: 2 real browser journeys, 4 creates, actual API/PG/workers, 0 real Provider; --check sends nothing"
    )


def run(run_id):
    if not re.fullmatch(r"r[0-9]{2}", run_id):
        raise ValueError("Fixed numbered run required")
    output = Path("/tmp/edumind-p15-t036-" + run_id)
    output.mkdir(exist_ok=False)
    import run_catalog_db_tests

    run_catalog_db_tests.CONTAINER = "edumind-phase1-t037-pg"
    database = "edumind_catalog_p15_t036_" + run_id
    env = run_catalog_db_tests.test_environment(database)
    env = {
        k: v
        for k, v in env.items()
        if not k.startswith(
            ("EDUMIND_PROVIDER", "EDUMIND_CREDENTIAL", "EDUMIND_REVIEW_CANDIDATE")
        )
    }
    env.update(
        EDUMIND_PRODUCT_MODE="dynamic",
        EDUMIND_API_PROXY_TARGET="http://127.0.0.1:8175",
        PYTHONPATH=str(ROOT / "backend"),
    )
    processes = []
    logs = []
    exit_code = -1
    try:
        with (output / "migration.log").open("w") as log:
            subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT / "backend",
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=90,
            )
        for name, command, cwd, url in [
            (
                "api",
                [
                    sys.executable,
                    "tests/p15_acceptance_server.py",
                    "--output",
                    str(output),
                ],
                ROOT / "backend",
                "http://127.0.0.1:8175/health",
            ),
            (
                "web",
                [
                    "pnpm",
                    "dev",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5192",
                    "--strictPort",
                ],
                ROOT / "web",
                "http://127.0.0.1:5192",
            ),
        ]:
            log = (output / (name + ".log")).open("w")
            logs.append(log)
            processes.append(
                subprocess.Popen(
                    command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT
                )
            )
            ready(url)
        with (output / "browser.log").open("w") as log:
            result = subprocess.run(
                [
                    sys.executable,
                    "web/tests/e2e/p15_free_course_browser.py",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=240,
            )
            exit_code = result.returncode
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs:
            log.close()
    if exit_code:
        raise SystemExit(
            "Browser failed; preserve raw local logs/screenshots, do not claim pass"
        )
    transport = json.loads((output / "transport-summary.json").read_text())
    data = dict(
        run_id=run_id,
        database=database,
        api_route_mocks=0,
        real_provider_calls=0,
        production_mode="catalog_only",
        test_mode="isolated dynamic fixture only",
        exit_code=exit_code,
        transport=transport,
        evidence_sha256={
            str(p): sha(p) for p in sorted(output.iterdir()) if p.is_file()
        },
    )
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(json.dumps(data, indent=2) + "\n")
    check()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--run", metavar="rNN")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        run(args.run)


if __name__ == "__main__":
    main()
