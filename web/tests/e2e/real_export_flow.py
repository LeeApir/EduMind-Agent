"""Real HTTP export check with isolated PostgreSQL and reviewed media bytes."""

import asyncio
import hashlib
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID, uuid4

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
WEB = ROOT / "web"
API = "http://127.0.0.1:8002"
FRONTEND = "http://127.0.0.1:4176"
MP4 = b"\x00\x00\x00\x18ftypisom T029 reviewed download bytes"
SRT = "1\n00:00:00,000 --> 00:00:01,000\n链表插入\n".encode()


def ready(url: str) -> None:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1):
                return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError(f"Server did not start: {url}")


def stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


async def seed(owner: UUID) -> tuple[UUID, UUID, UUID, tuple[Path, Path]]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import create_database_engine
    from app.models.animation import AnimationMedia, AnimationResourceBinding
    from app.models.learning import GeneratedResource, LearningScene, LearningUnit
    from app.services.animation_cache import AnimationCache
    from app.services.animation_jobs import reserve_animation_job

    cache = AnimationCache()
    objects = cache.root / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    mp4_path = objects / f"{hashlib.sha256(MP4).hexdigest()}.mp4"
    srt_path = objects / f"{hashlib.sha256(SRT).hexdigest()}.srt"
    mp4_path.write_bytes(MP4)
    srt_path.write_bytes(SRT)
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            unit = LearningUnit(
                user_id=owner, knowledge_point_id="linked-list-insertion",
                title="T029 导出浏览器验收", status="ready",
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
                content={"markdown": "T029 当前已审核链表讲解。"},
                review_status="passed", version=1,
                published_at=datetime.now(timezone.utc),
            ))
            await db.commit()
            reservation = await reserve_animation_job(
                db, owner_id=owner, learning_unit_id=unit.id, scene_id=scene.id,
                scene_version=1, template_id="linked-list-insertion",
                template_version="1.0.0",
                parameters={"values": [1, 3, 5], "index": 1, "value": 4},
                idempotency_key=uuid4().hex,
            )
            job = reservation.job
            media = await db.scalar(select(AnimationMedia).where(
                AnimationMedia.cache_key == job.cache_key
            ))
            if media is None:
                media = AnimationMedia(
                    cache_key=job.cache_key, template_id=job.template_id,
                    template_version=job.template_version,
                    review_rule_version=job.review_rule_version,
                    source_sha256=job.source_sha256, image_digest=job.image_digest,
                    font_digest=job.font_digest,
                    renderer_config_sha256=job.renderer_config_sha256,
                    subtitle_version=job.subtitle_version,
                    mp4_sha256=hashlib.sha256(MP4).hexdigest(),
                    srt_sha256=hashlib.sha256(SRT).hexdigest(),
                    mp4_size=len(MP4), srt_size=len(SRT), duration_seconds=36,
                    review_status="passed",
                )
                db.add(media)
                await db.flush()
            job.status = "succeeded"
            job.attempt = 1
            job.progress = 1
            job.media_id = media.id
            await db.flush()
            db.add(AnimationResourceBinding(
                user_id=owner, job_id=job.id, media_id=media.id,
                learning_unit_id=unit.id, scene_id=scene.id, scene_version=1,
            ))
            await db.commit()
            return unit.id, job.id, media.id, (mp4_path, srt_path)
    finally:
        await engine.dispose()


def run() -> None:
    if not os.getenv("EDUMIND_TEST_DATABASE_URL"):
        raise RuntimeError("An isolated PostgreSQL URL is required")
    backend_env = {**os.environ, "EDUMIND_DATABASE_URL": os.environ["EDUMIND_TEST_DATABASE_URL"]}
    web_env = {**os.environ, "EDUMIND_API_PROXY_TARGET": API}
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"],
        cwd=BACKEND, env=backend_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    web = subprocess.Popen(
        ["pnpm", "dev", "--host", "127.0.0.1", "--port", "4176"],
        cwd=WEB, env=web_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    paths: tuple[Path, Path] | None = None
    try:
        ready(API + "/health")
        ready(FRONTEND)
        sys.path.insert(0, str(BACKEND))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(accept_downloads=True)
                auth = context.request.post(FRONTEND + "/api/auth/guest")
                assert auth.status == 201, auth.text()
                owner = UUID(auth.json()["user"]["id"])
                with ThreadPoolExecutor(max_workers=1) as pool:
                    unit_id, job_id, media_id, paths = pool.submit(
                        lambda: asyncio.run(seed(owner))
                    ).result()
                page = context.new_page()
                page.add_init_script(
                    f"sessionStorage.setItem('edumind:last-learning-unit', '{unit_id}');"
                    f"sessionStorage.setItem('edumind:animation:{unit_id}', JSON.stringify({{"
                    f"requestKey:'saved', jobId:'{job_id}', request:{{"
                    "template_id:'linked-list-insertion',"
                    "template_version:'1.0.0',scene_version:1,"
                    "parameters:{values:[1,3,5],index:1,value:4}}}));"
                )
                posts = []
                page.on(
                    "request",
                    lambda request: posts.append(request.url)
                    if request.method == "POST" else None,
                )
                page.goto(FRONTEND)
                expect(page.get_by_test_id("download-notes")).to_be_enabled()
                expect(page.get_by_test_id("download-mp4")).to_be_visible()
                for test_id, extension, expected in (
                    ("download-mp4", "mp4", MP4),
                    ("download-srt", "srt", SRT),
                ):
                    with page.expect_download() as event:
                        page.get_by_test_id(test_id).click()
                    download = event.value
                    assert download.suggested_filename == f"animation-{media_id}.{extension}"
                    assert Path(download.path()).read_bytes() == expected
                with page.expect_download() as event:
                    page.get_by_test_id("download-notes").click()
                notes = event.value
                assert notes.suggested_filename == f"learning-notes-{unit_id}.md"
                assert "T029 当前已审核链表讲解。" in Path(notes.path()).read_text()
                assert not any("/animations" in url or "/learning-sessions" in url for url in posts)
                print("Real HTTP Markdown/MP4/SRT browser downloads passed", flush=True)
            finally:
                browser.close()
    finally:
        stop(web)
        stop(backend)
        if paths:
            for path in paths:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
