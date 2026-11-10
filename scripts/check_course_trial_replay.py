"""Verify both actual sealed trials in the same isolated app and browser guest session."""

import argparse
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import UUID

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.models.free_course import FreeCourse
from app.models.free_course_scheduler import FreeCourseAttempt
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services.course_trial_replay import import_course, projection, require_database
from app.services.course_trial_sources import ARCHIVES
from app.services.free_course_snapshots import SnapshotError
from scripts.check_head_course_archive_browser import check_frames
from scripts.course_trial import ROOT, read_frozen

WORK = Path("/tmp/edumind-t120")
URL = "http://127.0.0.1:5213/"


def api(page, route):
    return page.evaluate(
        "async p => {const r=await fetch(p);return [r.status,await r.json()];}", route
    )


def seal_snapshot():
    root = Path.home() / ".local/share/edumind"
    batches = [archive.batch for archive in ARCHIVES.values()] + [
        "head-empty-deepseek-r02"
    ]
    return {
        str(path.relative_to(root)): sha256(path.read_bytes()).hexdigest()
        for batch in batches
        for path in (root / batch).iterdir()
        if path.is_file() and path.name != "raw.key"
    }


async def check_rejections(owner, archives):
    engine = create_database_engine()
    try:
        async with AsyncSession(engine) as db, db.begin():

            async def count():
                return await db.scalar(
                    select(func.count())
                    .select_from(FreeCourse)
                    .where(FreeCourse.user_id == owner)
                )

            before = await count()
            head, head_review = archives["head"]
            stack, stack_review = archives["stack"]
            unauthorized = deepcopy(head)
            unauthorized["approval"]["explicit_user_authorization"] = False
            stack_revision = {
                **stack,
                "parent_digest": head["candidate"]["candidate_digest"],
            }
            mixed_material = {
                **stack,
                "materials_digest": head["candidate"]["payload"]["materials"][
                    "materials_digest"
                ],
            }
            cases = [
                ("head", stack, stack_review, "TRIAL_REPLAY_CANDIDATE"),
                ("stack", head, head_review, "TRIAL_REPLAY_CANDIDATE"),
                ("head", head, stack_review, "TRIAL_REPLAY_REVIEW"),
                ("stack", stack, head_review, "TRIAL_REPLAY_REVIEW"),
                ("head", unauthorized, head_review, "TRIAL_REPLAY_REVISION"),
                ("stack", stack_revision, stack_review, "TRIAL_REPLAY_BINDING"),
                ("stack", mixed_material, stack_review, "TRIAL_REPLAY_BINDING"),
            ]
            for topic, record, review, reason in cases:
                try:
                    await import_course(db, owner, topic, record, review)
                except SnapshotError as error:
                    assert error.code == reason, error.code
                else:
                    raise AssertionError(f"unexpected admission for {topic}: {reason}")
            assert await count() == before
            return [reason for _, _, _, reason in cases]
    finally:
        await engine.dispose()


async def check_storage(bindings):
    engine = create_database_engine()
    try:
        async with AsyncSession(engine) as db:
            for topic, binding in bindings.items():
                course_id = UUID(binding["course_id"])
                (row,) = (
                    await db.scalars(
                        select(FreeSceneGenerationResult).where(
                            FreeSceneGenerationResult.course_id == course_id
                        )
                    )
                ).all()
                assert row.sent_attempts == 0 and row.usage_json is None
                assert row.input_snapshot["trial_replay"]["topic"] == topic
                assert row.response_json["replay_source"]["new_provider_calls"] == 0
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(FreeCourseAttempt)
                        .where(FreeCourseAttempt.course_id == course_id)
                    )
                    == 0
                )
    finally:
        await engine.dispose()


