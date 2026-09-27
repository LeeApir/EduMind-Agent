"""Non-billable HTTP path benchmark; isolated, explicitly synthetic profile fixture."""

import argparse
import asyncio
import json
import platform
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.profile_schema import empty_transient_profile
from app.core.database import create_database_engine
from app.services.profile_updates import persist_profile_version
from tests.manual_provider_acceptance import authenticated_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_mvp02_acceptance import distribution


async def seed_profile(database_url, owner_id):
    engine = create_database_engine(database_url)
    try:
        async with async_sessionmaker(engine)() as db:
            await persist_profile_version(
                db, owner_id=owner_id, profile=empty_transient_profile("学习单链表")
            )
            await db.commit()
    finally:
        await engine.dispose()


def main():
    import os

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite evidence")
    client, csrf = authenticated_client(args.base_url)
    try:
        owner = client.get("/api/auth/session").json()["user"]["id"]
        asyncio.run(seed_profile(os.environ["EDUMIND_DATABASE_URL"], UUID(owner)))
        target = {"target_node_id": "single-linked-list"}

        def headers():
            return {"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())}

        planned = client.post("/api/path/plan", json=target, headers=headers())
        assert planned.status_code == 201
        version = planned.json()["version"]
        report = {
            "environment": {
                "platform": platform.platform(),
                "python": platform.python_version(),
                "transport": "httpx TCP -> Uvicorn -> PostgreSQL",
                "concurrency": 1,
                "warmups_per_endpoint": 5,
                "samples_per_endpoint": 100,
                "fixture": "new guest, synthetic initial profile, 10-node real YAML",
                "provider_calls": 0,
            },
            "passed": False,
        }
        for mode in ("current", "replan"):
            timings, failures = [], 0
            for index in range(105):
                started = time.perf_counter()
                if mode == "current":
                    response = client.get("/api/path/current", params=target)
                else:
                    response = client.post(
                        "/api/path/replan",
                        json=target,
                        headers={**headers(), "If-Match-Path-Version": str(version)},
                    )
                    if response.status_code == 200:
                        version = response.json()["version"]
                elapsed = round((time.perf_counter() - started) * 1000, 3)
                if index < 5:
                    assert response.status_code == 200
                elif response.status_code == 200:
                    timings.append(elapsed)
                else:
                    failures += 1
            report[mode] = distribution(timings, failures)
        report["passed"] = (
            report["current"]["failures"] == report["replan"]["failures"] == 0
            and report["current"]["p99_ms"] <= 200
            and report["replan"]["p95_ms"] <= 200
        )
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    "passed": report["passed"],
                    "current_p99_ms": report["current"]["p99_ms"],
                    "replan_p95_ms": report["replan"]["p95_ms"],
                }
            )
        )
        if not report["passed"]:
            raise SystemExit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
