"""T032 real-browser cache and fresh-render timing over frozen slot lists."""

from __future__ import annotations

import asyncio
import json
import math
import os
import platform
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Thread
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID

from playwright.sync_api import sync_playwright
from sqlalchemy.ext.asyncio import async_sessionmaker
from uvicorn import Config, Server

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
WEB = ROOT / "web"
API = "http://127.0.0.1:8004"
FRONTEND = "http://127.0.0.1:4178"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from real_stage_backend import app  # noqa: E402

from app.core.database import create_database_engine  # noqa: E402
from app.models.learning import GeneratedResource, LearningScene, LearningUnit  # noqa: E402
from app.services.animation_worker import run_one_animation_job  # noqa: E402

MEASURE_SCRIPT = """() => {
  const metric = {t0: null, loaded: null, playing: null, error: null};
  window.__animationMetric = metric;
  const button = document.querySelector('[data-testid="request-animation"]');
  if (!button) throw new Error('animation button missing');
  button.addEventListener('click', () => { metric.t0 = performance.now(); }, {once: true});
  const attached = new WeakSet();
  function attach() {
    const video = document.querySelector('[data-testid="animation-video"]');
    if (!video || attached.has(video)) return;
    attached.add(video);
    const loaded = () => {
      metric.loaded ??= performance.now();
      video.play().catch(error => { metric.error = String(error); });
    };
    video.addEventListener('loadeddata', loaded, {once: true});
    video.addEventListener('playing', () => { metric.playing = performance.now(); }, {once: true});
    video.addEventListener('error', () => { metric.error = 'media error ' + video.error?.code; });
    if (video.readyState >= 2) loaded();
  }
  new MutationObserver(attach).observe(document.body, {subtree: true, childList: true});
  attach();
}"""


def ready(url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1):
                return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError(f"Server did not start: {url}")


async def seed_units(owner: UUID, slots: list[dict[str, str]]) -> list[str]:
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            unit_ids: list[str] = []
            for slot in slots:
                unit = LearningUnit(
                    user_id=owner, knowledge_point_id=slot["template_id"],
                    title=f"T032 {slot['id']}", status="ready",
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
                    knowledge_point_id=slot["template_id"], resource_type="explanation",
                    content={"markdown": "链表节点通过指针相连；动画运行不影响讲解阅读。"},
                    review_status="passed", version=1,
                    published_at=datetime.now(timezone.utc),
                ))
                unit_ids.append(str(unit.id))
            await db.commit()
            return unit_ids
    finally:
        await engine.dispose()


async def worker_once() -> str | None:
    engine = create_database_engine()
    try:
        result = await run_one_animation_job(async_sessionmaker(engine, expire_on_commit=False))
        return str(result) if result else None
    finally:
        await engine.dispose()