def stack_frames(page, steps, code):
    reference = json.loads(
        (
            ROOT
            / "docs/acceptance/phase-1.5-stack-lifo-t119/independent-reference.json"
        ).read_bytes()
    )
    panel = page.get_by_role("region", name="过程演示与代码对照", exact=True)
    frame = panel.locator("[data-frame]")
    rendered = [
        line.split("  ", 1)[1]
        for line in panel.locator(".course-code-line").all_text_contents()
    ]
    assert "\n".join(rendered) == code.rstrip()
    for i, (step, ref) in enumerate(zip(steps, reference["main"], strict=True)):
        if i:
            panel.get_by_role("button", name="下一步", exact=True).click()
        expect(frame).to_have_attribute("data-frame", ref["frame_id"])
        highlight = frame.locator(".active-code-line")
        expect(highlight).to_have_attribute("data-line", str(ref["line"]))
        expect(highlight).to_contain_text(code.splitlines()[ref["line"] - 1].strip())
        expect(frame).to_contain_text(step["stack_frame"]["note"])
        expect(frame).to_contain_text(
            f"本步出栈结果：{ref['popped'] if ref['popped'] is not None else '无'}"
        )
        assert [
            int(value) for value in frame.locator("ol strong").all_text_contents()
        ] == ref["values"]
        if ref["top"] is None:
            expect(frame).to_contain_text("栈为空，没有栈顶")
        else:
            expect(frame.locator(".element-highlight strong")).to_have_text(
                str(ref["top"])
            )
    panel.get_by_role("button", name="上一步", exact=True).click()
    expect(frame).to_have_attribute("data-frame", "f3")
    panel.get_by_role("button", name="重置", exact=True).click()
    expect(frame).to_have_attribute("data-frame", "f0")
    panel.get_by_role("button", name="播放", exact=True).click()
    expect(frame).to_have_attribute("data-frame", "f1")
    panel.get_by_role("button", name="暂停", exact=True).click()
    page.wait_for_timeout(1450)
    expect(frame).to_have_attribute("data-frame", "f1")
    return reference["main"]


