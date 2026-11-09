"""Verify an approved archived course through the real private application."""

import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from unittest.mock import patch
from uuid import UUID

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from app.models.free_course import FreeCourse, FreeCourseVersion  # noqa: E402
from app.models.free_course_scheduler import FreeCourseAttempt  # noqa: E402
from app.models.free_course_writes import FreeCourseOperation, FreeCourseReceipt  # noqa: E402
from app.models.free_scene_generation import FreeSceneGenerationResult  # noqa: E402
from app.services import free_scene_availability as availability  # noqa: E402
from app.services import head_course_archived_import as archive  # noqa: E402
from app.services.free_course_snapshots import SnapshotError  # noqa: E402
from app.services.head_course_replay import mapping as legacy_mapping  # noqa: E402
from scripts.head_course_goal import database  # noqa: E402

WORK = Path("/tmp/edumind-t112")
URL = "http://127.0.0.1:5202"
CLI = [sys.executable, str(ROOT / "scripts/import_head_course_archive.py")]


async def verify_rollback(db, owner, source):
    async def counts():
        models = (
            FreeCourse,
            FreeCourseVersion,
            FreeCourseOperation,
            FreeCourseReceipt,
            FreeSceneGenerationResult,
            FreeCourseAttempt,
        )
        return [
            await db.scalar(
                select(func.count()).select_from(model).where(model.user_id == owner)
            )
            for model in models
        ]

    before = await counts()
    commit = availability.commit_scene

    async def fail_after_ready(*args, **kwargs):
        await commit(*args, **kwargs)
        raise SnapshotError("TEST_ROLLBACK_AFTER_READY")

    with patch.object(availability, "commit_scene", fail_after_ready):
        try:
            await archive.import_course(db, owner, source_batch=source)
        except SnapshotError as error:
            assert str(error) == "TEST_ROLLBACK_AFTER_READY"
        else:
            raise AssertionError("injected failure not reached")
    assert await counts() == before == [0] * len(before)


async def verify_storage(db, binding, original):
    course = UUID(binding["course_id"])
    (row,) = (
        await db.scalars(
            select(FreeSceneGenerationResult).where(
                FreeSceneGenerationResult.course_id == course
            )
        )
    ).all()
    assert row.sent_attempts == 0 and row.usage_json is None
    assert row.input_snapshot["archived_import"] == original
    assert (
        await db.scalar(
            select(func.count())
            .select_from(FreeCourseAttempt)
            .where(FreeCourseAttempt.course_id == course)
        )
        == 0
    )


