"""Synthetic approvals and mock media verify export provenance and withdrawal policy."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from catalog_fixtures import approval_fixture, package_fixture
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_animation_media_api import _clean_jobs, _fake_renderer

from app.core.database import create_database_engine
from app.main import app
from app.models.animation import AnimationJob
from app.services.animation_cache import AnimationCache
from app.services.animation_worker import (
    claim_animation_job,
    publish_animation_job,
    run_one_animation_job,
)
from app.services.catalog_package import validate_package
from app.services.catalog_publication import publish_catalog, revoke_catalog

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="isolated PostgreSQL URL not set")


def test_catalog_notes_and_shared_media_owners_releases_and_late_publication(tmp_path, monkeypatch):
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    cache = AnimationCache(tmp_path, renderer=_fake_renderer)
    monkeypatch.setattr("app.api.animation_jobs.AnimationCache", lambda: cache)
    monkeypatch.setattr("app.api.animation_media.AnimationCache", lambda: cache)

    async def release():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                package = package_fixture()
                package.manifest["package_id"] = "export-" + uuid4().hex
                package = validate_package(package.payload())
                release = await publish_catalog(db, package, approval=approval_fixture(package),
                                                trusted_digest=package.digest)
                await db.commit()
                return str(release.id)
        finally:
            await engine.dispose()
    release_id, second_release = asyncio.run(release()), asyncio.run(release())

    def enroll(client, release, headers):
        result = client.post("/api/catalog/sessions", headers={**headers,
            "Idempotency-Key": uuid4().hex}, json={"release_id": release,
                                                   "node_id": "linked-list-insertion"})
        assert result.status_code == 201, result.text
        return result.json()["learning_unit_id"]

    async def revoke(release_id):
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine)() as db:
                await revoke_catalog(db, UUID(release_id))
                await db.commit()
        finally:
            await engine.dispose()

    with TestClient(app, base_url="https://testserver") as client:
        csrf = client.post("/api/auth/guest").json()["csrf_token"]
        headers = {"X-CSRF-Token": csrf}
        unit = enroll(client, release_id, headers)
        notes_path = f"/api/learning-units/{unit}/notes.md"
        assert "预设数组 vs 链表总结" not in client.get(notes_path).text
        resources = client.get(f"/api/learning-units/{unit}").json()["scenes"][0]["resources"]
        exercise = next(resource for resource in resources if resource["type"] == "exercise")
        score = client.post("/api/quiz-submissions", headers={**headers,
            "Idempotency-Key": uuid4().hex}, json={"resource_id": exercise["id"],
            "resource_version": 1, "answers": [{"question_id": "q1", "answer": "RAW_SECRET"}]})
        assert score.status_code == 200, score.text
        assert score.json()["profile_update_status"] == "no_change"
        client.post(f"/api/learning-units/{unit}/classroom", headers={**headers,
            "Idempotency-Key": uuid4().hex})
        assert client.post(f"/api/catalog/learning-units/{unit}/demo", headers={**headers,
            "Idempotency-Key": uuid4().hex, "If-Match-Classroom-Revision": "1"},
            json={"action": "begin"}).status_code == 200
        notes = client.get(notes_path)
        assert notes.status_code == 200 and "attachment" in notes.headers["Content-Disposition"]
        assert "人工审核课程包" in notes.text and r"TEST\_ONLY synthetic approval" in notes.text
        assert "内容 SHA256" in notes.text and "预设数组 vs 链表总结" in notes.text
        assert "RAW_SECRET" not in notes.text and "模型" not in notes.text
        assert r"TEST\_ONLY 1?" in notes.text and "本人错题摘要" in notes.text
        body = {"template_id": "linked-list-insertion", "template_version": "1.0.0",
                "scene_version": 1, "parameters": {"values": [1, 3, 5], "index": 1, "value": 61}}
        key = uuid4().hex
        request_headers = {**headers, "Idempotency-Key": key}
        response = client.post(f"/api/learning-units/{unit}/animations", json=body,
                               headers=request_headers)
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]

        async def finish():
            engine = create_database_engine(URL)
            try:
                sessions = async_sessionmaker(engine)
                assert await run_one_animation_job(sessions, cache=cache) == UUID(job_id)
                async with sessions() as db:
                    job = await db.get(AnimationJob, UUID(job_id))
                    assert job.status == "succeeded"
                    return str(job.media_id)
            finally:
                await engine.dispose()
        media_id = asyncio.run(finish())
        mp4, srt = f"/api/animation-media/{media_id}/mp4", f"/api/animation-media/{media_id}/srt"
        assert client.get(mp4, headers={"Range": "bytes=0-7"}).status_code == 206
        assert client.get(srt + "?download=true").status_code == 200
        with TestClient(app, base_url="https://testserver") as other:
            other.post("/api/auth/guest")
            assert other.get(notes_path).status_code == 404
            assert other.get(mp4).status_code == 404
        # A second approved course can authorize the same immutable public media bytes.
        second_unit = enroll(client, second_release, headers)
        second = client.post(f"/api/learning-units/{second_unit}/animations", json=body,
                            headers={**headers, "Idempotency-Key": uuid4().hex})
        assert second.status_code == 200 and second.json()["media_id"] == media_id
        # Start a different render; revoke before its publication CAS.
        late_body = {**body, "parameters": {"values": [1, 3, 5], "index": 1, "value": 17}}
        late = client.post(f"/api/learning-units/{unit}/animations", json=late_body,
                           headers={**headers, "Idempotency-Key": uuid4().hex})
        assert late.status_code == 202

        async def late_publication():
            engine = create_database_engine(URL)
            try:
                sessions = async_sessionmaker(engine)
                lease = await claim_animation_job(sessions)
                assert str(lease.job_id) == late.json()["id"]
                media = cache.resolve("linked-list-insertion", late_body["parameters"],
                                      container_name="catalog-late-test")
                async with sessions() as db:
                    await revoke_catalog(db, UUID(release_id))
                    await db.commit()
                assert not await publish_animation_job(sessions, lease, cache=cache, media=media)
                async with sessions() as db:
                    job = await db.get(AnimationJob, lease.job_id)
                    assert job.status == "failed" and job.media_id is None
                    assert job.error_code == "ANIMATION_TARGET_UNAVAILABLE"
            finally:
                await engine.dispose()
        asyncio.run(late_publication())
        for path in (notes_path, f"/api/animation-jobs/{job_id}",
                     f"/api/animation-jobs/{job_id}/events"):
            assert client.get(path).status_code == 404
        assert client.post(f"/api/learning-units/{unit}/animations", json=body,
                           headers=request_headers).status_code == 404
        assert client.post(f"/api/animation-jobs/{job_id}/retry", headers={**headers,
            "Idempotency-Key": uuid4().hex}).status_code == 404
        assert client.get(mp4).status_code == 200  # Still authorized via second course binding.
        asyncio.run(revoke(second_release))
        assert client.get(mp4).status_code == 404 and client.get(srt).status_code == 404
