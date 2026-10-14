"""Signed catalog, actual PG/Worker/browser and API process restart; no model calls."""

import asyncio
import json
import os
import platform
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import catalog_acceptance as catalog
import catalog_journey as core
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.services.catalog_package import read_json
from app.services.catalog_publication import publish_catalog
from verify_catalog_release import trusted_release, verify

ROOT = catalog.ROOT
OUTPUT = Path(os.environ["EDUMIND_CATALOG_RESULT"])
ARTIFACTS = OUTPUT.parent
API = "http://127.0.0.1:8038"
BASE = "http://127.0.0.1:4238"


async def publish():
    directory = ROOT / "data/course_catalog/linear-v1"
    digest, approval = trusted_release(
        directory, ROOT / "data/course_catalog/release-allowlist.json"
    )
    signature = verify(directory, digest, approval)
    assert signature["state"] == "HUMAN_APPROVED" and signature["publishable"]
    package = catalog.load_package(directory)
    engine = create_database_engine()
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            release = await publish_catalog(
                db, package, approval=read_json(approval), trusted_digest=digest
            )
            await db.commit()
            return str(release.id), package, signature
    finally:
        await engine.dispose()


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    assert not OUTPUT.exists()
    assert os.environ["EDUMIND_PRODUCT_MODE"] == "catalog_only"
    assert "/edumind_catalog_phase1_t038_" in os.environ["EDUMIND_DATABASE_URL"]
    assert not any(k.startswith("EDUMIND_PROVIDER") for k in os.environ)
    assert not catalog.app.dependency_overrides
    catalog.API = core.API = API
    catalog.BASE = core.BASE = BASE
    catalog.ARTIFACTS = ARTIFACTS
    sys.addaudithook(catalog.audit)
    release_id, package, signature = asyncio.run(publish())
    report = {
        "provider_requests": 0,
        "release_approval": signature,
        "content_digest": package.digest,
        "transport": "real PostgreSQL, native Chromium, isolated Docker Worker, actual API processes",
        "binding_probes": [],
        "screen_slots": [],
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "journey": {"ok": False, "nodes": [], "media_downloads": []},
        "api_restart": {"ok": False},
        "passed": False,
    }

    def persist():
        catalog.save(report)

    persist()
    logs = [(ARTIFACTS / name).open("w") for name in ("api.log", "vite.log")]

    def start_api():
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8038",
                "--log-level",
                "error",
            ],
            cwd=ROOT / "backend",
            stdout=logs[0],
            stderr=subprocess.STDOUT,
        )
        catalog.ready(API + "/health")
        return process

    server = None
    web = None
    blocked = []
    try:
        server = start_api()
        web = subprocess.Popen(
            [
                "pnpm",
                "exec",
                "vite",
                "preview",
                "--host",
                "127.0.0.1",
                "--port",
                "4238",
                "--strictPort",
            ],
            cwd=ROOT / "web",
            env={**os.environ, "EDUMIND_API_PROXY_TARGET": API},
            stdout=logs[1],
            stderr=subprocess.STDOUT,
        )
        catalog.ready(BASE)
        with catalog.sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, args=["--autoplay-policy=no-user-gesture-required"]
            )

            def route(r):
                if urlsplit(r.request.url).hostname not in ("127.0.0.1", "localhost"):
                    blocked.append("external browser request blocked")
                    r.abort()
                else:
                    r.continue_()

            # Ten nodes, independently cold and then warm; no selected-slot retries.
            for index, node_id in enumerate(package.nodes):
                screen_context = browser.new_context(
                    viewport={"width": 1280, "height": 900}
                )
                screen_context.route("**/*", route)
                try:
                    screen_page = screen_context.new_page()
                    screen_page.add_init_script("""(() => {
                      window.__pathPaint = null;
                      const fetchOriginal = window.fetch.bind(window);
                      window.fetch = (...args) => {
                        const url = typeof args[0] === 'string' ? args[0] : args[0].url;
                        if (url?.startsWith('/api/path/current') && !window.__pathPaint)
                          window.__pathPaint = {start:performance.now(), end:null};
                        return fetchOriginal(...args);
                      };
                      const inspect = () => {
                        const metric = window.__pathPaint;
                        const panel = document.querySelector('.learning-path[aria-busy="false"]');
                        if (metric && metric.end === null && !metric.pending &&
                            panel?.querySelector('.path-nodes li') && !panel.querySelector('[role=alert]')) {
                          metric.pending = true;
                          requestAnimationFrame(() => requestAnimationFrame(() => {
                            if (panel.isConnected && panel.getAttribute('aria-busy') === 'false')
                              metric.end = performance.now();
                            else metric.pending = false;
                          }));
                        }
                      };
                      document.addEventListener('DOMContentLoaded', () => {
                        new MutationObserver(inspect).observe(document.body,
                          {subtree:true,childList:true,attributes:true});
                        inspect();
                      });
                    })()""")
                    for mode in ("cold", "warm"):
                        row = catalog.measure_screen(
                            screen_page,
                            {
                                "id": f"screen-{index:02}-{mode}",
                                "node_id": node_id,
                                "mode": mode,
                            },
                            package,
                        )
                        try:
                            screen_page.wait_for_function(
                                "window.__pathPaint?.end != null", timeout=3000
                            )
                            row["path_load_ms"] = screen_page.evaluate(
                                "window.__pathPaint.end-window.__pathPaint.start"
                            )
                            assert row["path_load_ms"] <= 500
                        except Exception as error:
                            row.update(ok=False, path_load_error=type(error).__name__)
                        report["screen_slots"].append(row)
                        persist()
                finally:
                    screen_context.close()
            assert len(report["screen_slots"]) == 20
            assert all(row["ok"] for row in report["screen_slots"])
            report["screen_p95_seconds"] = {
                key: sorted(row[key] for row in report["screen_slots"])[18]
                for key in ("http_seconds", "dom_seconds")
            }
            assert report["screen_p95_seconds"]["http_seconds"] <= 2
            assert report["screen_p95_seconds"]["dom_seconds"] <= 10
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            context.route("**/*", route)
            page = context.new_page()
            report["main_frame_navigations"] = []
            page.on(
                "framenavigated",
                lambda frame: (
                    report["main_frame_navigations"].append(frame.url)
                    if frame == page.main_frame
                    else None
                ),
            )
            page.goto(BASE, wait_until="networkidle")
            graph = catalog.api(page, "/api/graph?version=phase-1.1.0")
            assert graph["status"] == 200 and len(graph["body"]["nodes"]) == 30
            report["expanded_graph_nodes"] = 30
            with ThreadPoolExecutor(max_workers=1) as pool:
                for template in ("linked-list-insertion", "linked-list-deletion"):
                    unit = catalog.enroll(page, release_id, template)
                    navigation_count = len(report["main_frame_navigations"])
                    row = catalog.measure_animation(
                        page,
                        {"id": "integration-" + template, "template_id": template},
                        unit,
                        fresh=True,
                        pool=pool,
                    )
                    row["unit_id"] = unit
                    row["navigation_count"] = (
                        len(report["main_frame_navigations"]) - navigation_count
                    )
                    report["binding_probes"].append(row)
                    persist()
                    assert row["ok"], row
                    assert row["navigation_count"] == 1, (
                        "Unexpected page reload during rendering"
                    )

                def restart(checks, rows):
                    nonlocal server
                    owner = catalog.api(page, "/api/auth/session")["body"]["user"]["id"]
                    mastery = catalog.api(page, "/api/mastery")["body"]
                    old_pid = server.pid
                    stop(server)
                    server = start_api()
                    assert server.pid != old_pid
                    for unit in (checks[-1]["unit_id"], rows[0]["unit_id"]):
                        page.evaluate(
                            "({owner,unit}) => sessionStorage.setItem(`edumind:catalog:last:${owner}`,unit)",
                            {"owner": owner, "unit": unit},
                        )
                        # A restored unit may correctly select its exercise tab.
                        page.reload(wait_until="networkidle")
                        assert (
                            catalog.api(page, "/api/learning-units/" + unit)["status"]
                            == 200
                        )
                        if unit == checks[-1]["unit_id"]:
                            page.get_by_role("button", name="练习", exact=True).click()
                            page.get_by_role(
                                "region", name="最近一次练习提交回执"
                            ).wait_for()
                        else:
                            page.get_by_test_id("animation-video").wait_for()
                            job = catalog.api(
                                page, "/api/animation-jobs/" + rows[0]["job_id"]
                            )
                            assert job["body"]["status"] == "succeeded"
                    assert catalog.api(page, "/api/mastery")["body"] == mastery
                    assert (
                        catalog.api(page, "/api/auth/session")["body"]["user"]["id"]
                        == owner
                    )
                    report["api_restart"] = {
                        "ok": True,
                        "distinct_processes": True,
                        "identity": True,
                        "quiz_receipt": True,
                        "mastery": True,
                        "job_and_video": True,
                    }
                    persist()

                report["journey"] = core.journey(
                    page,
                    release_id,
                    package,
                    report["binding_probes"],
                    pool,
                    browser,
                    report["journey"],
                    persist,
                    before_withdraw=restart,
                    configure_context=lambda ctx: ctx.route("**/*", route),
                )
            page.screenshot(path=str(ARTIFACTS / "withdrawn.png"), full_page=True)
            browser.close()
        assert not blocked and not catalog.external_attempts
        report["passed"] = True
    except Exception as error:
        report["fatal_error"] = {
            "type": type(error).__name__,
            "message": str(error)[:300],
        }
        raise
    finally:
        report["external_attempts"] = catalog.external_attempts + blocked
        persist()
        for process in (web, server):
            if process is not None:
                stop(process)
        for log in logs:
            log.close()
    print(json.dumps({"catalog_integration": "passed", "provider_requests": 0}))


if __name__ == "__main__":
    main()
