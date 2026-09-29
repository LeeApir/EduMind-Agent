"""T032 real-render probe: learning and scoring stay usable while a Job runs."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT / "web" / "tests" / "e2e"))

from real_stage_backend import app  # noqa: E402
from real_stage_flow import seed  # noqa: E402

from app.core.database import create_database_engine  # noqa: E402
from app.models.learning import GeneratedResource  # noqa: E402
from app.services.animation_worker import run_one_animation_job  # noqa: E402
from app.services.profile_behavior_updates import profile_behavior_gateway_factory  # noqa: E402
from app.services.provider_gateway import ProviderError, ProviderErrorCode  # noqa: E402


async def exercise_for(unit_id: UUID) -> UUID:
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine)() as db:
            resource = await db.scalar(select(GeneratedResource).where(
                GeneratedResource.learning_unit_id == unit_id,
                GeneratedResource.resource_type == "exercise",
            ))
            assert resource is not None
            return resource.id
    finally:
        await engine.dispose()


async def work() -> UUID | None:
    engine = create_database_engine()
    try:
        return await run_one_animation_job(async_sessionmaker(engine))
    finally:
        await engine.dispose()


def run(output: Path) -> None:
    if output.exists():
        raise RuntimeError("Refusing to overwrite an existing report")
    if not os.getenv("EDUMIND_TEST_DATABASE_URL") or not os.getenv("EDUMIND_ANIMATION_CACHE_ROOT"):
        raise RuntimeError("Isolated database and fresh cache root are required")
    os.environ["EDUMIND_DATABASE_URL"] = os.environ["EDUMIND_TEST_DATABASE_URL"]
    cache_root = Path(os.environ["EDUMIND_ANIMATION_CACHE_ROOT"])
    assert not cache_root.exists(), cache_root

    def unavailable():
        raise ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE)

    app.dependency_overrides[profile_behavior_gateway_factory] = lambda: unavailable
    try:
        with TestClient(app, base_url="https://testserver") as client:
            auth = client.post("/api/auth/guest")
            assert auth.status_code == 201, auth.text
            owner = UUID(auth.json()["user"]["id"])
            unit_id = asyncio.run(seed(owner))
            exercise_id = asyncio.run(exercise_for(unit_id))
            headers = {
                "Origin": "https://testserver",
                "X-CSRF-Token": auth.json()["csrf_token"],
                "Idempotency-Key": uuid4().hex,
            }
            created = client.post(
                f"/api/learning-units/{unit_id}/animations",
                json={
                    "template_id": "linked-list-insertion", "template_version": "1.0.0",
                    "scene_version": 1,
                    "parameters": {"values": [1, 3, 5], "index": 1, "value": 4},
                }, headers=headers,
            )
            assert created.status_code == 202 and created.json()["status"] == "queued"
            job_id = UUID(created.json()["id"])
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(lambda: asyncio.run(work()))
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    status = client.get(f"/api/animation-jobs/{job_id}").json()["status"]
                    if status == "running":
                        break
                    time.sleep(0.05)
                assert status == "running" and not future.done()
                start = time.monotonic()
                unit = client.get(f"/api/learning-units/{unit_id}")
                assert unit.status_code == 200 and "先保存后继" in unit.text
                receipt = client.post(
                    "/api/quiz-submissions", json={
                        "resource_id": str(exercise_id), "resource_version": 1,
                        "answers": [
                            {"question_id": "q1", "answer": "O(1)"},
                            {"question_id": "q2", "answer": "next"},
                        ],
                    }, headers={**headers, "Idempotency-Key": uuid4().hex},
                )
                assert receipt.status_code == 200, receipt.text
                assert receipt.json()["correct_count"] == 2
                assert receipt.json()["score"] == 1.0
                elapsed = time.monotonic() - start
                assert not future.done(), "Render finished before concurrent reads ended"
                assert future.result(timeout=150) == job_id
            final = client.get(f"/api/animation-jobs/{job_id}")
            assert final.status_code == 200 and final.json()["status"] == "succeeded"
            result = {
                "job_id": str(job_id), "status_during_learning": "running",
                "explanation_status": unit.status_code,
                "quiz_status": receipt.status_code,
                "quiz_score": receipt.json()["score"],
                "correct_count": receipt.json()["correct_count"],
                "learning_elapsed_seconds": round(elapsed, 4),
                "final_status": final.json()["status"],
                "provider_calls": 0,
            }
            output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(result), flush=True)
    finally:
        app.dependency_overrides.pop(profile_behavior_gateway_factory, None)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: animation_nonblocking_probe.py OUTPUT.json")
    run(Path(sys.argv[1]))
