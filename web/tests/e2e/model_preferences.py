"""Browser proof of explicit model preferences; all API responses are synthetic."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:4188")
    parser.add_argument("--evidence", required=True)
    args = parser.parse_args()
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    ids = ["00000000-0000-4000-8000-000000000001", "00000000-0000-4000-8000-000000000002"]
    connections = [{"id": cid, "provider_type": "openai-compatible" if index == 0 else "ollama",
                    "display_name": "云端 A" if index == 0 else "本地 B", "base_url": "https://a.example/v1" if index == 0 else "http://localhost:11434",
                    "is_local": index == 1, "enabled": True, "config_version": 2,
                    "credential_mode": "persistent" if index == 0 else "none", "credential_state": "present",
                    "credential_expires_at": "2030-01-01T00:00:00Z"} for index, cid in enumerate(ids)]
    preferences: dict[str, dict] = {}
    calls: list[tuple[str, str]] = []
    failures: list[str] = []

    def route_api(route) -> None:
        path = urlsplit(route.request.url).path
        if not path.startswith("/api/"):
            route.continue_()
            return
        method = route.request.method
        calls.append((method, path))
        if path == "/api/runtime":
            value = {"mode": "catalog_only"}
        elif path == "/api/auth/session":
            value = {"user": {"id": "owner"}, "csrf_token": "csrf"}
        elif path == "/api/catalog":
            value = {"status": "not_ready", "releases": []}
        elif path == "/api/providers/connections":
            value = {"items": connections}
        elif path.endswith("/models"):
            value = {"connection_id": path.split("/")[-2], "config_version": 2, "models": [], "refreshed_at": None}
        elif path == "/api/model-preferences":
            value = {"preferences": list(preferences.values())}
        elif path.startswith("/api/model-preferences/") and method == "PUT":
            body = route.request.post_data_json
            assert route.request.headers["x-csrf-token"] == "csrf"
            profile = path.split("/")[-1]
            assert body["expected_version"] == preferences.get(profile, {}).get("version", 0)
            assert body["consent_accepted"] is True
            assert body["route"]["config_version"] == 2
            for item in body["fallbacks"]:
                assert item["on_errors"] and set(item["on_errors"]) <= {"TIMEOUT", "RATE_LIMITED", "TEMPORARILY_UNAVAILABLE"}
            value = {"task_profile": profile, "version": body["expected_version"] + 1,
                     "route": body["route"], "fallbacks": body["fallbacks"], "state": "available"}
            preferences[profile] = value
        else:
            failures.append(f"Unexpected API {method} {path}")
            route.fulfill(status=500, json={"code": "UNEXPECTED_MOCK_ROUTE"})
            return
        route.fulfill(json=value)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1050})
            page.on("pageerror", lambda error: failures.append(str(error)))
            page.route("**/api/**", route_api)
            page.goto(args.url)
            page.wait_for_load_state("networkidle")
            evidence.joinpath("initial-dom.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
            expect(page.get_by_role("button", name="档位与数据去向", exact=True)).to_be_visible()
            page.get_by_role("button", name="档位与数据去向", exact=True).click()
            expect(page.get_by_role("heading", name="默认 · 用户默认连接", exact=True)).to_be_visible()
            assert not any(method != "GET" for method, _ in calls)
            expect(page.get_by_role("button", name="保存当前档位")).to_be_disabled()
            page.get_by_label("主目标连接", exact=False).select_option(ids[0])
            page.get_by_label("主目标模型 ID", exact=False).fill("model-a")
            page.locator(".preferences-consent input").check()
            page.get_by_role("button", name="保存当前档位").click()
            expect(page.get_by_role("status")).to_contain_text("本次没有调用模型")
            assert preferences["default"]["fallbacks"] == []
            expect(page.locator(".preferences-resolution")).to_contain_text("快速 · 用户默认连接")
            page.get_by_role("button", name="添加回退目标").click()
            page.get_by_label("回退 1连接", exact=False).select_option(ids[1])
            page.get_by_label("回退 1模型 ID", exact=False).fill("local-model")
            page.locator(".fallback-settings article").get_by_label("超时", exact=True).check()
            page.locator(".preferences-consent input").check()
            page.get_by_role("button", name="保存当前档位").click()
            expect(page.get_by_role("status")).to_be_visible()
            assert preferences["default"]["fallbacks"][0]["on_errors"] == ["TIMEOUT"]
            expect(page.locator(".preferences-resolution")).to_contain_text("本地 B · ollama · local-model · 服务端白名单目标")
            page.get_by_role("button", name="独立审核", exact=True).click()
            page.get_by_label("主目标连接", exact=False).select_option(ids[1])
            page.get_by_label("主目标模型 ID", exact=False).fill("review-model")
            page.locator(".preferences-consent input").check()
            page.get_by_role("button", name="保存当前档位").click()
            expect(page.get_by_role("status")).to_be_visible()
            assert preferences["review"]["route"]["data_categories"] == ["content_for_review"]
            assert not preferences["review"]["fallbacks"]
            page.screenshot(path=str(evidence / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(evidence / "mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.get_by_role("button", name="返回课程", exact=True).click()
            expect(page.get_by_text("课程正在准备", exact=False)).to_be_visible()
            assert not any(path.endswith(("/test", "/refresh", "/chat", "/completions")) for _, path in calls)
            assert sum(method == "PUT" for method, _ in calls) == 3
            assert not failures, failures
            evidence.joinpath("requests.json").write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding="utf-8")
            print("PASS: read-only opening, default inheritance, explicit ordered fallback, independent review, target/data receipt, mobile fit, catalog retained. Real Provider requests=0.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
