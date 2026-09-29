"""Full MVP 0.3 browser journey against FastAPI, PostgreSQL and real template media."""

import asyncio
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
WEB = ROOT / "web"
API = "http://127.0.0.1:8003"
FRONTEND = "http://127.0.0.1:4177"


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


async def seed(owner: UUID) -> UUID:
    from datetime import datetime, timezone

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.agents.learning_resource_schema import RESOURCE_PROMPT_VERSION
    from app.agents.profile_schema import empty_transient_profile
    from app.core.database import create_database_engine
    from app.models.learning import GeneratedResource, LearningScene, LearningUnit
    from app.services.profile_updates import persist_profile_version

    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            unit = LearningUnit(
                user_id=owner, knowledge_point_id="linked-list-insertion",
                title="链表插入完整学习旅程", status="ready",
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
            now = datetime.now(timezone.utc)
            for kind, content in (
                ("explanation", {"markdown": "先保存后继，再连接新节点。"}),
                ("code", {"source": "new_node->next = current->next;"}),
                ("exercise", {"items": [{
                    "id": "q1", "question": "头插法复杂度？", "answer": "O(1)",
                    "explanation": "只需常数次指针修改。",
                }, {
                    "id": "q2", "question": "后继成员名？", "answer": "next",
                    "explanation": "next 指向后继。",
                }]}),
            ):
                db.add(GeneratedResource(
                    user_id=owner, learning_unit_id=unit.id, scene_id=scene.id,
                    knowledge_point_id="linked-list-insertion", resource_type=kind,
                    content=content, review_status="passed", version=1,
                    published_at=now, generation_metadata={
                        "model_id": "stage-fixture", "prompt_version": RESOURCE_PROMPT_VERSION,
                    },
                ))
            await db.commit()
            await persist_profile_version(
                db, owner_id=owner,
                profile=empty_transient_profile("想理解链表插入"),
            )
            return unit.id
    finally:
        await engine.dispose()


def run() -> None:
    if not os.getenv("EDUMIND_TEST_DATABASE_URL"):
        raise RuntimeError("An isolated PostgreSQL URL is required")
    backend_env = {**os.environ, "EDUMIND_DATABASE_URL": os.environ["EDUMIND_TEST_DATABASE_URL"]}
    web_env = {**os.environ, "EDUMIND_API_PROXY_TARGET": API}
    backend = subprocess.Popen(
        [sys.executable, "../web/tests/e2e/real_stage_backend.py"],
        cwd=BACKEND, env=backend_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    web = subprocess.Popen(
        ["pnpm", "dev", "--host", "127.0.0.1", "--port", "4177"],
        cwd=WEB, env=web_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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
                    unit_id = pool.submit(
                        lambda: asyncio.run(seed(owner))
                    ).result()
                page = context.new_page()
                page.add_init_script(
                    f"sessionStorage.setItem('edumind:last-learning-unit', '{unit_id}')"
                )
                posts: list[str] = []
                page.on(
                    "request", lambda request: posts.append(request.url)
                    if request.method == "POST" else None,
                )
                page.goto(FRONTEND)
                expect(page.get_by_test_id("explanation-tab")).to_contain_text("先保存后继")
                expect(page.get_by_test_id("mode-tag")).to_contain_text("专注模式")
                page.get_by_role("button", name="练习", exact=True).click()
                page.locator("#answer-q1").fill("O(1)")
                page.locator("#answer-q2").fill("next")
                page.get_by_role("button", name="提交练习").click()
                expect(page.get_by_label("最近一次练习提交回执")).to_contain_text("2 / 2")

                page.get_by_test_id("toggle-mode").click()
                expect(page.get_by_test_id("mode-tag")).to_contain_text("互动模式")
                page.get_by_test_id("role-beginner").click()
                expect(page.get_by_test_id("role-beginner")).to_have_attribute(
                    "aria-pressed", "true"
                )
                page.get_by_test_id("speech-input").fill("为什么要先保存后继？")
                page.get_by_test_id("send-speech").click()
                expect(page.get_by_test_id("transcript")).to_contain_text("为什么要先保存后继？")
                expect(page.get_by_test_id("transcript")).to_contain_text("两步连接不能颠倒")

                page.get_by_test_id("debate-question").fill("频繁随机访问时怎么选？")
                page.get_by_test_id("start-debate").click()
                try:
                    expect(page.get_by_test_id("debate-perspectives")).to_be_visible()
                except AssertionError:
                    print("debate stage", page.get_by_test_id("debate-stage").all_inner_texts())
                    print("debate errors", page.get_by_test_id("debate-error").all_inner_texts())
                    raise
                expect(page.get_by_test_id("debate-perspectives")).to_contain_text("随机访问")
                page.get_by_test_id("debate-perspectives").locator("article").first.get_by_role(
                    "button", name="这个视角有帮助"
                ).click()
                expect(page.get_by_test_id("perspective-feedback-status")).to_contain_text("反馈已记录")
                page.get_by_test_id("exit-debate").click()
                expect(page.get_by_test_id("classroom-panel")).to_be_visible()
                expect(page.get_by_label("最近一次练习提交回执")).to_contain_text("2 / 2")
                page.get_by_test_id("toggle-mode").click()
                expect(page.get_by_test_id("mode-tag")).to_contain_text("专注模式")

                page.get_by_test_id("request-animation").click()
                expect(page.get_by_test_id("animation-video")).to_be_visible()
                page.wait_for_function(
                    "document.querySelector('[data-testid=animation-video]').readyState >= 1"
                )
                video = page.get_by_test_id("animation-video").evaluate(
                    "v => ({duration: v.duration, error: v.error && v.error.code})"
                )
                assert video["duration"] == 36 and video["error"] is None, video
                download_start = len(posts)
                for test_id, suffix in (
                    ("download-notes", ".md"), ("download-mp4", ".mp4"),
                    ("download-srt", ".srt"),
                ):
                    with page.expect_download() as event:
                        page.get_by_test_id(test_id).click()
                    download = event.value
                    assert download.suggested_filename.endswith(suffix)
                    assert Path(download.path()).stat().st_size > 0
                assert len(posts) == download_start, posts[download_start:]
                print("Real MVP 0.3 full browser journey passed", flush=True)
            finally:
                browser.close()
    finally:
        stop(web)
        stop(backend)


if __name__ == "__main__":
    run()
