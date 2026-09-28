"""Durable SSE cursor, owner isolation, disconnect and restart behavior."""

import asyncio
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import animation_events
from app.core.database import create_database_engine
from app.main import app
from app.models.animation import (
    AnimationJob,
    AnimationJobEvent,
    AnimationMedia,
    AnimationResourceBinding,
)
from app.models.auth import GuestSessionRecord
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_worker import (
    claim_animation_job,
    fail_animation_job,
    report_animation_progress,
)

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def _clean_jobs() -> None:
    assert TEST_DATABASE_URL is not None

    async def clean() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            async with engine.begin() as connection:
                for table in (
                    AnimationResourceBinding, AnimationJobEvent, AnimationJob, AnimationMedia
                ):
                    await connection.execute(delete(table))
        finally:
            await engine.dispose()

    asyncio.run(clean())


async def _target(owner: UUID) -> UUID:
    assert TEST_DATABASE_URL is not None
    engine = create_database_engine(TEST_DATABASE_URL)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            unit = LearningUnit(
                user_id=owner, knowledge_point_id="linked-list-insertion",
                title="SSE", status="ready",
            )
            db.add(unit)
            await db.flush()
            db.add(LearningScene(
                learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                scene_type="first_learning", version=1,
                generation_status="complete", review_status="passed",
            ))
            await db.commit()
            return unit.id
    finally:
        await engine.dispose()


def _create(client: TestClient, value: int) -> tuple[dict[str, object], UUID]:
    auth = client.post("/api/auth/guest").json()
    unit_id = asyncio.run(_target(UUID(auth["user"]["id"])))
    created = client.post(
        f"/api/learning-units/{unit_id}/animations",
        json={
            "template_id": "linked-list-insertion", "template_version": "1.0.0",
            "scene_version": 1,
            "parameters": {"values": [1, 3, 5], "index": 1, "value": value},
        },
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": uuid4().hex, "Origin": "https://testserver",
        },
    )
    assert created.status_code == 202, created.text
    return auth, UUID(created.json()["id"])


def _ids(body: str) -> list[int]:
    return [int(line.removeprefix("id: ")) for line in body.splitlines() if line.startswith("id: ")]


def test_terminal_sse_replays_only_new_events_across_client_restart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    with TestClient(app, base_url="https://testserver") as client:
        auth, job_id = _create(client, 50)
        token = client.cookies.get("edumind_session")
        assert token is not None

        async def fail() -> None:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                lease = await claim_animation_job(sessions)
                assert lease is not None and lease.job_id == job_id
                assert await fail_animation_job(sessions, lease, code="RENDER_UNAVAILABLE")
            finally:
                await engine.dispose()

        asyncio.run(fail())
        path = f"/api/animation-jobs/{job_id}/events"
        all_events = client.get(path)
        assert all_events.status_code == 200
        assert _ids(all_events.text) == [1, 2, 3]
        assert all_events.headers["content-type"].startswith("text/event-stream")
        assert all_events.headers["cache-control"] == "no-store"
        assert all_events.text.count("event: failed") == 1
        assert json.loads(all_events.text.split("event: failed\ndata: ")[1].split("\n")[0])[
            "code"
        ] == "RENDER_UNAVAILABLE"
        tail = client.get(path, headers={"Last-Event-ID": "2"})
        assert _ids(tail.text) == [3]
        assert _ids(client.get(path + "?after=2").text) == [3]
        assert _ids(client.get(path + "?after=1", headers={"Last-Event-ID": "2"}).text) == [3]
        consumed = client.get(path, headers={"Last-Event-ID": "3"})
        assert consumed.status_code == 200 and consumed.text == ""
        assert client.get(path, headers={"Last-Event-ID": "4"}).json()[
            "code"
        ] == "EVENT_CURSOR_INVALID"
        assert client.get(path, headers={"Last-Event-ID": "bad"}).status_code == 409
        with TestClient(app, base_url="https://testserver") as foreign:
            foreign.post("/api/auth/guest")
            assert foreign.get(path).status_code == 404

    with TestClient(app, base_url="https://testserver") as restarted:
        restarted.cookies.set("edumind_session", token)
        recovered = restarted.get(path, headers={"Last-Event-ID": "1"})
        assert recovered.status_code == 200 and _ids(recovered.text) == [2, 3]
        snapshot = restarted.get(f"/api/animation-jobs/{job_id}")
        assert snapshot.json()["last_event_id"] == 3
        assert snapshot.json()["status"] == "failed"
    assert auth["user"]["id"] not in all_events.text


