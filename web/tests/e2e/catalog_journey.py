"""Independent real-browser core journey; earlier metric evidence stays immutable."""

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Thread
from uuid import uuid4
import subprocess

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "backend"),
    str(ROOT / "backend/tests"),
]
from catalog_acceptance import (  # noqa: E402
    API,
    BASE,
    app,
    api,
    audit,
    external_attempts,
    enroll,
    open_enrolled,
    measure_animation,
    seed,
    revoke,
    save,
    ready,
    sha,
    load_package,
    sync_playwright,
    Config,
    Server,
)  # noqa: E402

OUTPUT = Path(os.environ["EDUMIND_CATALOG_RESULT"])
PLAN = Path(os.environ["EDUMIND_CATALOG_PROTOCOL"])


def journey(
    page, release_id, package, animation_rows, pool, browser, progress, persist
):
    checks = progress["nodes"]
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
        persist()
        print("journey", node_id, "passed", flush=True)
    # Actual media, owner isolation, UI downloads and restored video for both templates.
    downloads = progress["media_downloads"]
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
            foreign_page = foreign.new_page()
            foreign_page.goto(BASE, wait_until="networkidle")
            identity = api(foreign_page, "/api/auth/session")
            assert identity["status"] == 200
            assert identity["body"]["user"]["id"] != owner
            assert api(foreign_page, "/api/learning-units/" + unit)["status"] == 404
            assert (
                api(foreign_page, "/api/animation-media/" + row["media_id"] + "/mp4")[
                    "status"
                ]
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
    assert api(page, "/api/animation-media/" + media + "/mp4")["status"] == 404
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
    assert app.dependency_overrides == {}
    assert os.environ["EDUMIND_PRODUCT_MODE"] == "catalog_only"
    assert "edumind_catalog_core_20261003_v5" in os.environ["EDUMIND_DATABASE_URL"]
    assert not any(
        k.startswith(("EDUMIND_PROVIDER", "EDUMIND_REVIEW_CANDIDATE"))
        for k in os.environ
    )
    sys.addaudithook(audit)
    release_id = asyncio.run(seed())
    package = load_package(ROOT / "data/course_catalog/linear-v1")
    report = {
        "protocol_sha256": sha(PLAN),
        "content_digest": package.digest,
        "provider_requests": 0,
        "release_approval": "TEST_ONLY NOT HUMAN REVIEW",
        "external_attempts": [],
        "binding_probes": [],
        "journey": {"ok": False, "nodes": [], "media_downloads": []},
    }
    save(report)
    server = Server(Config(app, host="127.0.0.1", port=8016, log_level="error"))
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    env = {**os.environ, "EDUMIND_API_PROXY_TARGET": API}
    artifacts = Path("/private/tmp/edumind-catalog-core-20261003-v5")
    artifacts.mkdir(exist_ok=False)
    log = (artifacts / "vite.log").open("w")
    web = subprocess.Popen(
        ["pnpm", "dev", "--host", "127.0.0.1", "--port", "4186", "--strictPort"],
        cwd=ROOT / "web",
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    blocked = []
    try:
        ready(API + "/health")
        ready(BASE)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=["--autoplay-policy=no-user-gesture-required"]
            )
            context = browser.new_context(viewport={"width": 1280, "height": 900})

            def route(r):
                from urllib.parse import urlsplit

                if urlsplit(r.request.url).hostname not in ("127.0.0.1", "localhost"):
                    blocked.append("external browser request blocked")
                    r.abort()
                else:
                    r.continue_()

            context.route("**/*", route)
            page = context.new_page()
            page.goto(BASE, wait_until="networkidle")
            with ThreadPoolExecutor(max_workers=1) as pool:
                for template in ("linked-list-insertion", "linked-list-deletion"):
                    os.environ["EDUMIND_ANIMATION_CACHE_ROOT"] = str(
                        artifacts / template
                    )
                    unit = enroll(page, release_id, template)
                    row = measure_animation(
                        page,
                        {"id": "core-" + template, "template_id": template},
                        unit,
                        fresh=True,
                        pool=pool,
                    )
                    row["unit_id"] = unit
                    report["binding_probes"].append(row)
                    save(report)
                    assert row["ok"], row
                os.environ["EDUMIND_ANIMATION_CACHE_ROOT"] = os.environ[
                    "EDUMIND_CATALOG_QUALITY_CACHE"
                ]
                report["journey"] = journey(
                    page,
                    release_id,
                    package,
                    report["binding_probes"],
                    pool,
                    browser,
                    report["journey"],
                    lambda: save(report),
                )
            page.screenshot(path=str(artifacts / "withdrawn.png"), full_page=True)
            browser.close()
    except Exception as error:
        report["fatal_error"] = {
            "type": type(error).__name__,
            "message": str(error)[:300],
        }
        raise
    finally:
        report["external_attempts"] = external_attempts + blocked
        save(report)
        web.terminate()
        try:
            web.wait(timeout=5)
        except subprocess.TimeoutExpired:
            web.kill()
            web.wait(timeout=5)
        log.close()
        server.should_exit = True
        thread.join(timeout=5)
    print("Core journey passed; Provider 0", flush=True)


if __name__ == "__main__":
    main()