def check_frames(page, visual, code):
    panel = page.get_by_role("region", name="过程演示与代码对照", exact=True)
    frame_element = panel.locator(".head-replay-frame")
    highlight = panel.locator(".active-code-line")
    rendered = [
        re.sub(r"^\d+  ", "", line)
        for line in panel.locator(".course-code-line").all_text_contents()
    ]
    assert "\n".join(rendered) == code.rstrip()
    steps = visual["steps"]
    assert len(steps) == 13
    frames = []
    for index, step in enumerate(steps):
        frame = step["head_frame"]
        expect(frame_element).to_have_attribute("data-frame", frame["frame_id"])
        expect(panel.locator(".head-step-note")).to_have_text(frame["note"])
        assert json.loads(panel.locator("details pre").text_content()) == frame
        if frame["line"] is None:
            expect(highlight).to_have_count(0)
        else:
            expect(highlight).to_have_attribute("data-line", str(frame["line"]))
        if frame["locals_scope"] == "inactive":
            expect(panel).to_contain_text("不在作用域")
        frames.append(
            {
                "frame": frame["frame_id"],
                "line": frame["line"],
                "scope": frame["locals_scope"],
            }
        )
        if index < len(steps) - 1:
            panel.get_by_role("button", name="下一步", exact=True).click()
    panel.get_by_role("button", name="上一步", exact=True).click()
    expect(frame_element).to_have_attribute("data-frame", "f11")
    panel.get_by_role("button", name="重置", exact=True).click()
    expect(frame_element).to_have_attribute("data-frame", "f00")
    panel.get_by_role("button", name="播放", exact=True).click()
    expect(frame_element).not_to_have_attribute("data-frame", "f00", timeout=4500)
    panel.get_by_role("button", name="暂停", exact=True).click()
    paused = frame_element.get_attribute("data-frame")
    page.wait_for_timeout(1500)
    expect(frame_element).to_have_attribute("data-frame", paused)
    panel.get_by_role("button", name="重置", exact=True).click()
    expect(frame_element).to_have_attribute("data-frame", "f00")
    return frames


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", choices=tuple(archive.IMPORT_RULES), default=archive.BATCH
    )
    parser.add_argument("--artifacts", type=Path, default=WORK)
    args = parser.parse_args()
    if args.source != archive.BATCH and args.artifacts == WORK:
        parser.error("Choose a separate artifacts directory")
    args.artifacts.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.environ.update(json.loads((WORK / "env.json").read_text()))
    original, assembled = archive.mapping(args.source)
    content_r01 = args.source == archive.CONTENT_BATCH
    for slot in ("C01", "C02"):
        legacy_mapping(slot)
    try:
        legacy_mapping("head-fixed-aiapi-r05")
    except SnapshotError as error:
        assert str(error) == "REPLAY_SOURCE_INVALID"
    else:
        raise AssertionError("T107 admitted an unapproved source")
    errors = []
    posts = []

    def run_db(action):
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(database(action))).result()

    def read(page, path):
        return page.evaluate(
            "async path => { const r = await fetch(path); return [r.status, await r.json()]; }",
            path,
        )

    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda req: posts.append(req.url) if req.method == "POST" else None,
        )
        page.goto(URL)
        page.wait_for_load_state("networkidle")
        status, session = read(page, "/api/auth/session")
        assert status == 200, status
        owner = session["user"]["id"]
        run_db(lambda db: verify_rollback(db, UUID(owner), args.source))

        def load():
            result = subprocess.run(
                [*CLI, "--owner", owner, "--source", args.source],
                check=True,
                capture_output=True,
                text=True,
            )
            return json.loads(result.stdout)

        first, second = load(), load()
        assert first["imported"] is True and second == {**first, "imported": False}
        run_db(lambda db: verify_storage(db, first, original))
        course, sid = first["course_id"], first["scene_id"]
        route = f"{URL}/api/free-courses/{course}"
        scene_route = f"{route}/versions/2/scenes/{sid}"
        page.get_by_role("button", name="重新读取", exact=True).click()
        page.get_by_role("button", name="继续学习 →", exact=True).click()
        source = page.get_by_label("新课程来源", exact=True)
        if content_r01:
            expect(source).to_contain_text(
                "AIAPI content r01 封存正文导入，独立教学审核通过"
            )
            expect(source).to_contain_text("响应标签 gpt-6.1-sol，回报 store=false")
            expect(source).to_contain_text("HEAD_AIAPI_ENVELOPE")
        else:
            expect(source).to_contain_text("从已封存响应提取的正文，独立教学评估通过")
            expect(source).to_contain_text("AIAPI r05 原响应 AIAPI_ENVELOPE")
        expect(source).to_contain_text("实际模型与存储状态未确认。")
        page.wait_for_load_state("networkidle")
        status, scene = read(page, scene_route)
        assert status == 200
        assert scene["generation_source"] == assembled["generation_source"]
        assert not (
            {"answer_key", "solution"}
            & set(re.findall(r'"([a-z_]+)"\s*:', json.dumps(scene)))
        )
        paragraphs = [
            block["markdown"]
            for block in assembled["blocks"]
            if block["kind"] == "text"
        ]
        assert [
            text.strip() for text in page.locator(".scene-prose").all_text_contents()
        ] == paragraphs
        visual = next(b for b in scene["blocks"] if b["kind"] == "visualization")
        assert visual == next(
            b for b in assembled["blocks"] if b["kind"] == "visualization"
        )
        code = next(b["source"] for b in assembled["blocks"] if b["kind"] == "code")
        frames = check_frames(page, visual, code)

        other = browser.new_context()
        other_page = other.new_page()
        other_page.goto(URL)
        other_page.wait_for_load_state("networkidle")
        assert read(other_page, "/api/auth/session")[0] == 200
        assert read(other_page, scene_route)[0] == 404
        exercise = page.get_by_role("region", name="随堂练习", exact=True)
        items = next(b["items"] for b in assembled["blocks"] if b["kind"] == "exercise")
        for item in items:
            expect(exercise).to_contain_text(item["question"])
        answers = ["i0", "[11, 30,40]", "[30,\n40]", "1"]
        feedback = []
        for values, score in ((["t0", "[40]", "[11]", "0"], 0), (answers, 100)):
            for box, value in zip(
                exercise.locator("textarea").all(), values, strict=True
            ):
                box.fill(value)
            with page.expect_response(
                lambda r: r.url == route + "/attempts" and r.request.method == "POST"
            ) as response:
                exercise.get_by_role("button", name="提交本次作答", exact=True).click()
            attempt_route = f"{route}/attempts/{response.value.json()['attempt_id']}"
            expect(exercise).to_contain_text(f"与暂定参考的匹配比例：{score}%")
            status, attempt = read(page, attempt_route)
            assert status == 200
            assert attempt["binding"]["course_version"] == 2
            assert (
                attempt["reliability"] == "provisional"
                and attempt["mastery_effect"] == "course_only"
            )
            assert len(attempt["question_results"]) == 4
            for question, item in zip(attempt["question_results"], items, strict=True):
                assert question["question_id"] == item["question_id"]
                assert question["matches_reference"] is bool(score)
                assert question["explanation"] == item["solution"]
            feedback.append(
                {"percent": score, "questions": len(attempt["question_results"])}
            )
            if score == 0:
                exercise.get_by_role(
                    "button", name="继续完善或新作答", exact=True
                ).click()
        assert read(other_page, attempt_route)[0] == 404
        before = posts.count(route + "/attempts")
        page.reload()
        page.wait_for_load_state("networkidle")
        expect(exercise).to_contain_text("与暂定参考的匹配比例：100%")
        assert read(page, scene_route) == [200, scene]
        assert read(page, attempt_route) == [200, attempt]
        assert [
            box.input_value() for box in exercise.locator("textarea").all()
        ] == answers
        assert posts.count(route + "/attempts") == before == 2
        assert not errors, errors
        page.screenshot(path=str(args.artifacts / "browser.png"), full_page=True)
        browser.close()
    result = dict(
        candidate_digest=original["candidate"]["candidate_digest"],
        version=2,
        paragraphs=len(paragraphs),
        frames=frames,
        playback_controls=True,
        feedback=feedback,
        refresh_preserved_scene_attempt_and_inputs=True,
        refresh_post_requests=0,
        cross_owner_scene_and_attempt_404=True,
        public_scene_answers_absent=True,
        database_import_idempotent=True,
        rollback_after_ready=True,
        provider_calls=0,
    )
    if content_r01:
        result["binding"] = first
        result["batch"] = args.source
        result["entry"] = URL + "/"
    (args.artifacts / "browser-results.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(
        "PASS: private import, idempotency, rollback, 13 frames, feedback, and refresh"
    )


if __name__ == "__main__":
    main()