def test_gap_returns_expired_and_snapshot_cursor_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    with TestClient(app, base_url="https://testserver") as client:
        _, job_id = _create(client, 51)

        async def make_gap() -> None:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                lease = await claim_animation_job(sessions)
                assert lease is not None and lease.job_id == job_id
                assert await fail_animation_job(sessions, lease, code="RENDER_UNAVAILABLE")
                async with sessions() as db:
                    await db.execute(delete(AnimationJobEvent).where(
                        AnimationJobEvent.job_id == job_id,
                        AnimationJobEvent.event_id == 2,
                    ))
                    await db.commit()
            finally:
                await engine.dispose()

        asyncio.run(make_gap())
        path = f"/api/animation-jobs/{job_id}/events"
        expired = client.get(path, headers={"Last-Event-ID": "1"})
        assert expired.status_code == 410
        assert expired.json()["code"] == "EVENT_CURSOR_EXPIRED"
        snapshot = client.get(f"/api/animation-jobs/{job_id}").json()
        assert snapshot["last_event_id"] == 3
        assert client.get(path, headers={"Last-Event-ID": "3"}).text == ""


def test_disconnect_does_not_change_job_or_render_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    with TestClient(app, base_url="https://testserver") as client:
        auth, job_id = _create(client, 52)
        token_hash = client.cookies.get("edumind_session")
        assert token_hash is not None
        from app.core.auth import token_hash as hash_token

        async def disconnect() -> None:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)

                class Connected:
                    async def is_disconnected(self) -> bool:
                        return False

                assert animation_events._STREAM_LIMIT.acquire(blocking=False)
                stream = animation_events._events(
                    Connected(), sessions, owner_id=UUID(auth["user"]["id"]),
                    token_hash=hash_token(token_hash), job_id=job_id, after=0,
                )
                first = await anext(stream)
                assert _ids(first) == [1]
                await stream.aclose()
                async with sessions() as db:
                    job = await db.get(AnimationJob, job_id)
                    events = (await db.scalars(select(AnimationJobEvent).where(
                        AnimationJobEvent.job_id == job_id,
                    ))).all()
                    assert job is not None and job.status == "queued" and job.attempt == 0
                    assert len(events) == 1
            finally:
                await engine.dispose()

        asyncio.run(disconnect())
        assert client.get(f"/api/animation-jobs/{job_id}").json()["status"] == "queued"


def test_live_stream_delivers_progress_and_closes_on_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(animation_events, "_POLL_SECONDS", 0.01)
    with TestClient(app, base_url="https://testserver") as client:
        auth, job_id = _create(client, 54)
        raw_cookie = client.cookies.get("edumind_session")
        assert raw_cookie is not None
        from app.core.auth import token_hash as hash_token

        async def exercise() -> None:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)

                class Connected:
                    async def is_disconnected(self) -> bool:
                        return False

                assert animation_events._STREAM_LIMIT.acquire(blocking=False)
                stream = animation_events._events(
                    Connected(), sessions, owner_id=UUID(auth["user"]["id"]),
                    token_hash=hash_token(raw_cookie), job_id=job_id, after=0,
                )
                assert _ids(await anext(stream)) == [1]
                lease = await claim_animation_job(sessions)
                assert lease is not None and lease.job_id == job_id
                assert await report_animation_progress(
                    sessions, lease, stage="validating", progress=0.8,
                )
                assert await fail_animation_job(sessions, lease, code="RENDER_UNAVAILABLE")
                frames = [await asyncio.wait_for(anext(stream), timeout=2) for _ in range(3)]
                assert [_ids(frame) for frame in frames] == [[2], [3], [4]]
                assert [frame.split("event: ")[1].split("\n")[0] for frame in frames] == [
                    "running", "progress", "failed",
                ]
                with pytest.raises(StopAsyncIteration):
                    await asyncio.wait_for(anext(stream), timeout=2)
            finally:
                await engine.dispose()

        asyncio.run(exercise())


def test_expired_cookie_ends_open_stream_and_connection_limit_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    with TestClient(app, base_url="https://testserver") as client:
        auth, job_id = _create(client, 53)
        raw_cookie = client.cookies.get("edumind_session")
        assert raw_cookie is not None
        from app.core.auth import token_hash as hash_token

        limited = threading.BoundedSemaphore(1)
        assert limited.acquire(blocking=False)
        monkeypatch.setattr(animation_events, "_STREAM_LIMIT", limited)
        saturated = client.get(f"/api/animation-jobs/{job_id}/events")
        assert saturated.status_code == 503 and saturated.json()["code"] == "STREAM_CAPACITY"
        limited.release()

        async def expire() -> None:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)

                class Connected:
                    async def is_disconnected(self) -> bool:
                        return False

                assert limited.acquire(blocking=False)
                stream = animation_events._events(
                    Connected(), sessions, owner_id=UUID(auth["user"]["id"]),
                    token_hash=hash_token(raw_cookie), job_id=job_id, after=0,
                )
                assert _ids(await anext(stream)) == [1]
                async with sessions() as db:
                    await db.execute(update(GuestSessionRecord).where(
                        GuestSessionRecord.token_hash == hash_token(raw_cookie),
                    ).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
                    await db.commit()
                monkeypatch.setattr(animation_events, "_POLL_SECONDS", 0.01)
                with pytest.raises(StopAsyncIteration):
                    await asyncio.wait_for(anext(stream), timeout=2)
                assert limited.acquire(blocking=False)
                limited.release()
            finally:
                await engine.dispose()

        asyncio.run(expire())
