"""Cookie-protected animation cache hit, lifecycle and publication race regression."""

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.animation_templates.insertion_plan import srt_for_insertion
from app.core.database import create_database_engine
from app.main import app
from app.models.animation import (
    AnimationJob,
    AnimationJobEvent,
    AnimationMedia,
    AnimationResourceBinding,
)
from app.models.learning import LearningScene, LearningUnit
from app.services.animation_cache import AnimationCache
from app.services.animation_jobs import AnimationIdempotencyConflict
from app.services.animation_lifecycle import AnimationJobStateConflict, cancel_animation_job
from app.services.animation_renderer import IMAGE, RenderedCandidate, RenderError
from app.services.animation_worker import (
    claim_animation_job,
    fail_animation_job,
    publish_animation_job,
    run_one_animation_job,
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


def _fake_renderer(template_id: str, parameters: dict[str, object], *, work_root: Path):
    assert template_id == "linked-list-insertion"
    attempt = Path(tempfile.mkdtemp(prefix="api-fake-", dir=work_root))
    mp4, srt = attempt / "scene.mp4", attempt / "scene.srt"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + json.dumps(parameters, sort_keys=True).encode())
    srt.write_text(srt_for_insertion(), encoding="utf-8")
    return RenderedCandidate(
        attempt, mp4, srt, 36.0,
        hashlib.sha256(mp4.read_bytes()).hexdigest(),
        hashlib.sha256(srt.read_bytes()).hexdigest(),
    )


async def _create_target(owner_id: UUID, *, node: str = "linked-list-insertion") -> UUID:
    assert TEST_DATABASE_URL is not None
    engine = create_database_engine(TEST_DATABASE_URL)
    try:
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as db:
            unit = LearningUnit(
                user_id=owner_id, knowledge_point_id=node, title="动画 API", status="ready",
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


def _headers(csrf: str, key: str | None = None) -> dict[str, str]:
    return {
        "X-CSRF-Token": csrf, "Origin": "https://testserver",
        "Idempotency-Key": key or uuid4().hex,
    }


def _request(value: int) -> dict[str, object]:
    return {
        "template_id": "linked-list-insertion", "template_version": "1.0.0",
        "scene_version": 1, "parameters": {"values": [1, 3, 5], "index": 1, "value": value},
    }


def test_create_cache_hit_idempotency_owner_csrf_and_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    cache = AnimationCache(tmp_path, renderer=_fake_renderer)
    monkeypatch.setattr("app.api.animation_jobs.AnimationCache", lambda: cache)
    hit = cache.resolve("linked-list-insertion", _request(7)["parameters"])
    assert hit.cache_hit is False

    with TestClient(app, base_url="https://testserver") as first:
        auth = first.post("/api/auth/guest").json()
        unit_id = asyncio.run(_create_target(UUID(auth["user"]["id"])))
        path = f"/api/learning-units/{unit_id}/animations"
        headers = _headers(auth["csrf_token"])
        completed = first.post(path, json=_request(7), headers=headers)
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "succeeded"
        media_id = completed.json()["media_id"]
        repeated = first.post(path, json=_request(7), headers=headers)
        assert repeated.status_code == 200 and repeated.json() == completed.json()
        assert first.get(f"/api/animation-jobs/{completed.json()['id']}").json() == completed.json()
        queued = first.post(path, json=_request(8), headers=_headers(auth["csrf_token"]))
        assert queued.status_code == 202 and queued.json()["status"] == "queued"
        assert queued.json()["last_event_id"] == 1
        assert first.post(path, json=_request(7), headers=headers).json() == completed.json()
        conflict = first.post(path, json=_request(8), headers=headers)
        assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
        invalid = first.post(path, json=_request(101), headers=_headers(auth["csrf_token"]))
        assert invalid.status_code == 422 and invalid.json()["code"] == "VALIDATION_ERROR"
        csrf_fail = first.post(path, json=_request(7), headers={"Idempotency-Key": uuid4().hex})
        assert csrf_fail.status_code == 403

        with TestClient(app, base_url="https://testserver") as second:
            second_auth = second.post("/api/auth/guest").json()
            assert second.get(f"/api/animation-jobs/{completed.json()['id']}").status_code == 404
            assert second.post(
                f"/api/animation-jobs/{completed.json()['id']}/cancel",
                headers=_headers(second_auth["csrf_token"]),
            ).status_code == 404
            assert second.post(
                f"/api/animation-jobs/{completed.json()['id']}/retry",
                headers=_headers(second_auth["csrf_token"]),
            ).status_code == 404
            second_unit = asyncio.run(_create_target(UUID(second_auth["user"]["id"])))
            second_hit = second.post(
                f"/api/learning-units/{second_unit}/animations", json=_request(7),
                headers=_headers(second_auth["csrf_token"]),
            )
            assert second_hit.status_code == 200 and second_hit.json()["media_id"] == media_id
            assert second.post(path, json=_request(7), headers=_headers(
                second_auth["csrf_token"]
            )).status_code == 404

    async def verify_bindings() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine)
            async with sessions() as db:
                media = await db.get(AnimationMedia, UUID(media_id))
                assert media is not None
                bindings = (await db.scalars(select(AnimationResourceBinding).where(
                    AnimationResourceBinding.media_id == media.id,
                ))).all()
                assert len(bindings) == 2
                assert len({binding.user_id for binding in bindings}) == 2
        finally:
            await engine.dispose()

    asyncio.run(verify_bindings())


