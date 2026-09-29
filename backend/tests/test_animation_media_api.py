"""Authorized MP4 byte ranges and SRT reads from private reviewed cache."""

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
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
from app.services.animation_renderer import RenderedCandidate
from app.services.animation_worker import run_one_animation_job

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def _fake_renderer(
    template_id: str, parameters: dict[str, object], *, work_root: Path,
    container_name: str,
) -> RenderedCandidate:
    assert template_id == "linked-list-insertion"
    attempt = Path(tempfile.mkdtemp(prefix="media-fake-", dir=work_root))
    mp4, srt = attempt / "scene.mp4", attempt / "scene.srt"
    mp4.write_bytes(b"\x00\x00\x00\x18ftypisom" + json.dumps(parameters, sort_keys=True).encode())
    srt.write_text(srt_for_insertion(), encoding="utf-8")
    return RenderedCandidate(
        attempt, mp4, srt, 36.0,
        hashlib.sha256(mp4.read_bytes()).hexdigest(),
        hashlib.sha256(srt.read_bytes()).hexdigest(),
    )


def _unexpected_renderer(*_args: object, **_kwargs: object) -> RenderedCandidate:
    raise AssertionError("A media download must not render again.")


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
                title="Media", status="ready",
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


def _create(client: TestClient, value: int) -> tuple[dict[str, object], UUID, UUID]:
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
            "X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": uuid4().hex,
            "Origin": "https://testserver",
        },
    )
    assert created.status_code == 202, created.text
    return auth, unit_id, UUID(created.json()["id"])


def _finish(job_id: UUID, cache: AnimationCache) -> UUID:
    assert TEST_DATABASE_URL is not None

    async def finish() -> UUID:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            assert await run_one_animation_job(sessions, cache=cache) == job_id
            async with sessions() as db:
                job = await db.get(AnimationJob, job_id)
                assert job is not None and job.status == "succeeded"
                assert job.media_id is not None
                return job.media_id
        finally:
            await engine.dispose()

    return asyncio.run(finish())