def check_course(page, other, topic, binding, goal, expected, posts):
    page.get_by_role("article").filter(
        has=page.get_by_role("heading", name=goal, exact=True)
    ).get_by_role("button", name="继续学习 →", exact=True).click()
    source = page.get_by_label("课程来源", exact=True)
    expect(source).to_contain_text("历史封存回放")
    expect(source).to_contain_text("本次 Provider 调用 0")
    expect(source).to_contain_text("模型规划" if topic == "head" else "固定提纲")
    expect(source).to_contain_text("原授权引用修订" if topic == "head" else "原首稿")
    cid, sid = binding["course_id"], binding["scene_id"]
    route = f"/api/free-courses/{cid}"
    scene_path = f"{route}/versions/2/scenes/{sid}"
    status, scene = api(page, scene_path)
    assert status == 200 and scene["replay_source"] == expected["replay_source"]
    assert "generation_source" not in scene and scene["actions"] == expected["actions"]
    assert '"answer_key"' not in json.dumps(scene) and '"solution"' not in json.dumps(
        scene
    )
    assert api(other, scene_path)[0] == 404

    paragraphs = [
        block["markdown"] for block in expected["blocks"] if block["kind"] == "text"
    ]
    assert [
        value.strip() for value in page.locator(".scene-prose").all_text_contents()
    ] == paragraphs
    visual = next(
        block for block in scene["blocks"] if block["kind"] == "visualization"
    )
    assert visual == next(
        block for block in expected["blocks"] if block["kind"] == "visualization"
    )
    code = next(
        block["source"] for block in expected["blocks"] if block["kind"] == "code"
    )
    assert code == next(
        block["source"] for block in scene["blocks"] if block["kind"] == "code"
    )
    frames = (
        check_frames(page, visual, code)
        if topic == "head"
        else stack_frames(page, visual["steps"], code)
    )
    exercise = page.get_by_role("region", name="随堂练习", exact=True)
    items = next(
        block["items"] for block in expected["blocks"] if block["kind"] == "exercise"
    )
    assert len(items) == 4
    for item in items:
        expect(exercise).to_contain_text(item["question"])
        assert (
            item["solution"] not in page.locator("main.course-workspace").inner_text()
        )
    wrong = [
        "[999]" if item["input_type"] == "json_integer_array" else "999"
        for item in items
    ]
    right = [item["answer_key"] for item in items]
    attempts = []
    for answers, score in ((wrong, 0), (right, 100)):
        for box, value in zip(exercise.locator("textarea").all(), answers, strict=True):
            box.fill(value)
        with page.expect_response(
            lambda resp: resp.url.endswith(route + "/attempts")
            and resp.request.method == "POST"
        ) as submitted:
            exercise.get_by_role("button", name="提交本次作答", exact=True).click()
        assert submitted.value.ok
        attempt_id = submitted.value.json()["attempt_id"]
        attempt_path = f"{route}/attempts/{attempt_id}"
        expect(exercise).to_contain_text(f"与暂定参考的匹配比例：{score}%")
        status, attempt = api(page, attempt_path)
        assert status == 200 and attempt["binding"]["course_version"] == 2
        for feedback, item in zip(attempt["question_results"], items, strict=True):
            assert feedback["question_id"] == item["question_id"]
            assert feedback["matches_reference"] is bool(score)
            assert feedback["explanation"] == item["solution"]
        assert api(other, attempt_path)[0] == 404
        attempts.append(dict(attempt_id=attempt_id, score=score))
        if not score:
            exercise.get_by_role("button", name="继续完善或新作答", exact=True).click()

    page.reload()
    page.wait_for_load_state("networkidle")
    expect(exercise).to_contain_text("与暂定参考的匹配比例：100%")
    assert api(page, scene_path) == [200, scene] and api(page, attempt_path) == [
        200,
        attempt,
    ]
    assert [box.input_value() for box in exercise.locator("textarea").all()] == right
    assert sum(url.endswith(route + "/attempts") for url in posts) == 2
    page.get_by_role("button", name="← 我的学习", exact=True).click()
    return dict(
        binding=binding,
        source=scene["replay_source"],
        scene_version_id=scene["scene_version_id"],
        exercise_version_id=scene["blocks"][-1]["exercise_version_id"],
        reading_blocks=len(paragraphs),
        frames=frames,
        attempts=attempts,
        refresh_post_requests=0,
        answer_and_owner_isolation=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=WORK / "verification")
    args = parser.parse_args()
    args.artifacts.mkdir(mode=0o700, exist_ok=False)
    os.environ.update(json.loads((WORK / "env.json").read_bytes()))
    require_database()
    sealed = seal_snapshot()
    archives = {topic: read_frozen(topic) for topic in ARCHIVES}
    profile = str(args.artifacts / "browser-profile")
    with sync_playwright() as driver:
        browser = driver.chromium.launch_persistent_context(profile, headless=True)
        page = browser.pages[0]
        page.goto(URL)
        page.wait_for_load_state("networkidle")
        status, session = api(page, "/api/auth/session")
        assert status == 200 and session["user"]["is_guest"]
        owner = UUID(session["user"]["id"])
        browser.close()

    rejected = asyncio.run(check_rejections(owner, archives))
    bindings = {}
    for topic in ARCHIVES:
        command = [
            sys.executable,
            "-m",
            "scripts.course_trial",
            "publish",
            "--topic",
            topic,
            "--owner",
            str(owner),
        ]
        published = json.loads(subprocess.check_output(command, cwd=ROOT))
        repeat = json.loads(subprocess.check_output(command, cwd=ROOT))
        assert published["imported"] and repeat == {**published, "imported": False}
        assert published["version"] == 2
        bindings[topic] = published
    asyncio.run(check_storage(bindings))

    courses, posts, errors = {}, [], []
    with sync_playwright() as driver:
        browser = driver.chromium.launch_persistent_context(profile, headless=True)
        other_browser = driver.chromium.launch(headless=True)
        page, other = browser.pages[0], other_browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda req: posts.append(req.url) if req.method == "POST" else None,
        )
        for current in (page, other):
            current.goto(URL)
            current.wait_for_load_state("networkidle")
        assert api(page, "/api/auth/session")[1]["user"]["id"] == str(owner)
        assert api(other, "/api/auth/session")[1]["user"]["id"] != str(owner)
        for topic, (record, review) in archives.items():
            goal, _, expected = projection(topic, record, review)
            courses[topic] = check_course(
                page, other, topic, bindings[topic], goal, expected, posts
            )
        assert not errors, errors
        other_browser.close()
        browser.close()
    assert seal_snapshot() == sealed
    result = dict(
        entry=URL,
        same_guest=True,
        provider_calls=0,
        source_files_unchanged=len(sealed),
        rejections=rejected,
        idempotent_import=True,
        page_errors=0,
        courses=courses,
    )
    (args.artifacts / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