def test_cancel_publish_race_retry_and_idempotency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    cache = AnimationCache(tmp_path, renderer=_fake_renderer)
    monkeypatch.setattr("app.api.animation_jobs.AnimationCache", lambda: cache)
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])
        unit_id = asyncio.run(_create_target(owner))
        path = f"/api/learning-units/{unit_id}/animations"
        created = client.post(path, json=_request(15), headers=_headers(auth["csrf_token"]))
        assert created.status_code == 202
        job_id = UUID(created.json()["id"])

        async def claim() -> object:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                return await claim_animation_job(async_sessionmaker(engine))
            finally:
                await engine.dispose()

        lease = asyncio.run(claim())
        assert lease is not None and lease.job_id == job_id
        media = cache.resolve("linked-list-insertion", _request(15)["parameters"])
        cancel_headers = _headers(auth["csrf_token"])
        cancelled = client.post(f"/api/animation-jobs/{job_id}/cancel", headers=cancel_headers)
        assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
        same = client.post(f"/api/animation-jobs/{job_id}/cancel", headers=cancel_headers)
        assert same.status_code == 200 and same.json() == cancelled.json()
        assert client.post(
            f"/api/animation-jobs/{job_id}/cancel",
            headers=_headers(auth["csrf_token"]),
        ).status_code == 409

        async def late_publish() -> bool:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                sessions = async_sessionmaker(engine)
                return await publish_animation_job(sessions, lease, cache=cache, media=media)
            finally:
                await engine.dispose()

        assert not asyncio.run(late_publish())
        key = _headers(auth["csrf_token"])
        retry = client.post(f"/api/animation-jobs/{job_id}/retry", headers=key)
        assert retry.status_code == 202 and retry.json()["status"] == "queued"
        assert retry.json()["retry_of"] == str(job_id)
        replay = client.post(f"/api/animation-jobs/{job_id}/retry", headers=key)
        assert replay.status_code == 200 and replay.json() == retry.json()
        assert client.post(f"/api/animation-jobs/{job_id}/cancel", headers=key).status_code == 409

        other = client.post(path, json=_request(16), headers=_headers(auth["csrf_token"]))
        assert other.status_code == 202
        other_id = UUID(other.json()["id"])
        reused_cancel_key = client.post(
            f"/api/animation-jobs/{other_id}/cancel", headers=cancel_headers,
        )
        assert reused_cancel_key.status_code == 409
        assert reused_cancel_key.json()["code"] == "IDEMPOTENCY_CONFLICT"
        other_lease = asyncio.run(claim())
        assert other_lease is not None
        # A successful publish makes cancellation lose the same row-lock race.
        other_media = cache.resolve("linked-list-insertion", other_lease.parameters)
        async def publish_other() -> bool:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                return await publish_animation_job(
                    async_sessionmaker(engine), other_lease, cache=cache, media=other_media,
                )
            finally:
                await engine.dispose()

        assert asyncio.run(publish_other())
        assert client.post(
            f"/api/animation-jobs/{other_lease.job_id}/cancel",
            headers=_headers(auth["csrf_token"]),
        ).status_code == 409
        assert other_lease.job_id in {other_id, UUID(retry.json()["id"])}


