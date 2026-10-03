import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import UUID, uuid4

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.learning import GeneratedResource, LearningScene, LearningUnit
from app.services.animation_jobs import reserve_animation_job
from app.services.animation_worker import run_one_animation_job

BASE = os.getenv("EDUMIND_E2E_BASE_URL", "http://127.0.0.1:4175")
pool = ThreadPoolExecutor(max_workers=1)


async def seed(owner: UUID, node: str) -> tuple[UUID, UUID]:
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            unit = LearningUnit(
                user_id=owner, knowledge_point_id=node, title="浏览器链表课堂", status="ready"
            )
            db.add(unit)
            await db.flush()
            scene = LearningScene(
                learning_unit_id=unit.id,
                scene_key="intro",
                scene_order=1,
                scene_type="first_learning",
                version=1,
                generation_status="complete",
                review_status="passed",
            )
            db.add(scene)
            await db.flush()
            db.add(
                GeneratedResource(
                    user_id=owner,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    knowledge_point_id=node,
                    resource_type="explanation",
                    content={"markdown": "链表节点通过指针相连。"},
                    review_status="passed",
                    version=1,
                    published_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            return unit.id, scene.id
    finally:
        await engine.dispose()


async def reserve(owner: UUID, unit: UUID, scene: UUID) -> UUID:
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            result = await reserve_animation_job(
                db,
                owner_id=owner,
                learning_unit_id=unit,
                scene_id=scene,
                scene_version=1,
                template_id="linked-list-deletion",
                template_version="1.0.0",
                parameters={"values": [1, 3, 5, 7], "index": 2},
                idempotency_key=uuid4().hex,
            )
            return result.job.id
    finally:
        await engine.dispose()


async def render(expected: UUID) -> None:
    engine = create_database_engine()
    try:
        processed = await run_one_animation_job(async_sessionmaker(engine, expire_on_commit=False))
        assert processed == expected, (processed, expected)
    finally:
        await engine.dispose()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(
        headless=True, args=["--autoplay-policy=no-user-gesture-required"]
    )
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    creates = []
    page.on(
        "request",
        lambda request: creates.append(request.url)
        if request.method == "POST" and request.url.endswith("/animations")
        else None,
    )
    page.goto(BASE)
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except PlaywrightTimeoutError:
        page.wait_for_selector("h1", timeout=10000)
    auth = page.evaluate(
        "async () => {"
        " let response = await fetch('/api/auth/session');"
        " if (response.status === 401)"
        " response = await fetch('/api/auth/guest', {method: 'POST'});"
        " return {status: response.status, body: await response.json()};"
        " }"
    )
    assert auth["status"] in (200, 201), auth
    owner = UUID(auth["body"]["user"]["id"])
    first_unit, _ = pool.submit(lambda: asyncio.run(seed(owner, "linked-list-insertion"))).result()
    page.evaluate(
        '(unit) => sessionStorage.setItem("edumind:last-learning-unit", unit)', str(first_unit)
    )
    page.reload()
    page.get_by_test_id("animation-panel").wait_for(timeout=15000)
    assert len(creates) == 0, creates
    page.get_by_test_id("request-animation").click()
    stored_job = (
        "JSON.parse(sessionStorage.getItem('edumind:animation:' + "
        "sessionStorage.getItem('edumind:last-learning-unit')) || '{}').jobId"
    )
    page.wait_for_function(
        f"() => {stored_job}",
        timeout=15000,
    )
    first_job = UUID(page.evaluate(f"() => {stored_job}"))
    first_status = page.get_by_test_id("animation-panel").inner_text()
    if "动画已就绪" not in first_status:
        pool.submit(lambda: asyncio.run(render(first_job))).result()
    page.get_by_test_id("animation-video").wait_for(timeout=30000)
    page.wait_for_function(
        "document.querySelector('[data-testid=animation-video]').readyState >= 1", timeout=30000
    )
    page.get_by_test_id("animation-video").evaluate("(video) => video.play()")
    page.wait_for_timeout(1100)
    video = page.get_by_test_id("animation-video").evaluate(
        "(v) => ({duration:v.duration,currentTime:v.currentTime,error:v.error && v.error.code})"
    )
    assert video["duration"] == 36 and video["currentTime"] > 0 and video["error"] is None, video
    page.locator("video track").wait_for(state="attached", timeout=10000)
    assert page.locator("video track").get_attribute("src").startswith("blob:")
    assert len(creates) == 1, creates
    page.reload()
    page.get_by_test_id("animation-video").wait_for(timeout=15000)
    assert len(creates) == 1, creates

    second_unit, second_scene = pool.submit(
        lambda: asyncio.run(seed(owner, "linked-list-deletion"))
    ).result()
    old_job = pool.submit(lambda: asyncio.run(reserve(owner, second_unit, second_scene))).result()
    page.evaluate(
        "({unit, job}) => {"
        " sessionStorage.setItem('edumind:last-learning-unit', unit);"
        " sessionStorage.setItem('edumind:animation:' + unit, JSON.stringify({"
        " requestKey:'preseeded-test-key',"
        " request:{template_id:'linked-list-deletion',template_version:'1.0.0',"
        " scene_version:1,parameters:{values:[1,3,5,7],index:2}},jobId:job"
        " })); }",
        {"unit": str(second_unit), "job": str(old_job)},
    )
    page.reload()
    page.get_by_test_id("cancel-animation").wait_for(timeout=15000)
    assert len(creates) == 1, creates
    page.get_by_test_id("cancel-animation").click()
    page.get_by_test_id("retry-animation").wait_for(timeout=15000)
    page.get_by_test_id("retry-animation").click()
    page.get_by_test_id("cancel-animation").wait_for(timeout=15000)
    retry_job = UUID(
        page.evaluate(
            "unit => JSON.parse(sessionStorage.getItem('edumind:animation:' + unit)).jobId",
            str(second_unit),
        )
    )
    assert retry_job != old_job
    context.set_offline(True)
    page.wait_for_timeout(2000)
    pool.submit(lambda: asyncio.run(render(retry_job))).result()
    context.set_offline(False)
    page.get_by_test_id("animation-video").wait_for(timeout=30000)
    assert len(creates) == 1, creates
    status = page.get_by_test_id("animation-panel").inner_text()
    assert "动画已就绪" in status, status
    print(
        json.dumps(
            {
                "create_posts": len(creates),
                "first_job": str(first_job),
                "first_video": video,
                "retry_job": str(retry_job),
                "offline_recovered": True,
            },
            ensure_ascii=False,
        )
    )
    browser.close()
pool.shutdown()
