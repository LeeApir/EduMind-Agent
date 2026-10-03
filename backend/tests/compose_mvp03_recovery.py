"""T031 isolated Compose restart probe; never point it at a user database."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.profile_schema import empty_transient_profile  # noqa: E402
from app.core.auth import COOKIE_NAME  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402
from app.models.animation import AnimationJob, AnimationJobEvent  # noqa: E402
from app.models.learning import GeneratedResource, LearningScene, LearningUnit  # noqa: E402
from app.services.animation_cache import AnimationCache  # noqa: E402
from app.services.animation_worker import (  # noqa: E402
    JobLease,
    claim_animation_job,
    publish_animation_job,
)
from app.services.profile_updates import persist_profile_version  # noqa: E402

API = os.getenv("EDUMIND_T031_API", "http://127.0.0.1:18031")
DATABASE_URL = os.environ["EDUMIND_TEST_DATABASE_URL"]
STATE_PATH = Path(os.getenv("EDUMIND_T031_STATE", "/private/tmp/edumind-t031-state.json"))


def request(value: int) -> dict[str, object]:
    return {
        "template_id": "linked-list-insertion", "template_version": "1.0.0",
        "scene_version": 1,
        "parameters": {"values": [1, 3, 5], "index": 1, "value": value},
    }


def client_for(state: dict[str, object] | None = None) -> httpx.Client:
    client = httpx.Client(base_url=API, timeout=20, trust_env=False)
    if state is not None:
        client.headers["Cookie"] = f"{COOKIE_NAME}={state['session_token']}"
    return client


def post_headers(csrf: str) -> dict[str, str]:
    return {
        "Origin": API, "X-CSRF-Token": csrf, "Idempotency-Key": uuid4().hex,
    }


async def seed_unit(owner: UUID) -> UUID:
    engine = create_database_engine(DATABASE_URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            unit = LearningUnit(
                user_id=owner, knowledge_point_id="linked-list-insertion",
                title="T031 restart fixture", status="ready",
            )
            db.add(unit)
            await db.flush()
            scene = LearningScene(
                learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                scene_type="first_learning", version=1,
                generation_status="complete", review_status="passed",
            )
            db.add(scene)
            await db.flush()
            db.add(GeneratedResource(
                user_id=owner, learning_unit_id=unit.id, scene_id=scene.id,
                knowledge_point_id="linked-list-insertion", resource_type="explanation",
                content={"markdown": "重启后保留已审核讲解。"},
                review_status="passed", version=1,
                published_at=datetime.now(timezone.utc),
            ))
            await db.commit()
            await persist_profile_version(
                db, owner_id=owner,
                profile=empty_transient_profile("学习链表插入与容器恢复"),
            )
            return unit.id
    finally:
        await engine.dispose()


async def claim() -> JobLease:
    engine = create_database_engine(DATABASE_URL)
    try:
        lease = await claim_animation_job(async_sessionmaker(engine))
        assert lease is not None
        return lease
    finally:
        await engine.dispose()


def seed() -> None:
    assert "t031" in DATABASE_URL and "t031" in str(STATE_PATH)
    with client_for() as client:
        auth = client.post("/api/auth/guest")
        assert auth.status_code == 201, auth.text
        session_token = client.cookies.get(COOKIE_NAME)
        assert session_token
        client.headers["Cookie"] = f"{COOKIE_NAME}={session_token}"
        owner = UUID(auth.json()["user"]["id"])
        unit_id = asyncio.run(seed_unit(owner))
        csrf = auth.json()["csrf_token"]
        classroom_path = f"/api/learning-units/{unit_id}/classroom"
        created = client.post(classroom_path, headers=post_headers(csrf))
        assert created.status_code == 201, created.text
        changed = client.patch(
            classroom_path + "/mode", json={"mode": "interactive", "enabled_roles": ["beginner"]},
            headers={**post_headers(csrf), "If-Match-Classroom-Revision": "1"},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["revision"] == 2
        animation_path = f"/api/learning-units/{unit_id}/animations"
        completed = client.post(animation_path, json=request(9), headers=post_headers(csrf))
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "succeeded"
        running = client.post(animation_path, json=request(11), headers=post_headers(csrf))
        assert running.status_code == 202, running.text
        assert running.json()["status"] == "queued"
        cancelled = client.post(animation_path, json=request(12), headers=post_headers(csrf))
        assert cancelled.status_code == 202, cancelled.text
        assert cancelled.json()["status"] == "queued"
        cancelled_id = cancelled.json()["id"]
        cancelled = client.post(
            f"/api/animation-jobs/{cancelled_id}/cancel", headers=post_headers(csrf),
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "cancelled"
        lease = asyncio.run(claim())
        assert str(lease.job_id) == running.json()["id"]
        state: dict[str, object] = {
            "session_token": session_token, "unit_id": str(unit_id),
            "completed_id": completed.json()["id"],
            "completed_media_id": completed.json()["media_id"],
            "running_id": running.json()["id"], "cancelled_id": cancelled_id,
            "lease_token": str(lease.token), "lease_attempt": lease.attempt,
        }
        STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
        STATE_PATH.chmod(0o600)
        print(json.dumps({
            "seeded": True, "classroom_revision": 2,
            "job_states": ["succeeded", "running", "cancelled"],
        }))


def check_http(state: dict[str, object], *, recovered: bool) -> None:
    with client_for(state) as client:
        unit_id = state["unit_id"]
        classroom = client.get(f"/api/learning-units/{unit_id}/classroom")
        assert classroom.status_code == 200 and classroom.json()["revision"] == 2
        assert classroom.json()["mode"] == "interactive"
        assert classroom.json()["enabled_roles"] == ["beginner"]
        notes = client.get(f"/api/learning-units/{unit_id}/notes.md")
        assert notes.status_code == 200 and "重启后保留已审核讲解" in notes.text
        completed = client.get(f"/api/animation-jobs/{state['completed_id']}")
        assert completed.status_code == 200 and completed.json()["status"] == "succeeded"
        assert completed.json()["media_id"] == state["completed_media_id"]
        cancelled = client.get(f"/api/animation-jobs/{state['cancelled_id']}")
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        for extension in ("mp4", "srt"):
            path = f"/api/animation-media/{state['completed_media_id']}/{extension}?download=true"
            response = client.get(path)
            assert response.status_code == 200 and response.content
            assert hashlib.sha256(response.content).hexdigest() == response.headers[
                "x-animation-content-sha256"
            ]
        running = client.get(f"/api/animation-jobs/{state['running_id']}")
        assert running.status_code == 200
        if recovered:
            assert running.json()["status"] == "succeeded", running.text
            media_id = running.json()["media_id"]
            response = client.get(f"/api/animation-media/{media_id}/mp4?download=true")
            assert response.status_code == 200 and response.content
            assert hashlib.sha256(response.content).hexdigest() == response.headers[
                "x-animation-content-sha256"
            ]
        else:
            assert running.json()["status"] == "running", running.text


async def check_database(state: dict[str, object]) -> None:
    engine = create_database_engine(DATABASE_URL)
    try:
        async with async_sessionmaker(engine)() as db:
            running = await db.get(AnimationJob, UUID(str(state["running_id"])))
            cancelled = await db.get(AnimationJob, UUID(str(state["cancelled_id"])))
            assert running is not None and running.status == "succeeded" and running.attempt == 2
            assert cancelled is not None
            assert cancelled.status == "cancelled" and cancelled.attempt == 0
            events = (await db.scalars(select(AnimationJobEvent).where(
                AnimationJobEvent.job_id == running.id,
            ).order_by(AnimationJobEvent.event_id))).all()
            assert [event.event_type for event in events] == [
                "queued", "running", "recovered", "running", "progress", "succeeded",
            ]
            assert len((await db.scalars(select(AnimationJobEvent).where(
                AnimationJobEvent.job_id == cancelled.id,
            ))).all()) == 2
        old_lease = JobLease(
            job_id=UUID(str(state["running_id"])),
            owner_id=running.user_id, attempt=int(state["lease_attempt"]),
            token=UUID(str(state["lease_token"])), template_id="linked-list-insertion",
            parameters=request(11)["parameters"],
        )
        media = AnimationCache().lookup("linked-list-insertion", request(11)["parameters"])
        assert media is not None
        assert await publish_animation_job(
            async_sessionmaker(engine), old_lease, cache=AnimationCache(), media=media,
        ) is False
    finally:
        await engine.dispose()


def check(*, recovered: bool) -> None:
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    check_http(state, recovered=recovered)
    if recovered:
        asyncio.run(check_database(state))
    print(json.dumps({"recovered": recovered, "classroom_revision": 2,
                      "media_and_exports_valid": True}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("seed", "check-restart", "check-worker"))
    command = parser.parse_args().command
    if command == "seed":
        seed()
    else:
        check(recovered=command == "check-worker")


if __name__ == "__main__":
    main()