def test_concurrent_cancel_and_publish_commit_only_one_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    cache = AnimationCache(tmp_path, renderer=_fake_renderer)
    monkeypatch.setattr("app.api.animation_jobs.AnimationCache", lambda: cache)
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])
        unit_id = asyncio.run(_create_target(owner))
        created = client.post(
            f"/api/learning-units/{unit_id}/animations", json=_request(25),
            headers=_headers(auth["csrf_token"]),
        )
        assert created.status_code == 202
        job_id = UUID(created.json()["id"])

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            lease = await claim_animation_job(sessions)
            assert lease is not None and lease.job_id == job_id
            media = cache.resolve(lease.template_id, lease.parameters)

            async def cancel() -> AnimationJob:
                async with sessions() as db:
                    return await cancel_animation_job(
                        db, owner_id=owner, job_id=job_id,
                        idempotency_key=uuid4().hex,
                    )

            published, cancelled = await asyncio.gather(
                publish_animation_job(sessions, lease, cache=cache, media=media),
                cancel(), return_exceptions=True,
            )
            async with sessions() as db:
                job = await db.get(AnimationJob, job_id)
                assert job is not None
                events = (await db.scalars(select(AnimationJobEvent).where(
                    AnimationJobEvent.job_id == job_id,
                    AnimationJobEvent.event_type.in_(("succeeded", "cancelled")),
                ))).all()
                bindings = (await db.scalars(select(AnimationResourceBinding).where(
                    AnimationResourceBinding.job_id == job_id,
                ))).all()
                assert len(events) == 1
                if job.status == "succeeded":
                    assert published is True and isinstance(cancelled, AnimationJobStateConflict)
                    assert len(bindings) == 1
                else:
                    assert job.status == "cancelled" and published is False
                    assert isinstance(cancelled, AnimationJob)
                    assert bindings == []
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_concurrent_cancel_key_is_unique_across_owner_jobs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(
        "app.api.animation_jobs.AnimationCache",
        lambda: AnimationCache(tmp_path, renderer=_fake_renderer),
    )
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])
        unit_id = asyncio.run(_create_target(owner))
        job_ids = []
        for value in (30, 31):
            created = client.post(
                f"/api/learning-units/{unit_id}/animations", json=_request(value),
                headers=_headers(auth["csrf_token"]),
            )
            assert created.status_code == 202
            job_ids.append(UUID(created.json()["id"]))

    async def exercise() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            key = uuid4().hex

            async def cancel(job_id: UUID) -> AnimationJob:
                async with sessions() as db:
                    return await cancel_animation_job(
                        db, owner_id=owner, job_id=job_id, idempotency_key=key,
                    )

            results = await asyncio.gather(
                *(cancel(job_id) for job_id in job_ids), return_exceptions=True,
            )
            assert sum(isinstance(value, AnimationJob) for value in results) == 1
            assert sum(isinstance(value, AnimationIdempotencyConflict) for value in results) == 1
            async with sessions() as db:
                jobs = (await db.scalars(select(AnimationJob).where(
                    AnimationJob.id.in_(job_ids),
                ))).all()
                assert {job.status for job in jobs} == {"cancelled", "queued"}
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_failed_job_retries_as_new_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(
        "app.api.animation_jobs.AnimationCache",
        lambda: AnimationCache(tmp_path, renderer=_fake_renderer),
    )
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        unit_id = asyncio.run(_create_target(UUID(auth["user"]["id"])))
        created = client.post(
            f"/api/learning-units/{unit_id}/animations", json=_request(40),
            headers=_headers(auth["csrf_token"]),
        )
        assert created.status_code == 202
        job_id = UUID(created.json()["id"])

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
        failed = client.get(f"/api/animation-jobs/{job_id}")
        assert failed.status_code == 200 and failed.json()["status"] == "failed"
        assert failed.json()["error"]["code"] == "RENDER_UNAVAILABLE"
        retry = client.post(
            f"/api/animation-jobs/{job_id}/retry", headers=_headers(auth["csrf_token"]),
        )
        assert retry.status_code == 202 and retry.json()["retry_of"] == str(job_id)
        assert retry.json()["id"] != str(job_id)
        assert client.get(f"/api/animation-jobs/{job_id}").json() == failed.json()


