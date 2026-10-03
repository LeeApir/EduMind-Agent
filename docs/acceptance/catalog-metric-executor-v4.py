"""Actual catalog app, private PostgreSQL, real Worker and Chromium; no Provider."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import platform
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Thread
from urllib.parse import urlsplit
from urllib.error import URLError
from urllib.request import urlopen
from uuid import UUID, uuid4

from playwright.sync_api import sync_playwright
from sqlalchemy.ext.asyncio import async_sessionmaker
from uvicorn import Config, Server

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(ROOT / "backend"),
    str(ROOT / "backend/tests"),
    str(ROOT / "scripts"),
    str(Path(__file__).parent),
]
from catalog_acceptance_protocol import p95, sha  # noqa: E402
from catalog_fixtures import approval_fixture  # noqa: E402
from app.core.database import create_database_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.animation_worker import run_one_animation_job  # noqa: E402
from app.services.knowledge_graph import default_knowledge_graph_repository  # noqa: E402
from app.services.catalog_package import load_package  # noqa: E402
from app.services.catalog_publication import publish_catalog, revoke_catalog  # noqa: E402

API = "http://127.0.0.1:8016"
BASE = "http://127.0.0.1:4186"  # Chromium trusts the loopback origin.
OUTPUT = Path(os.environ["EDUMIND_CATALOG_RESULT"])
PLAN = Path(os.environ["EDUMIND_CATALOG_PROTOCOL"])
ARTIFACTS = Path("/private/tmp/edumind-catalog-browser-20261003-v4")
MEASURE_SCRIPT = "() => {\n  const metric = {t0: null, loaded: null, playing: null, error: null};\n  window.__animationMetric = metric;\n  const button = document.querySelector('[data-testid=\"request-animation\"]');\n  if (!button) throw new Error('animation button missing');\n  button.addEventListener('click', () => { metric.t0 = performance.now(); }, {once: true});\n  const attached = new WeakSet();\n  function attach() {\n    const video = document.querySelector('[data-testid=\"animation-video\"]');\n    if (!video || attached.has(video)) return;\n    attached.add(video);\n    const loaded = () => {\n      metric.loaded ??= performance.now();\n      video.play().catch(error => { metric.error = String(error); });\n    };\n    video.addEventListener('loadeddata', loaded, {once: true});\n    video.addEventListener('playing', () => { metric.playing = performance.now(); }, {once: true});\n    video.addEventListener('error', () => { metric.error = 'media error ' + video.error?.code; });\n    if (video.readyState >= 2) loaded();\n  }\n  new MutationObserver(attach).observe(document.body, {subtree: true, childList: true});\n  attach();\n}"


def ready(url):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1):
                return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("Local server did not start")


external_attempts: list[str] = []


def audit(event, args):
    if event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple):
            try:
                local = ipaddress.ip_address(address[0]).is_loopback
            except ValueError:
                local = address[0] == "localhost"
            if not local:
                external_attempts.append("non-loopback socket blocked")
                raise RuntimeError("Catalog acceptance forbids external network")


async def seed() -> str:
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            package = load_package(ROOT / "data/course_catalog/linear-v1")
            assert package.digest == json.loads(PLAN.read_text())["content_digest"]
            release = await publish_catalog(
                db,
                package,
                approval=approval_fixture(package),
                trusted_digest=package.digest,
            )
            await db.commit()
            return str(release.id)
    finally:
        await engine.dispose()


async def worker_once() -> str | None:
    engine = create_database_engine()
    try:
        result = await run_one_animation_job(
            async_sessionmaker(engine, expire_on_commit=False)
        )
        return str(result) if result else None
    finally:
        await engine.dispose()


async def revoke(release_id: str) -> None:
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine)() as db:
            await revoke_catalog(db, UUID(release_id))
            await db.commit()
    finally:
        await engine.dispose()


def save(report):
    temp = OUTPUT.with_suffix(".tmp")
    temp.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    temp.replace(OUTPUT)


def api(page, path, *, method="GET", body=None, headers=None):
    # The test driver never saves cookies/CSRF to an evidence file.
    return page.evaluate(
        """async ({path, method, body, headers}) => {
      const r = await fetch(path, {method, headers: {...(body ? {'Content-Type':'application/json'} : {}), ...headers},
        ...(body ? {body: JSON.stringify(body)} : {})});
      return {status:r.status, body:await r.json()};
    }""",
        {"path": path, "method": method, "body": body, "headers": headers or {}},
    )


def enroll(page, release_id, node_id):
    auth = api(page, "/api/auth/session")
    assert auth["status"] == 200
    response = api(
        page,
        "/api/catalog/sessions",
        method="POST",
        body={"release_id": release_id, "node_id": node_id},
        headers={
            "X-CSRF-Token": auth["body"]["csrf_token"],
            "Idempotency-Key": uuid4().hex,
        },
    )
    assert response["status"] == 201, response
    unit = response["body"]["learning_unit_id"]
    owner = auth["body"]["user"]["id"]
    page.evaluate(
        "({owner,unit}) => { sessionStorage.setItem(`edumind:catalog:last:${owner}`,unit); }",
        {"owner": owner, "unit": unit},
    )
    return unit


def open_enrolled(page, unit):
    page.reload(wait_until="networkidle")
    page.get_by_test_id("explanation-tab").wait_for()
    assert api(page, "/api/learning-units/" + unit)["status"] == 200


def measure_screen(page, slot, package):
    result = {**slot, "ok": False}
    timings = []

    def finished(request):
        path = urlsplit(request.url).path
        if path in [
            "/api/auth/session",
            "/api/auth/guest",
            "/api/catalog",
            "/api/catalog/sessions",
        ] or re.fullmatch(r"/api/learning-units/[a-f0-9-]{36}", path):
            timing = request.timing
            assert 0 <= timing["requestStart"] <= timing["responseEnd"], (
                "HTTP timing unknown"
            )
            timings.append(
                {
                    "path": path,
                    "method": request.method,
                    "milliseconds": max(
                        0, timing["responseEnd"] - timing["requestStart"]
                    ),
                }
            )

    page.on("requestfinished", finished)
    started = time.monotonic()
    try:
        if slot["mode"] == "cold":
            page.goto(BASE, wait_until="networkidle")
            name = next(
                n.name
                for n in default_knowledge_graph_repository().all_nodes()
                if n.id == slot["node_id"]
            )
            page.locator(".catalog-list li button").filter(
                has=page.locator(
                    "span", has_text=re.compile("^" + re.escape(name) + "$")
                )
            ).click()
        else:
            page.reload(wait_until="domcontentloaded")
        text = package.nodes[slot["node_id"]]["explanation"]["markdown"]
        page.get_by_test_id("explanation-tab").wait_for(timeout=20000)
        page.wait_for_function(
            'text => document.querySelector("[data-testid=explanation-tab]")?.innerText === text',
            arg=text,
        )
        page.evaluate(
            "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )
        assert page.get_by_test_id("explanation-tab").is_visible()
        result.update(
            ok=True,
            dom_seconds=round(time.monotonic() - started, 6),
            http_seconds=round(sum(t["milliseconds"] for t in timings) / 1000, 6),
            http_requests=timings,
        )
    except Exception as error:
        result.update(
            error_type=type(error).__name__,
            error=str(error)[:240],
            http_requests=timings,
        )
    finally:
        page.remove_listener("requestfinished", finished)
    return result


def measure_animation(page, slot, unit, *, fresh, pool):
    result = {**slot, "ok": False}
    worker = None
    try:
        open_enrolled(page, unit)
        page.get_by_test_id("request-animation").wait_for(timeout=15000)
        page.evaluate(MEASURE_SCRIPT)
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/animations")
        ) as event:
            page.get_by_test_id("request-animation").click()
        response = event.value
        payload = response.json()
        assert response.status == (202 if fresh else 200), (response.status, payload)
        result.update(
            http_status=response.status,
            job_id=payload["id"],
            job_status=payload["status"],
        )
        if fresh:
            assert payload["status"] == "queued"
            worker = pool.submit(lambda: asyncio.run(worker_once()))
            assert page.get_by_test_id("explanation-tab").inner_text()
            result["learning_read_during_render_ok"] = True
        page.wait_for_function(
            "() => window.__animationMetric.playing !== null || window.__animationMetric.error !== null",
            timeout=140000,
        )
        metric = page.evaluate("window.__animationMetric")
        assert metric["error"] is None and all(
            metric[k] is not None for k in ("t0", "loaded", "playing")
        ), metric
        result["click_to_play_seconds"] = round(
            (metric["playing"] - metric["t0"]) / 1000, 6
        )
        result["click_to_loaded_seconds"] = round(
            (metric["loaded"] - metric["t0"]) / 1000, 6
        )
        video = page.get_by_test_id("animation-video").evaluate(
            "(v) => ({duration:v.duration,error:v.error?.code??null})"
        )
        assert (
            video["duration"]
            == (36 if slot["template_id"] == "linked-list-insertion" else 42)
            and video["error"] is None
        )
        snapshot = api(page, "/api/animation-jobs/" + payload["id"])
        assert snapshot["status"] == 200 and snapshot["body"]["status"] == "succeeded"
        result.update(ok=True, media_id=snapshot["body"]["media_id"], video=video)
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error)[:240])
    finally:
        if worker:
            try:
                result["worker_job_id"] = worker.result(timeout=150)
                assert result["worker_job_id"] == result["job_id"]
            except Exception as error:
                result.update(
                    ok=False,
                    worker_error=type(error).__name__ + ": " + str(error)[:150],
                )
    return result


def journey(page, release_id, package, animation_rows, pool, browser):
    checks = []
    # All fixed content through actual server, server answers stripped, real quiz in UI.
    for node_id in package.nodes:
        unit = enroll(page, release_id, node_id)
        open_enrolled(page, unit)
        body = api(page, "/api/learning-units/" + unit)["body"]
        resources = body["scenes"][0]["resources"]
        assert (
            body["origin_type"] == "curated"
            and body["catalog_release_id"] == release_id
        )
        assert len(resources) == 3
        for resource in resources:
            expected = package.nodes[node_id][resource["type"]]
            if resource["type"] == "exercise":
                assert len(resource["content"]["items"]) == 3
                assert all(
                    "answer" not in q and "explanation" not in q
                    for q in resource["content"]["items"]
                )
            else:
                assert resource["content"] == expected
        page.get_by_role("button", name="代码", exact=True).click()
        assert (
            page.get_by_test_id("code-tab").locator("code").inner_text()
            == package.nodes[node_id]["code"]["source"]
        )
        page.get_by_role("button", name="练习", exact=True).click()
        items = package.nodes[node_id]["exercise"]["items"]
        for index, q in enumerate(items):
            page.get_by_label(q["question"], exact=True).fill(
                q["answer"] if index else "INCORRECT_TEST"
            )
        with page.expect_response(
            lambda r: r.request.method == "POST"
            and r.url.endswith("/api/quiz-submissions")
        ) as event:
            page.get_by_role("button", name="提交练习", exact=True).click()
        quiz = event.value.json()
        assert event.value.status == 200 and quiz["correct_count"] == 2
        assert quiz["catalog_assessment"]["eligible_for_mastery"] is True
        page.get_by_role("region", name="最近一次练习提交回执").wait_for()
        mastery = api(page, "/api/mastery")["body"]
        page.get_by_role("button", name="再做一次", exact=True).click()
        for q in items:
            page.get_by_label(q["question"], exact=True).fill(q["answer"])
        with page.expect_response(
            lambda r: r.request.method == "POST"
            and r.url.endswith("/api/quiz-submissions")
        ) as event:
            page.get_by_role("button", name="提交练习", exact=True).click()
        repeat = event.value.json()
        assert (
            repeat["correct_count"] == 3
            and repeat["catalog_assessment"]["reason"] == "repeat"
        )
        assert (
            repeat["mastery_changes"] == []
            and api(page, "/api/mastery")["body"] == mastery
        )
        page.reload(wait_until="networkidle")
        page.get_by_role("region", name="最近一次练习提交回执").wait_for()
        page.get_by_role("button", name="查看数组 vs 链表预设演示", exact=True).click()
        page.locator(".catalog-demo").wait_for()
        assert "预设教学演示" in page.locator(".catalog-demo").inner_text()
        page.reload(wait_until="networkidle")
        page.locator(".catalog-demo").wait_for()
        page.get_by_role("button", name="退出演示，返回学习", exact=True).click()
        page.get_by_test_id("exercise-tab").wait_for(state="visible")
        with page.expect_download() as download:
            page.get_by_role("button", name="下载 Markdown 笔记", exact=True).click()
        file = download.value.path()
        notes = Path(file).read_text()
        assert (
            "人工审核课程包" in notes
            and "预设数组 vs 链表总结" in notes
            and "本人错题摘要" in notes
        )
        assert "INCORRECT_TEST" not in notes and "模型" not in notes
        path = api(page, "/api/path/current?target_node_id=" + node_id)
        assert path["status"] == 200
        page.locator('[aria-label="学习路径"]').wait_for()
        checks.append(
            {
                "node_id": node_id,
                "resources": 3,
                "questions": 3,
                "quiz": 2,
                "repeat": 3,
                "mastery_repeat_unchanged": True,
                "restore": True,
                "preset_restore": True,
                "notes": True,
                "path": True,
                "unit_id": unit,
            }
        )
    # Actual media, owner isolation, UI downloads and restored video for both templates.
    downloads = []
    for template in ("linked-list-insertion", "linked-list-deletion"):
        row = next(
            r for r in animation_rows if r["template_id"] == template and r.get("ok")
        )
        # Keep the correct scene-qualified request state from that animation page.
        unit = row["unit_id"]
        owner = api(page, "/api/auth/session")["body"]["user"]["id"]
        page.evaluate(
            "({owner,unit}) => sessionStorage.setItem(`edumind:catalog:last:${owner}`,unit)",
            {"owner": owner, "unit": unit},
        )
        open_enrolled(page, unit)
        page.get_by_test_id("animation-video").wait_for()
        for ext in ("mp4", "srt"):
            with page.expect_download() as download:
                page.get_by_test_id("download-" + ext).click()
            path = Path(download.value.path())
            assert path.stat().st_size > 0
            downloads.append(
                {
                    "template": template,
                    "extension": ext,
                    "bytes": path.stat().st_size,
                    "sha256": sha(path),
                }
            )
        foreign = browser.new_context()
        try:
            foreign.request.post(BASE + "/api/auth/guest")
            assert (
                foreign.request.get(BASE + "/api/learning-units/" + unit).status == 404
            )
            assert (
                foreign.request.get(
                    BASE + "/api/animation-media/" + row["media_id"] + "/mp4"
                ).status
                == 404
            )
        finally:
            foreign.close()
    unit = checks[-1]["unit_id"]
    auth = api(page, "/api/auth/session")["body"]
    missing_csrf = api(
        page,
        "/api/catalog/sessions",
        method="POST",
        body={"release_id": release_id, "node_id": "array"},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert missing_csrf["status"] == 403
    blocked = api(
        page,
        "/api/learning-sessions",
        method="POST",
        body={"goal": "test"},
        headers={"X-CSRF-Token": auth["csrf_token"], "Idempotency-Key": uuid4().hex},
    )
    assert blocked["status"] == 409 and blocked["body"]["code"] == "FEATURE_UNAVAILABLE"
    assert (
        page.get_by_role("textbox").count() == 0
    )  # restored receipt has no free AI input
    pool.submit(lambda: asyncio.run(revoke(release_id))).result()
    assert api(page, "/api/learning-units/" + unit)["status"] == 404
    media = animation_rows[0]["media_id"]
    assert (
        page.request.get(BASE + "/api/animation-media/" + media + "/mp4").status == 404
    )
    page.reload(wait_until="networkidle")
    page.get_by_text("课程正在准备", exact=True).wait_for()
    return {
        "ok": True,
        "nodes": checks,
        "media_downloads": downloads,
        "owner_isolation": True,
        "csrf": True,
        "dynamic_blocked": True,
        "revoked_hidden": True,
    }


def main():
    assert not OUTPUT.exists()
    plan = json.loads(PLAN.read_text())
    assert "edumind_catalog_accept_20261003_v4" in os.environ["EDUMIND_DATABASE_URL"]
    assert not any(
        k.startswith(("EDUMIND_PROVIDER", "EDUMIND_REVIEW_CANDIDATE"))
        for k in os.environ
    )
    assert os.environ["EDUMIND_PRODUCT_MODE"] == "catalog_only"
    assert app.dependency_overrides == {}, (
        "Acceptance must use actual production dependencies"
    )
    sys.addaudithook(audit)
    package = load_package(ROOT / "data/course_catalog/linear-v1")
    release_id = asyncio.run(seed())
    os.environ["EDUMIND_ANIMATION_CACHE_ROOT"] = os.environ[
        "EDUMIND_CATALOG_QUALITY_CACHE"
    ]
    report = {
        "protocol_sha256": sha(PLAN),
        "scope": plan["scope"],
        "content_digest": package.digest,
        "release_approval": "TEST_ONLY NOT HUMAN REVIEW",
        "provider_requests": 0,
        "host": platform.platform(),
        "first_screen_slots": [],
        "cache_slots": [],
        "render_slots": [],
        "journey": {"ok": False},
        "external_attempts": external_attempts,
    }
    save(report)
    server = Server(Config(app, host="127.0.0.1", port=8016, log_level="error"))
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    env = {**os.environ, "EDUMIND_API_PROXY_TARGET": API}
    ARTIFACTS.mkdir(exist_ok=False)
    server_log = (ARTIFACTS / "vite.log").open("w")
    web = subprocess.Popen(
        ["pnpm", "dev", "--host", "127.0.0.1", "--port", "4186", "--strictPort"],
        cwd=ROOT / "web",
        env=env,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )
    browser_external = []
    try:
        ready(API + "/health")
        ready(BASE)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=["--autoplay-policy=no-user-gesture-required"]
            )
            report["browser_version"] = browser.version

            def route(request):
                host = urlsplit(request.request.url).hostname
                if host not in ("localhost", "127.0.0.1"):
                    browser_external.append("external browser request blocked")
                    request.abort()
                else:
                    request.continue_()

            browser_context = browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            browser_context.route("**/*", route)
            page = browser_context.new_page()
            page.goto(BASE, wait_until="networkidle")
            page.screenshot(path=str(ARTIFACTS / "initial.png"), full_page=True)
            (ARTIFACTS / "initial.html").write_text(page.content())
            report["initial_buttons"] = page.get_by_role("button").all_text_contents()
            assert page.get_by_role("heading", name="课程目录", exact=True).is_visible()
            for node in package.nodes:
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                context.route("**/*", route)
                first = context.new_page()
                cdp = context.new_cdp_session(first)
                cdp.send("Network.enable")
                cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
                for mode in ("cold", "warm"):
                    slot = next(
                        s
                        for s in plan["first_screen_slots"]
                        if s["node_id"] == node and s["mode"] == mode
                    )
                    row = measure_screen(first, slot, package)
                    report["first_screen_slots"].append(row)
                    save(report)
                    print("screen", slot["id"], row["ok"], flush=True)
                context.close()
            if not all(row["ok"] for row in report["first_screen_slots"]):
                report["stop_reason"] = (
                    "First-screen gate failed; remaining browser phases unattempted"
                )
                report["unattempted"] = (
                    plan["cache_browser_slots"] + plan["render_browser_slots"]
                )
                raise RuntimeError(report["stop_reason"])
            with ThreadPoolExecutor(max_workers=1) as pool:
                for group, fresh in [("cache_slots", False), ("render_slots", True)]:
                    slots = plan[
                        "render_browser_slots" if fresh else "cache_browser_slots"
                    ]
                    for slot in slots:
                        if fresh:
                            root = (
                                Path(os.environ["EDUMIND_CATALOG_FRESH_ROOT"])
                                / slot["id"]
                            )
                            assert not root.exists()
                            os.environ["EDUMIND_ANIMATION_CACHE_ROOT"] = str(root)
                        unit = enroll(page, release_id, slot["template_id"])
                        row = measure_animation(
                            page, slot, unit, fresh=fresh, pool=pool
                        )
                        row["unit_id"] = unit
                        report[group].append(row)
                        save(report)
                        print("animation", slot["id"], row["ok"], flush=True)
                os.environ["EDUMIND_ANIMATION_CACHE_ROOT"] = os.environ[
                    "EDUMIND_CATALOG_QUALITY_CACHE"
                ]
                report["journey"] = journey(
                    page, release_id, package, report["cache_slots"], pool, browser
                )
                # Cache media is stored in quality root; fresh media has independent roots.
            page.screenshot(path=str(ARTIFACTS / "withdrawn.png"), full_page=True)
            report["summary"] = {
                "http_p95_seconds": p95(
                    report["first_screen_slots"], "http_seconds", 20
                ),
                "dom_p95_seconds": p95(report["first_screen_slots"], "dom_seconds", 20),
                "cache_p95_seconds": p95(
                    report["cache_slots"], "click_to_play_seconds", 100
                ),
                "render_p95_seconds": p95(
                    report["render_slots"], "click_to_play_seconds", 20
                ),
            }
            browser.close()
    except Exception as error:
        report["fatal_error"] = {
            "type": type(error).__name__,
            "message": str(error)[:350],
        }
        raise
    finally:
        report["external_attempts"] = external_attempts + browser_external
        save(report)
        web.terminate()
        try:
            web.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web.kill()
            web.wait(timeout=5)
        server_log.close()
        server.should_exit = True
        thread.join(timeout=5)
    print(json.dumps(report["summary"]), flush=True)


if __name__ == "__main__":
    main()
