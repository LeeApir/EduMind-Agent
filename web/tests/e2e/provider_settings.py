"""Connection settings browser contract with synthetic same-origin API only."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:4187")
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--native-type", choices=["anthropic", "gemini", "spark"])
    args = parser.parse_args()
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    cid = "00000000-0000-4000-8000-000000000001"
    caps = dict.fromkeys(["streaming", "structured_output", "tool_calling", "vision", "embedding", "tts", "asr"])
    caps.update(source="unknown", version="mock-v1")
    items = [{"id": cid, "provider_type": "openai-compatible", "display_name": "我的兼容服务",
              "base_url": "https://provider.example/v1", "is_local": False, "enabled": True,
              "config_version": 1, "credential_mode": "persistent", "credential_state": "present",
              "credential_expires_at": "2026-10-05T00:00:00Z"}]
    calls: list[tuple[str, str]] = []
    failures: list[str] = []

    def route_api(route) -> None:
        path = urlsplit(route.request.url).path
        if not path.startswith("/api/"):
            route.continue_()
            return
        method = route.request.method
        calls.append((method, path))
        status = 200
        if path == "/api/runtime":
            result = {"mode": "catalog_only"}
        elif path == "/api/auth/session":
            result = {"user": {"id": "owner"}, "csrf_token": "csrf"}
        elif path == "/api/catalog":
            result = {"status": "not_ready", "releases": []}
        elif path.endswith("/models"):
            result = {"connection_id": cid, "config_version": items[0]["config_version"],
                      "models": [{"id": "mock-model", "capabilities": caps}], "refreshed_at": "2026-10-04T00:00:00Z"}
        elif path.endswith("/models/refresh"):
            status, result = 403, {"code": "BUDGET_NOT_AUTHORIZED", "message": "synthetic-secret"}
        elif path.endswith("/temporary-credentials"):
            body = route.request.post_data_json
            assert body["purpose"] == "connection_test" and body["consent"]["data_categories"] == ["probe"]
            result = {"handle": "h" * 40, "config_version": items[0]["config_version"],
                      "expires_at": "2026-10-04T01:00:00Z", "operation_deadline_seconds": 10}
        elif path.endswith("/test"):
            body = route.request.post_data_json
            assert body["consent"]["config_version"] == items[0]["config_version"]
            assert body["consent"]["model_id"] == "mock-model" and "secret" not in body
            result = {"connection_id": cid, "config_version": items[0]["config_version"],
                      "model_id": "mock-model", "target": items[0]["base_url"], "is_local": False,
                      "requests": 1, "usage": None, "capabilities": caps}
        elif method == "PATCH" and path.endswith(cid):
            body = route.request.post_data_json
            if "blocked.example" in body["base_url"]:
                status, result = 422, {"code": "INVALID_TARGET", "message": "synthetic-secret"}
            else:
                assert route.request.headers["if-match"] == str(items[0]["config_version"])
                items[0].update({key: value for key, value in body.items() if key != "secret"})
                items[0]["config_version"] += 1
                result = items[0]
        elif path == "/api/providers/connections" and method == "GET":
            result = {"items": items}
        else:
            failures.append(f"Unexpected Mock route {method} {path}")
            status, result = 500, {"code": "UNEXPECTED_MOCK_ROUTE"}
        route.fulfill(status=status, json=result)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1050})
            page.on("pageerror", lambda error: failures.append(str(error)))
            page.route("**/api/**", route_api)
            page.goto(args.url)
            page.wait_for_load_state("networkidle")
            evidence.joinpath("initial-dom.txt").write_text(page.locator("body").inner_text(), encoding="utf-8")
            page.screenshot(path=str(evidence / "initial.png"), full_page=True)
            expect(page.get_by_role("button", name="模型设置", exact=True)).to_be_visible()
            page.get_by_role("button", name="模型设置", exact=True).click()
            expect(page.get_by_label("模型 ID", exact=True)).to_have_value("mock-model")
            assert not any(method == "POST" for method, path in calls if path.startswith("/api/providers"))
            expect(page.get_by_role("button", name="测试连接一次")).to_be_disabled()
            expect(page.locator(".provider-capabilities dd")).to_have_text(["未知"] * 7)
            if args.native_type:
                page.get_by_label("服务类型", exact=True).select_option(args.native_type)
            page.get_by_label("替换 Key", exact=False).fill("synthetic-secret")
            assert page.locator("#provider-key").get_attribute("type") == "password"
            page.get_by_role("button", name="保存连接", exact=True).click()
            expect(page.locator("#provider-key")).to_have_value("")
            expect(page.get_by_role("status")).to_contain_text("连接已保存")
            page.locator(".provider-consent input").check()
            page.get_by_role("button", name="测试连接一次").click()
            expect(page.get_by_role("status")).to_contain_text("文本连接测试完成")
            expect(page.locator(".provider-destination code")).to_have_text(items[0]["base_url"])
            page.screenshot(path=str(evidence / "desktop.png"), full_page=True)
            page.locator(".provider-consent input").check()
            page.get_by_role("button", name="刷新模型一次").click()
            expect(page.get_by_role("alert")).to_contain_text("尚未授权测试预算")
            page.get_by_label("Key 保存方式").select_option("temporary")
            page.get_by_role("button", name="保存连接", exact=True).click()
            expect(page.get_by_role("status")).to_contain_text("连接已保存")
            page.get_by_label("本次操作的临时 Key").fill("synthetic-secret")
            page.locator(".provider-consent input").check()
            page.get_by_role("button", name="测试连接一次").click()
            expect(page.get_by_role("status")).to_contain_text("文本连接测试完成")
            expect(page.get_by_label("本次操作的临时 Key")).to_have_value("")
            storage = page.evaluate("JSON.stringify({local: {...localStorage}, session: {...sessionStorage}})")
            assert "synthetic-secret" not in storage and "h" * 40 not in storage
            assert "synthetic-secret" not in page.content() and "h" * 40 not in page.content()
            page.get_by_label("服务地址", exact=True).fill("https://blocked.example/v1")
            page.get_by_role("button", name="保存连接", exact=True).click()
            expect(page.get_by_role("alert")).to_contain_text("服务地址被拒绝")
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(evidence / "mobile.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.get_by_role("button", name="返回课程", exact=True).click()
            expect(page.get_by_text("课程正在准备", exact=False)).to_be_visible()
            assert sum(path.endswith("/test") for _, path in calls) == 2
            assert sum(path.endswith("/models/refresh") for _, path in calls) == 1
            assert not failures, failures
            evidence.joinpath("requests.json").write_text(json.dumps(calls, ensure_ascii=False, indent=2), encoding="utf-8")
            print("PASS: settings reads only on open; persistent/temporary Key cleared; exact consent; fixed failures; mobile fit; catalog return. Real Provider requests=0.")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