@pytest.mark.skipif(os.getenv("EDUMIND_DOCKER_TESTS") != "1", reason="needs Docker")
def test_cancelling_running_job_stops_its_container_within_ten_seconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    started = threading.Event()
    names: list[str] = []

    def blocking_renderer(
        template_id: str, parameters: dict[str, object], *, work_root: Path,
        container_name: str,
    ) -> RenderedCandidate:
        command = [
            "docker", "run", "-d", "--rm", "--name", container_name,
            "--network", "none", "--read-only", "--user", "10001:10001",
            IMAGE, "python", "-c", "import time; time.sleep(60)",
        ]
        launched = subprocess.run(command, capture_output=True, timeout=15, check=False)
        assert launched.returncode == 0, launched.stderr.decode()
        names.append(container_name)
        started.set()
        try:
            while True:
                state = subprocess.run(
                    ["docker", "inspect", "--format", "{{.State.Running}}", container_name],
                    capture_output=True, timeout=5, check=False,
                )
                if state.returncode != 0:
                    raise RenderError("RENDER_UNAVAILABLE")
                time.sleep(0.2)
        finally:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=10, check=False,
            )

    cache = AnimationCache(tmp_path, renderer=blocking_renderer)
    monkeypatch.setattr("app.api.animation_jobs.AnimationCache", lambda: cache)
    with TestClient(app, base_url="https://testserver") as client:
        auth = client.post("/api/auth/guest").json()
        owner = UUID(auth["user"]["id"])
        unit_id = asyncio.run(_create_target(owner))
        created = client.post(
            f"/api/learning-units/{unit_id}/animations",
            json=_request(22), headers=_headers(auth["csrf_token"]),
        )
        assert created.status_code == 202
        job_id = UUID(created.json()["id"])

        async def exercise() -> None:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                sessions = async_sessionmaker(engine, expire_on_commit=False)
                worker = asyncio.create_task(run_one_animation_job(sessions, cache=cache))
                assert await asyncio.wait_for(asyncio.to_thread(started.wait), timeout=10)
                clock = time.monotonic()
                async with sessions() as db:
                    cancelled = await cancel_animation_job(
                        db, owner_id=owner, job_id=job_id,
                        idempotency_key=uuid4().hex,
                    )
                    assert cancelled.status == "cancelled"
                assert await asyncio.wait_for(worker, timeout=12) == job_id
                assert time.monotonic() - clock < 10
                async with sessions() as db:
                    final = await db.get(AnimationJob, job_id)
                    assert final is not None and final.status == "cancelled"
                    assert final.media_id is None
                    assert (await db.scalars(select(AnimationResourceBinding).where(
                        AnimationResourceBinding.job_id == job_id,
                    ))).all() == []
            finally:
                await engine.dispose()

        asyncio.run(exercise())
        assert names
        assert subprocess.run(
            ["docker", "inspect", names[0]], capture_output=True, timeout=5,
            check=False,
        ).returncode != 0
