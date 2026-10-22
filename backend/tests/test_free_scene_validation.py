"""Mechanical hard gates, inert Markdown and real private PG bindings; no model quality."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from test_free_course_migrations import legacy_digest, seed_legacy
from test_free_scene_generation import Gateway, authorize, inputs, prepare, response

from app.agents.free_scene_generation import generate_once
from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course import FreeCourseSceneVersion
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.models.free_scene_validation import FreeSceneValidation
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, WriteFence
from app.services.free_scene_generation import load_inputs, persist_outcome
from app.services.free_scene_validation import (
    RULE_VERSION,
    check_scene,
    clean_markdown,
    validate_candidate,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "raw",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "<svg/onload=alert(1)>",
        "[x](javascript:alert(1))",
        "![x](data:text/html,boom)",
        "[x][ref]\n[ref]: javascript:boom",
        "<javascript:alert(1)>",
        "&#x3c;script&#x3e;alert(1)",
        "\\[x](javascript:boom)",
        "\\\\![x](javascript:boom)",
        "[x](file:///private/data)",
        '<iframe srcdoc="boom"></iframe>',
    ],
)
def test_markdown_html_links_and_escaped_variants_are_inert_data(raw):
    cleaned = clean_markdown(raw)

    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []

        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)

    parser = Tags()
    parser.feed(cleaned)
    assert not parser.tags
    assert "<" not in cleaned and ">" not in cleaned
    for i, c in enumerate(cleaned):
        if c in "[]":
            j = i - 1
            while j >= 0 and cleaned[j] == "\\":
                j -= 1
            assert (i - 1 - j) % 2 == 1


def test_legal_content_is_accepted_without_review_and_original_is_preserved():
    raw = response()
    raw["blocks"][0]["markdown"] = "# 标题\n\n**重点**与C数组。"
    raw["blocks"][1]["source"] = "if (a[i] < b[i]) { a[i] = b[i]; }"
    raw["blocks"][2]["items"][0]["answer_key"] = "a[i] < b[i]"
    raw["blocks"][2]["items"][0]["solution"] = "[参考](javascript:bad) <b>解释</b>"
    prior = deepcopy(raw)
    checked = check_scene(raw, inputs())
    assert (
        checked["state"] == "accepted"
        and checked["reason_code"] is None
        and not checked["findings"]
    )
    assert raw == prior
    blocks = checked["cleaned"]["content"]["blocks"]
    assert blocks[0]["markdown"] == raw["blocks"][0]["markdown"]
    assert blocks[1]["source"] == raw["blocks"][1]["source"]
    assert blocks[2]["items"][0]["answer_key"] == "a[i] < b[i]"
    assert blocks[2]["items"][0]["solution"] == clean_markdown(
        raw["blocks"][2]["items"][0]["solution"]
    )
    assert check_scene(raw, inputs())["cleaned"] == checked["cleaned"]


@pytest.mark.parametrize(
    "mode,code",
    [
        ("duplicate_anchor", "ANCHOR_INVALID"),
        ("blank_anchor", "ANCHOR_INVALID"),
        ("foreign_anchor", "ACTION_REFERENCE_INVALID"),
        ("step_on_text", "ACTION_REFERENCE_INVALID"),
        ("step_outside", "ACTION_REFERENCE_INVALID"),
        ("duplicate_element", "VISUAL_REFERENCE_INVALID"),
        ("unknown_next", "VISUAL_REFERENCE_INVALID"),
        ("unknown_highlight", "VISUAL_REFERENCE_INVALID"),
        ("blank_element", "VISUAL_REFERENCE_INVALID"),
        ("script_block", "SCHEMA_INVALID"),
        ("tool_action", "SCHEMA_INVALID"),
        ("owner_override", "SCHEMA_INVALID"),
        ("blank_text", "SCHEMA_INVALID"),
        ("size_expansion", "CLEANED_SIZE_EXCEEDED"),
        ("wrong_language", "SCHEMA_INVALID"),
    ],
)
def test_bad_references_execution_fields_and_size_reject_without_cleaned_body(mode, code):
    raw = response()
    if mode == "duplicate_anchor":
        raw["blocks"][1]["anchor_id"] = "t"
    if mode == "blank_anchor":
        raw["blocks"][0]["anchor_id"] = " "
    if mode == "foreign_anchor":
        raw["actions"][0]["anchor_id"] = str(uuid4())
    if mode == "step_on_text":
        raw["actions"] = [dict(type="show_step", anchor_id="t", step_index=0)]
    if mode == "step_outside":
        raw["actions"] = [dict(type="show_step", anchor_id="v", step_index=1)]
    if mode == "duplicate_element":
        raw["blocks"][3]["steps"][0]["elements"] *= 2
    if mode == "unknown_next":
        raw["blocks"][3]["steps"][0]["elements"][0]["next_id"] = "foreign"
    if mode == "unknown_highlight":
        raw["blocks"][3]["steps"][0]["highlight_ids"] = ["foreign"]
    if mode == "blank_element":
        raw["blocks"][3]["steps"][0]["elements"][0]["id"] = " "
    if mode == "script_block":
        raw["blocks"].append(dict(kind="html", html="<script>bad</script>"))
    if mode == "tool_action":
        raw["actions"] = [dict(type="exec", source="bad")]
    if mode == "owner_override":
        raw["owner_id"] = str(uuid4())
    if mode == "blank_text":
        raw["blocks"][0]["markdown"] = " "
    if mode == "size_expansion":
        raw["blocks"][0]["markdown"] = "&" * 14000
    if mode == "wrong_language":
        raw["blocks"][1]["language"] = "javascript"
    checked = check_scene(raw, inputs())
    assert (
        checked["state"] == "rejected"
        and checked["reason_code"] == code
        and checked["cleaned"] is None
    )
    assert checked["findings"] == [dict(rule_id=f"{RULE_VERSION}:{code}", code=code)]


def test_valid_step_and_same_step_element_references():
    raw = response()
    raw["actions"] = [dict(type="show_step", anchor_id="v", step_index=0)]
    raw["blocks"][3]["steps"][0]["elements"].append(dict(id="y", label="2", next_id="x"))
    assert check_scene(raw, inputs())["state"] == "accepted"


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual isolated PG required; no skip"
    parsed = make_url(value)
    assert parsed.host == "127.0.0.1" and parsed.port == 15437
    assert (parsed.database or "").startswith("edumind_catalog_p15_t011_")
    return value


def migrate(target):
    return subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=ROOT / "backend",
        env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture(scope="module", autouse=True)
def migrate_database(record_testsuite_property):
    old = migrate("0037_free_scene_generation")
    assert old.returncode == 0, old.stderr
    owner = uuid4()

    async def storage(create=False, clean=False):
        engine = create_database_engine(database_url())
        try:
            if create:
                async with AsyncSession(engine) as db:
                    db.add(User(id=owner, is_guest=True))
                    await db.commit()
                    _, cid, fence, pid, plan, _ = await prepare(db, owner)
                    data = await load_inputs(
                        db,
                        owner,
                        cid,
                        fence.operation_id,
                        plan_id=pid,
                        scene_id=UUID(plan["scenes"][2]["scene_id"]),
                        expected_head=1,
                    )
                outcome = await generate_once(Gateway(), data, authorize_send=authorize)
                async with AsyncSession(engine) as db:
                    await persist_outcome(
                        db, owner, cid, fence, call_key="pre0038", inputs=data, outcome=outcome
                    )
                    await db.commit()
            async with engine.begin() as conn:
                if clean:
                    await conn.execute(text("DELETE FROM users WHERE id=:i"), {"i": owner})
                    return None
                tables = (
                    await conn.scalars(
                        text(
                            "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                            "AND tablename LIKE 'free_course%' "
                            "AND tablename<>'free_course_scene_validations' ORDER BY tablename"
                        )
                    )
                ).all()
                values = {
                    t: await conn.scalar(
                        text(
                            "SELECT coalesce(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text),"
                            f"'[]'::jsonb)::text FROM \"{t}\" r"
                        )
                    )
                    for t in tables
                }
                return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()
        finally:
            await engine.dispose()

    before = asyncio.run(storage(create=True))
    new = migrate("head")
    assert new.returncode == 0, new.stderr
    assert asyncio.run(storage()) == before
    record_testsuite_property("populated_0037_storage_sha256", before)
    asyncio.run(storage(clean=True))


def exercise(action):
    async def run():
        engine = create_database_engine(database_url())
        owners = [uuid4(), uuid4()]
        try:
            async with AsyncSession(engine) as db:
                db.add_all([User(id=u, is_guest=True) for u in owners])
                await db.commit()
            await action(engine, *owners)
        finally:
            async with engine.begin() as conn:
                for u in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": u})
            await engine.dispose()

    asyncio.run(run())


async def stored_candidate(db, owner, raw=None):
    repo, cid, fence, pid, plan, bindings = await prepare(db, owner)
    data = await load_inputs(
        db,
        owner,
        cid,
        fence.operation_id,
        plan_id=pid,
        scene_id=UUID(plan["scenes"][2]["scene_id"]),
        expected_head=1,
    )
    result = await generate_once(Gateway(raw), data, authorize_send=authorize)
    saved = await persist_outcome(
        db, owner, cid, fence, call_key="primary", inputs=data, outcome=result
    )
    await db.commit()
    return repo, cid, fence, UUID(saved["result_id"]), pid, bindings


def test_private_validation_atomic_replay_no_publication_or_legacy_review_changes(
    record_testsuite_property, monkeypatch
):
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *_a, **_k: pytest.fail("No Provider"),
    )

    async def action(engine, owner, other):
        await seed_legacy(engine)
        async with AsyncSession(engine) as db:
            raw = response()
            raw["blocks"][0]["markdown"] = "<script>boom</script> [x](javascript:bad)"
            repo, cid, fence, rid, pid, bindings = await stored_candidate(db, owner, raw)
            before = await legacy_digest(engine)
            first = await validate_candidate(db, owner, cid, fence, result_id=rid)
            again = await validate_candidate(db, owner, cid, fence, result_id=rid)
            assert first == again and first["state"] == "accepted"
            assert first["cleaned"]["content"]["blocks"][0]["markdown"] == clean_markdown(
                raw["blocks"][0]["markdown"]
            )
            first["cleaned"]["content"]["blocks"][0]["markdown"] = "mutated returned copy"
            await db.commit()
        async with AsyncSession(engine) as db:
            row = await db.get(FreeSceneGenerationResult, rid)
            assert row.response_json == raw
            saved = await db.get(FreeSceneValidation, UUID(again["validation_id"]))
            assert saved.cleaned_json == again["cleaned"] and saved.rule_version == RULE_VERSION
            assert saved.raw_digest != saved.cleaned_digest
            assert await db.scalar(select(func.count()).select_from(FreeSceneValidation)) == 1
            assert await db.scalar(select(func.count()).select_from(FreeCourseSceneVersion)) == 2
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 1
            assert (await db.get(FreeCourseOperation, fence.operation_id)).state == "running"
            for statement in [
                "UPDATE free_course_scene_validations SET state='rejected' WHERE id=:i",
                "DELETE FROM free_course_scene_validations WHERE id=:i",
            ]:
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(text(statement), {"i": saved.id})
        assert await legacy_digest(engine) == before
        record_testsuite_property("legacy_review_qualification_sha256", before)
        down = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0037_free_scene_generation"],
            cwd=ROOT / "backend",
            env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert down.returncode != 0 and "free course data prevents downgrade" in down.stderr

    exercise(action)


@pytest.mark.parametrize("mode", ["reference", "generation_failed"])
def test_rejected_fact_keeps_raw_and_exposes_no_cleaned_payload(mode):
    async def action(engine, owner, other):
        raw = response()
        if mode == "reference":
            raw["actions"][0]["anchor_id"] = "foreign"
        else:
            raw["blocks"] = []
        async with AsyncSession(engine) as db:
            repo, cid, fence, rid, pid, bindings = await stored_candidate(db, owner, raw)
            result = await validate_candidate(db, owner, cid, fence, result_id=rid)
            assert result["state"] == "rejected" and result["cleaned"] is None
            assert result["reason_code"] == (
                "ACTION_REFERENCE_INVALID" if mode == "reference" else "GENERATION_FAILED"
            )
            await db.commit()
            assert (await db.get(FreeSceneGenerationResult, rid)).response_json == raw
            assert (await repo.get_course(cid))["head_version"] == 1

    exercise(action)


@pytest.mark.parametrize(
    "mode",
    [
        "owner",
        "wrong_result",
        "wrong_operation",
        "cancel",
        "expired",
        "stale",
        "new_epoch",
        "rollback",
    ],
)
def test_wrong_identity_version_and_dead_fence_do_not_validate(mode):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, rid, pid, bindings = await stored_candidate(db, owner)
            if mode == "cancel":
                await db.execute(
                    text("UPDATE free_course_operations SET cancel_requested_at=now() WHERE id=:i"),
                    {"i": fence.operation_id},
                )
            if mode == "expired":
                await db.execute(
                    text(
                        "UPDATE free_course_operations SET "
                        "lease_expires_at=now()-interval '1 second' WHERE id=:i"
                    ),
                    {"i": fence.operation_id},
                )
            if mode == "stale":
                await repo.commit_manifest(
                    cid, fence, expected_head=1, key="next", plan_id=pid, bindings=bindings
                )
            if mode == "new_epoch":
                token = uuid4()
                await db.execute(
                    text(
                        "UPDATE free_course_operations SET lease_epoch=lease_epoch+1,"
                        "lease_token=:token WHERE id=:i"
                    ),
                    {"i": fence.operation_id, "token": token},
                )
                fence = WriteFence(fence.operation_id, fence.epoch + 1, token)
            if mode == "wrong_operation":
                fence = WriteFence(uuid4(), fence.epoch, fence.token)
            await db.commit()
            if mode == "rollback":
                await validate_candidate(db, owner, cid, fence, result_id=rid)
                await db.rollback()
            else:
                with pytest.raises(SnapshotError):
                    await validate_candidate(
                        db,
                        other if mode == "owner" else owner,
                        cid,
                        fence,
                        result_id=uuid4() if mode == "wrong_result" else rid,
                    )
                await db.rollback()
            assert await db.scalar(select(func.count()).select_from(FreeSceneValidation)) == 0
            assert (await repo.get_course(cid))["head_version"] == (2 if mode == "stale" else 1)

    exercise(action)