def test_mp4_ranges_srt_headers_owner_and_unbound_media(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    cache = AnimationCache(tmp_path, renderer=_fake_renderer)
    monkeypatch.setattr("app.api.animation_jobs.AnimationCache", lambda: cache)
    monkeypatch.setattr("app.api.animation_media.AnimationCache", lambda: cache)
    with TestClient(app, base_url="https://testserver") as client:
        _, unit_id, job_id = _create(client, 61)
        assert client.get(f"/api/animation-media/{uuid4()}/mp4").status_code == 404
        media_id = _finish(job_id, cache)
        monkeypatch.setattr(cache, "renderer", _unexpected_renderer)
        mp4_url = f"/api/animation-media/{media_id}/mp4"
        srt_url = f"/api/animation-media/{media_id}/srt"
        full = client.get(mp4_url)
        assert full.status_code == 200
        assert full.content.startswith(b"\x00\x00\x00\x18ftypisom")
        assert full.headers["content-type"] == "video/mp4"
        assert full.headers["accept-ranges"] == "bytes"
        assert full.headers["cache-control"] == "private, no-store"
        assert full.headers["x-content-type-options"] == "nosniff"
        assert full.headers["content-disposition"].startswith("inline;")
        assert "Users/" not in str(full.headers)
        assert int(full.headers["content-length"]) == len(full.content)
        assert full.headers["x-animation-media-id"] == str(media_id)
        assert full.headers["x-animation-template-id"] == "linked-list-insertion"
        assert full.headers["x-animation-template-version"] == "1.0.0"
        assert full.headers["x-animation-subtitle-version"] == "srt-v1"
        assert full.headers["x-animation-review-version"]
        assert full.headers["x-animation-generated-by"] == "reviewed-manim-template"
        assert hashlib.sha256(full.content).hexdigest() == full.headers[
            "x-animation-content-sha256"
        ]
        datetime.fromisoformat(full.headers["x-animation-published-at"])
        first = client.get(mp4_url, headers={"Range": "bytes=0-7"})
        assert first.status_code == 206 and first.content == full.content[:8]
        assert first.headers["content-range"] == f"bytes 0-7/{len(full.content)}"
        assert first.headers["x-animation-content-sha256"] == full.headers[
            "x-animation-content-sha256"
        ]
        assert client.get(mp4_url, headers={"Range": "bytes=8-"}).content == full.content[8:]
        assert client.get(mp4_url, headers={"Range": "bytes=-5"}).content == full.content[-5:]
        for bad in (
            "bytes=99999-", "bytes=7-2", "bytes=0-1,3-4", "bytes=-0",
            "bytes=0-" + "9" * 1000,
        ):
            invalid = client.get(mp4_url, headers={"Range": bad})
            assert invalid.status_code == 416
            assert invalid.headers["content-range"] == f"bytes */{len(full.content)}"
        subtitle = client.get(srt_url)
        assert subtitle.status_code == 200 and subtitle.content == srt_for_insertion().encode()
        assert subtitle.headers["content-type"].startswith("application/x-subrip")
        assert subtitle.headers["x-animation-media-id"] == full.headers[
            "x-animation-media-id"
        ]
        for field in (
            "template-id", "template-version", "subtitle-version", "review-version",
            "generated-by", "published-at",
        ):
            assert subtitle.headers[f"x-animation-{field}"] == full.headers[
                f"x-animation-{field}"
            ]
        assert hashlib.sha256(subtitle.content).hexdigest() == subtitle.headers[
            "x-animation-content-sha256"
        ]
        srt_download = client.get(srt_url + "?download=true")
        assert srt_download.content == subtitle.content
        assert srt_download.headers["content-disposition"] == (
            f'attachment; filename="animation-{media_id}.srt"'
        )
        download = client.get(mp4_url + "?download=true&filename=../../private.env")
        assert download.content == full.content
        assert download.headers["content-disposition"] == (
            f'attachment; filename="animation-{media_id}.mp4"'
        )
        assert client.get("/api/animation-media/not-a-uuid/mp4").status_code == 422
        assert client.get(f"/api/learning-units/{unit_id}").status_code == 200

        with TestClient(app, base_url="https://testserver") as foreign:
            foreign.post("/api/auth/guest")
            assert foreign.get(mp4_url).status_code == 404
            assert foreign.get(srt_url).status_code == 404
        with TestClient(app, base_url="https://testserver") as anonymous:
            assert anonymous.get(mp4_url).status_code == 401

    async def orphan() -> UUID:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                original = await db.get(AnimationMedia, media_id)
                assert original is not None
                orphan = AnimationMedia(
                    cache_key="f" * 64, template_id=original.template_id,
                    template_version=original.template_version,
                    review_rule_version=original.review_rule_version,
                    source_sha256=original.source_sha256,
                    image_digest=original.image_digest,
                    font_digest=original.font_digest,
                    renderer_config_sha256=original.renderer_config_sha256,
                    subtitle_version=original.subtitle_version,
                    mp4_sha256=original.mp4_sha256, srt_sha256=original.srt_sha256,
                    mp4_size=original.mp4_size, srt_size=original.srt_size,
                    duration_seconds=original.duration_seconds, review_status="passed",
                )
                db.add(orphan)
                await db.commit()
                return orphan.id
        finally:
            await engine.dispose()

    orphan_id = asyncio.run(orphan())
    with TestClient(app, base_url="https://testserver") as client:
        client.post("/api/auth/guest")
        assert client.get(f"/api/animation-media/{orphan_id}/mp4").status_code == 404


def test_corrupt_or_missing_bound_bytes_are_unavailable_without_harming_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    _clean_jobs()
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    cache = AnimationCache(tmp_path, renderer=_fake_renderer)
    monkeypatch.setattr("app.api.animation_jobs.AnimationCache", lambda: cache)
    monkeypatch.setattr("app.api.animation_media.AnimationCache", lambda: cache)
    with TestClient(app, base_url="https://testserver") as client:
        _, unit_id, job_id = _create(client, 62)
        media_id = _finish(job_id, cache)
        async def hashes() -> tuple[str, str]:
            engine = create_database_engine(TEST_DATABASE_URL)
            try:
                async with async_sessionmaker(engine)() as db:
                    media = await db.get(AnimationMedia, media_id)
                    assert media is not None
                    return media.mp4_sha256, media.srt_sha256
            finally:
                await engine.dispose()

        mp4_hash, srt_hash = asyncio.run(hashes())
        mp4 = tmp_path / "objects" / f"{mp4_hash}.mp4"
        srt = tmp_path / "objects" / f"{srt_hash}.srt"
        original = tmp_path / "objects" / "saved.mp4"
        mp4.rename(original)
        mp4.symlink_to(original)
        assert client.get(f"/api/animation-media/{media_id}/mp4").status_code == 503
        mp4.unlink()
        original.rename(mp4)
        mp4.chmod(0o644)
        original_bytes = mp4.read_bytes()
        mp4.write_bytes(b"corrupt")
        unavailable = client.get(f"/api/animation-media/{media_id}/mp4")
        assert unavailable.status_code == 503
        assert unavailable.json()["code"] == "MEDIA_UNAVAILABLE"
        assert "Request a new animation job" in unavailable.json()["message"]
        mp4.write_bytes(original_bytes)
        srt.unlink()
        assert client.get(f"/api/animation-media/{media_id}/srt").status_code == 503
        assert client.get(f"/api/animation-media/{media_id}/mp4").content == original_bytes
        assert client.get(f"/api/learning-units/{unit_id}").status_code == 200
