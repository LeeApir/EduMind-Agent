"""Real HTTP browser integration against isolated PostgreSQL and a mock Provider."""

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
API = "http://127.0.0.1:8001"
FRONTEND = "http://127.0.0.1:4174"


def ready(url: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=1):
                return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError(f"Test server did not become ready: {url}")


def stop(process: subprocess.Popen[bytes]) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run() -> None:
    if not os.getenv("EDUMIND_TEST_DATABASE_URL"):
        raise RuntimeError("EDUMIND_TEST_DATABASE_URL must name an isolated PostgreSQL database")
    backend_env = {**os.environ, "EDUMIND_DATABASE_URL": os.environ["EDUMIND_TEST_DATABASE_URL"]}
    web_env = {**os.environ, "EDUMIND_API_PROXY_TARGET": API}
    backend = subprocess.Popen(
        ["uv", "run", "python", "../web/tests/e2e/real_debate_backend.py"],
        cwd=BACKEND, env=backend_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    web = subprocess.Popen(
        ["pnpm", "dev", "--host", "127.0.0.1", "--port", "4174"],
        cwd=WEB, env=web_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ready(API + "/health")
        ready(FRONTEND)
        sys.path.insert(0, str(BACKEND))
        sys.path.insert(0, str(BACKEND / "tests"))
        from test_debate_api import seed_unit
        from test_debate_feedback_api import prepare_profile

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                guest = context.request.post(FRONTEND + "/api/auth/guest")
                assert guest.status == 201
                with ThreadPoolExecutor(max_workers=1) as pool:
                    unit_id = pool.submit(seed_unit, UUID(guest.json()["user"]["id"])).result()
                    pool.submit(prepare_profile, UUID(guest.json()["user"]["id"])).result()
                page = context.new_page()
                page.add_init_script(
                    f"sessionStorage.setItem('edumind:last-learning-unit', '{unit_id}')"
                )
                page.goto(FRONTEND)
                expect(page.get_by_test_id("debate-panel")).to_be_visible()
                page.get_by_test_id("debate-question").fill("频繁随机访问时怎么选？")
                page.get_by_test_id("start-debate").click()
                expect(page.get_by_test_id("debate-perspectives")).to_contain_text("随机访问")
                expect(page.get_by_test_id("debate-moderator")).to_contain_text("条件")
                page.get_by_test_id("debate-perspectives").locator("article").first.get_by_role(
                    "button", name="这个视角有帮助"
                ).click()
                expect(page.get_by_test_id("perspective-feedback-status")).to_contain_text(
                    "反馈已记录"
                )
                profile = page.evaluate("""async () => {
                    const response = await fetch('/api/profile/me', {credentials: 'same-origin'});
                    return {status: response.status, body: await response.json()};
                }""")
                assert profile["status"] == 200, profile["body"]
                assert profile["body"]["cognitive_style"]["preference_persona"] == "performance"
                page.reload()
                expect(page.get_by_test_id("debate-perspectives")).to_be_visible()
                page.get_by_test_id("exit-debate").click()
                expect(page.get_by_test_id("classroom-panel")).to_be_visible()
                receipt = page.evaluate("""async (unitId) => {
                    const response = await fetch(`/api/learning-units/${unitId}/classroom`,
                        {credentials: 'same-origin'});
                    return {status: response.status, body: await response.json()};
                }""", str(unit_id))
                assert receipt["status"] == 200, receipt["body"]
                snapshot = receipt["body"]
                assert snapshot["scene_key"] == "intro"
                assert snapshot["scene_progress"] == 0
                assert snapshot["revision"] == 3
                print("Real HTTP debate browser integration passed", flush=True)
            finally:
                browser.close()
    finally:
        stop(web)
        stop(backend)


if __name__ == "__main__":
    run()
