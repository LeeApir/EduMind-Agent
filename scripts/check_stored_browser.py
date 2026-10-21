"""Real browser reads of stored results. Failures retain DOM, screenshot and safe network data."""

import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "local-materials/phase-1-browser-evidence-r01"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--case", choices=["pending", "rejected", "published"], required=True
    )
    parser.add_argument("--attempt", default="r01", choices=["r01", "r02"])
    args = parser.parse_args()
    directory = BASE / (args.case + "-" + args.attempt)
    info = json.loads((directory / "server-info.json").read_text())
    network = []
    errors = []
    failure = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1000})
        page.on(
            "response",
            lambda r: network.append(
                dict(
                    path=r.url.split("18179")[-1],
                    status=r.status,
                    method=r.request.method,
                )
            )
            if "/api/" in r.url
            else None,
        )
        page.on("pageerror", lambda e: errors.append(str(e)))
        try:
            page.goto(
                "http://127.0.0.1:18179/api/__acceptance/bootstrap",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            page.wait_for_url("http://127.0.0.1:18179/", timeout=10000)
            # Pending-state polling makes global quietness an unsuitable success gate.
            # Require the final page and concrete UI/API state below instead.
            idle_warning = None
            try:
                page.wait_for_load_state("networkidle", timeout=2000)
            except Exception:
                idle_warning = (
                    "networkidle not reached; explicit final URL/UI/API gates used"
                )
            selector = {
                "pending": "human-review-state",
                "rejected": "review-rejected-state",
                "published": "published-state",
            }[args.case]
            page.get_by_test_id(selector).wait_for(timeout=10000)
            path = f"/api/learning-units/{info['learning_unit_id']}"
            actual = page.request.get(
                "http://127.0.0.1:18179"
                + path
                + f"?publication_version={info['version']}"
            )
            wrong = page.request.get(
                "http://127.0.0.1:18179" + path + "?publication_version=999999"
            )
            blocked = page.request.post(
                "http://127.0.0.1:18179/api/learning-sessions",
                data={"goal": "NEVER_GENERATE"},
            )
            assert blocked.status == 403
            anonymous = p.request.new_context()
            try:
                unauthenticated = anonymous.get("http://127.0.0.1:18179" + path)
                assert unauthenticated.status in (401, 403)
            finally:
                anonymous.dispose()
            assert wrong.status == 404
            if args.case == "published":
                assert actual.status == 200
                payload = actual.json()
                (directory / "formal-response.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
                )
                assert (
                    payload["publication_version"] == info["version"]
                    and len(payload["scenes"]) == 3
                )
                page.get_by_test_id("explanation-tab").wait_for(timeout=5000)
                assert page.get_by_test_id("explanation-tab").inner_text().strip()
            else:
                assert actual.status == 404
                assert page.get_by_test_id("published-state").count() == 0
                assert page.get_by_test_id("explanation-tab").count() == 0
            assert not errors
            outcome = dict(
                exact_unit_status=actual.status,
                wrong_version_status=wrong.status,
                generation_write_status=blocked.status,
                anonymous_read_status=unauthenticated.status,
            )
        except Exception as exc:
            failure = type(exc).__name__ + ": " + str(exc)[:1200]
            outcome = {}
        finally:
            text = page.locator("body").inner_text()
            (directory / "visible.txt").write_text(text)
            page.screenshot(path=str(directory / "screen.png"), full_page=True)
            report = dict(
                case=args.case,
                source=info,
                status="fail" if failure else "pass",
                failure=failure,
                observations=outcome,
                page_errors=errors,
                network=network,
                real_provider_calls=0,
                networkidle_warning=locals().get("idle_warning"),
                ui_source="pnpm build output + actual read-only backend, no mocked HTTP replies",
                screenshot_sha256=hashlib.sha256(
                    (directory / "screen.png").read_bytes()
                ).hexdigest(),
            )
            (directory / "browser-result.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n"
            )
            print(json.dumps(report, ensure_ascii=False))
            print(text[:2500])
            browser.close()
    if failure:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