def save(path: Path, report: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def p95(results: list[dict[str, object]]) -> float | str:
    samples = sorted(
        float(row["click_to_play_seconds"]) if row.get("ok") else math.inf
        for row in results
    )
    value = samples[math.ceil(0.95 * len(samples)) - 1]
    return "+inf" if math.isinf(value) else value


def measure(page, slot: dict[str, str], unit_id: str, *, fresh: bool, pool) -> dict[str, object]:
    result: dict[str, object] = {"id": slot["id"], "template_id": slot["template_id"]}
    page.evaluate("unit => sessionStorage.setItem('edumind:last-learning-unit', unit)", unit_id)
    page.reload(wait_until="domcontentloaded")
    page.get_by_test_id("request-animation").wait_for(timeout=15000)
    page.evaluate(MEASURE_SCRIPT)
    worker = None
    try:
        with page.expect_response(
            lambda response: response.request.method == "POST"
            and response.url.endswith("/animations"), timeout=15000,
        ) as event:
            page.get_by_test_id("request-animation").click()
        response = event.value
        payload = response.json()
        result.update({"http_status": response.status, "job_status": payload.get("status"),
                       "job_id": payload.get("id")})
        assert response.status == (202 if fresh else 200), payload
        assert payload["status"] == ("queued" if fresh else "succeeded"), payload
        if fresh:
            page.get_by_test_id("animation-panel").get_by_text(
                "排队中", exact=True,
            ).first.wait_for(timeout=10000)
            worker = pool.submit(lambda: asyncio.run(worker_once()))
            assert "动画运行不影响讲解阅读" in page.get_by_test_id("explanation-tab").inner_text()
            result["learning_read_during_render_ok"] = True
        page.wait_for_function(
            "() => { const m = window.__animationMetric; "
            "return m.playing !== null || m.error !== null; }",
            timeout=180000,
        )
        metric = page.evaluate("window.__animationMetric")
        assert metric["error"] is None and metric["t0"] is not None, metric
        assert metric["loaded"] is not None and metric["playing"] is not None, metric
        result["click_to_loaded_seconds"] = round((metric["loaded"] - metric["t0"]) / 1000, 4)
        result["click_to_play_seconds"] = round((metric["playing"] - metric["t0"]) / 1000, 4)
        video = page.get_by_test_id("animation-video").evaluate(
            "video => ({duration: video.duration, error: video.error?.code ?? null})"
        )
        assert video["duration"] in (36, 42) and video["error"] is None, video
        result["ok"] = True
    except Exception as error:
        result.update({"ok": False, "error_type": type(error).__name__,
                       "error": str(error)[:250]})
    finally:
        if worker is not None:
            try:
                result["worker_job_id"] = worker.result(timeout=190)
                if result.get("worker_job_id") != result.get("job_id"):
                    result.update({"ok": False, "error": "worker claimed a different job"})
            except Exception as error:
                result.update({"ok": False, "worker_error": str(error)[:180]})
    return result


def run(plan_path: Path, output: Path, quality_cache: Path, fresh_root: Path) -> None:
    if not os.getenv("EDUMIND_TEST_DATABASE_URL"):
        raise RuntimeError("An isolated PostgreSQL URL is required")
    if output.exists():
        raise RuntimeError("Refusing to overwrite an existing report")
    plan = json.loads(plan_path.read_text())
    cache_slots = plan["cache_browser_slots"]
    fresh_slots = plan["render_browser_slots"]
    assert len(cache_slots) == 100 and len(fresh_slots) == 20
    os.environ["EDUMIND_DATABASE_URL"] = os.environ["EDUMIND_TEST_DATABASE_URL"]
    os.environ["EDUMIND_ANIMATION_CACHE_ROOT"] = str(quality_cache)
    server = Server(Config(app, host="127.0.0.1", port=8004, log_level="error"))
    api_thread = Thread(target=server.run, daemon=True)
    api_thread.start()
    web_env = {**os.environ, "EDUMIND_API_PROXY_TARGET": API}
    web = subprocess.Popen(
        ["pnpm", "dev", "--host", "127.0.0.1", "--port", "4178"],
        cwd=WEB, env=web_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    report: dict[str, object] = {
        "plan": str(plan_path.resolve().relative_to(ROOT)),
        "baseline_commit": plan["baseline_commit"],
        "host": {"platform": platform.platform(), "machine": platform.machine()},
        "browser_cache_disabled": True, "concurrency": 1,
        "cache_slots": [], "render_slots": [],
    }
    save(output, report)
    try:
        ready(API + "/health")
        ready(FRONTEND)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=["--autoplay-policy=no-user-gesture-required"],
            )
            try:
                report["browser_version"] = browser.version
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                auth = context.request.post(FRONTEND + "/api/auth/guest")
                assert auth.status == 201, auth.text()
                owner = UUID(auth.json()["user"]["id"])
                slots = cache_slots + fresh_slots
                with ThreadPoolExecutor(max_workers=1) as pool:
                    unit_ids = pool.submit(lambda: asyncio.run(seed_units(owner, slots))).result()
                    page = context.new_page()
                    cdp = context.new_cdp_session(page)
                    cdp.send("Network.enable")
                    cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                    page.goto(FRONTEND)
                    for index, slot in enumerate(cache_slots):
                        result = measure(page, slot, unit_ids[index], fresh=False, pool=pool)
                        report["cache_slots"].append(result)
                        save(output, report)
                        print(f"cache {index + 1}/100 {slot['id']} ok={result['ok']}", flush=True)
                    for index, slot in enumerate(fresh_slots):
                        root = fresh_root / slot["id"] / "approved"
                        assert not root.exists(), root
                        os.environ["EDUMIND_ANIMATION_CACHE_ROOT"] = str(root)
                        result = measure(
                            page, slot, unit_ids[len(cache_slots) + index], fresh=True, pool=pool,
                        )
                        report["render_slots"].append(result)
                        save(output, report)
                        print(f"render {index + 1}/20 {slot['id']} ok={result['ok']}", flush=True)
                cache = report["cache_slots"]
                render = report["render_slots"]
                report["summary"] = {
                    "cache_p95_seconds": p95(cache),
                    "cache_all_under_2_seconds": all(
                        row.get("ok") and float(row["click_to_play_seconds"]) <= 2
                        for row in cache
                    ),
                    "render_p95_seconds": p95(render),
                    "cache_passed": sum(row.get("ok") is True for row in cache),
                    "render_passed": sum(row.get("ok") is True for row in render),
                }
                save(output, report)
                print(json.dumps(report["summary"]), flush=True)
            finally:
                browser.close()
    finally:
        web.terminate()
        try:
            web.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web.kill()
            web.wait(timeout=5)
        server.should_exit = True
        api_thread.join(timeout=5)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--quality-cache", type=Path, required=True)
    parser.add_argument("--fresh-root", type=Path, required=True)
    args = parser.parse_args()
    run(args.plan, args.output, args.quality_cache, args.fresh_root)
