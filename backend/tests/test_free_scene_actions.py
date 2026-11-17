"""Non-executable presentation/reducer and real owned PG binding; no frontend/media claim."""

import asyncio
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from test_free_scene_generation import inputs, response
from test_free_scene_validation import stored_candidate

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course import FreeCourseSceneVersion
from app.models.free_course_writes import FreeCourseOperation
from app.models.free_scene_actions import FreeScenePresentation
from app.models.free_scene_generation import FreeSceneGenerationResult
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository, WriteFence, digest
from app.services.free_scene_actions import (
    compile_presentation,
    initial_state,
    prepare_presentation,
    transition,
)
from app.services.free_scene_validation import check_scene, validate_candidate

ROOT = Path(__file__).resolve().parents[2]


def view(kind="array", fallback=None):
    raw = response()
    raw["blocks"][3]["visualization_type"] = kind
    raw["blocks"][3]["steps"] *= 3
    raw["actions"] = [
        dict(type="highlight_block", anchor_id="t", step_index=None),
        dict(type="highlight_block", anchor_id="c", step_index=None),
        dict(type="show_step", anchor_id="v", step_index=2),
        dict(type="pause", anchor_id="v", step_index=None),
    ]
    checked = check_scene(raw, inputs())
    assert checked["state"] == "accepted"
    return compile_presentation(
        checked["cleaned"],
        dict(scene_id="synthetic exact scene", validation_id="synthetic"),
        fallback_reason=fallback,
    )


@pytest.mark.parametrize("kind", ["array", "linked_list", "stack", "queue"])
def test_components_and_timeline_only_select_real_same_snapshot_data(kind):
    p = view(kind)
    state = initial_state(p)
    original = deepcopy(state)
    state = transition(p, state, "play")
    assert state["paused"] is False
    state = transition(p, state, "next_action")
    assert state["active_anchor"] == "t" and state["code_anchor"] is None
    state = transition(p, state, "next_action")
    assert state["code_anchor"] == "c"
    assert next(b for b in p["blocks"] if b["anchor_id"] == "c")["source"] == "int value = 1;"
    state = transition(p, state, "next_action")
    assert state["step_indices"]["v"] == 2
    state = transition(p, state, "next_action")
    assert state["paused"] is True
    assert transition(p, state, "next_action")["cursor"] == 3
    assert original == initial_state(p)
    assert next(b for b in p["blocks"] if b["anchor_id"] == "v")["visualization_type"] == kind
    assert p["code_execution"] is p["media_requested"] is p["animation_executed"] is False
    assert "未执行" in p["description"]
    assert "answer_key" not in json.dumps(p) and "solution" not in json.dumps(p)


def test_manual_steps_clamp_and_do_not_rewrite_source_or_simulate_code_execution():
    p = view()
    before = deepcopy(p)
    s = initial_state(p)
    for _ in range(8):
        s = transition(p, s, "next_step", anchor_id="v")
    assert s["step_indices"] == {"v": 2}
    for _ in range(8):
        s = transition(p, s, "previous_step", anchor_id="v")
    assert s["step_indices"] == {"v": 0} and p == before
    assert transition(p, s, "pause")["paused"] is True


@pytest.mark.parametrize(
    "reason", ["MEDIA_UNAVAILABLE", "RENDERER_UNAVAILABLE", "ACTION_UNAVAILABLE"]
)
def test_static_fallback_preserves_all_body_and_diagnostics_without_fake_media_success(reason):
    p = view(fallback=reason)
    normal = view()
    assert p["blocks"] == normal["blocks"] and p["timeline"] == [] and p["mode"] == "static"
    assert p["diagnostics"] == [dict(code=reason)]
    state = initial_state(p)
    assert transition(p, state, "play")["paused"] is True
    assert transition(p, state, "pause")["diagnostics"] == [dict(code=reason)]
    assert p["animation_executed"] is False


@pytest.mark.parametrize(
    "mode",
    [
        "unknown_command",
        "unknown_anchor",
        "bad_cursor",
        "bad_step",
        "bool_step",
        "missing_state",
        "extra_state",
        "forged_anchor",
        "forged_code_anchor",
        "bad_mode",
        "bad_diagnostic",
        "changed_action_type",
        "changed_action_anchor",
        "changed_step_index",
    ],
)
def test_damaged_runtime_action_or_state_degrades_to_static_known_body(mode):
    p = view()
    s = initial_state(p)
    cmd = "next_action"
    anchor = None
    if mode == "unknown_command":
        cmd = "eval arbitrary script"
    if mode == "unknown_anchor":
        cmd = "next_step"
        anchor = "external-version"
    if mode == "bad_cursor":
        s["cursor"] = 9999
    if mode == "bad_step":
        s["step_indices"]["v"] = 99
    if mode == "bool_step":
        s["step_indices"]["v"] = True
    if mode == "missing_state":
        s.pop("paused")
    if mode == "extra_state":
        s["exec"] = "bad"
    if mode == "forged_anchor":
        s["active_anchor"] = "external"
    if mode == "forged_code_anchor":
        s["code_anchor"] = "t"
    if mode == "bad_mode":
        s["mode"] = []
    if mode == "bad_diagnostic":
        s["diagnostics"] = [dict(code=[])]
    if mode.startswith("changed_"):
        if mode == "changed_action_type":
            p["timeline"][0]["type"] = "eval"
        if mode == "changed_action_anchor":
            p["timeline"][0]["anchor_id"] = "external"
        if mode == "changed_step_index":
            p["timeline"][0] = dict(type="show_step", anchor_id="v", step_index=99)
        # Test malformed local presentation transport only; digests do not grant source authority.
        payload = {k: v for k, v in p.items() if k != "digest"}
        p["digest"] = digest("scene-presentation", payload=payload)
        s = initial_state(p)
    before = deepcopy(p["blocks"])
    result = transition(p, s, cmd, anchor_id=anchor)
    assert result["mode"] == "static" and result["paused"] is True
    assert result["diagnostics"] == [dict(code="ACTION_UNAVAILABLE")]
    assert p["blocks"] == before


def test_stale_or_accidentally_mutated_presentation_is_not_a_static_bypass():
    p = view()
    s = initial_state(p)
    other = view(fallback="MEDIA_UNAVAILABLE")
    with pytest.raises(SnapshotError, match="STALE_PRESENTATION"):
        transition(other, s, "play")
    p["blocks"][0]["markdown"] = "changed source"
    with pytest.raises(SnapshotError, match="PRESENTATION_CORRUPT"):
        transition(p, s, "play")


def test_reduced_motion_or_local_render_failure_can_select_static_without_network():
    p = view()
    state = transition(p, initial_state(p), "RENDERER_UNAVAILABLE")
    assert state["mode"] == "static" and state["step_indices"] == {"v": 0}
    assert state["diagnostics"] == [dict(code="RENDERER_UNAVAILABLE")]
    assert transition(p, state, "play")["mode"] == "static"


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual isolated PG required, no skip"
    parsed = make_url(value)
    assert parsed.host == "127.0.0.1" and parsed.port == 15437
    assert (parsed.database or "").startswith("edumind_catalog_p15_t012_")
    return value


@pytest.fixture(scope="module", autouse=True)
def migrate_database():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


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


async def setup(db, owner, raw=None):
    repo, cid, fence, rid, pid, bindings = await stored_candidate(db, owner, raw)
    validated = await validate_candidate(db, owner, cid, fence, result_id=rid)
    await db.commit()
    return repo, cid, fence, UUID(validated["validation_id"]), rid, pid, bindings


def test_presentation_and_static_diagnostics_persist_without_raw_answers_or_publication(
    monkeypatch,
):
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda *_a, **_k: pytest.fail("No real Provider"),
    )

    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, vid, rid, pid, bindings = await setup(db, owner)
            source = (await db.get(FreeSceneGenerationResult, rid)).response_json
            first = await prepare_presentation(db, owner, cid, fence, validation_id=vid)
            again = await prepare_presentation(db, owner, cid, fence, validation_id=vid)
            assert first == again
            fallback = await prepare_presentation(
                db, owner, cid, fence, validation_id=vid, fallback_reason="MEDIA_UNAVAILABLE"
            )
            assert fallback["presentation"]["blocks"] == first["presentation"]["blocks"]
            assert fallback["presentation"]["diagnostics"] == [dict(code="MEDIA_UNAVAILABLE")]
            assert first["presentation"]["binding"]["plan_id"] == str(pid)
            assert first["presentation"]["binding"]["expected_head"] == 1
            assert "answer_key" not in json.dumps(first) and "solution" not in json.dumps(first)
            first["presentation"]["blocks"][0]["markdown"] = "changed return"
            await db.commit()
        async with AsyncSession(engine) as db:
            saved = await db.get(FreeScenePresentation, UUID(again["presentation_id"]))
            assert saved.presentation_json == again["presentation"]
            assert (await db.get(FreeSceneGenerationResult, rid)).response_json == source
            assert await db.scalar(select(func.count()).select_from(FreeScenePresentation)) == 2
            assert await db.scalar(select(func.count()).select_from(FreeCourseSceneVersion)) == 2
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 1
            assert (await db.get(FreeCourseOperation, fence.operation_id)).state == "running"
            for sql in [
                "UPDATE free_course_scene_presentations "
                "SET fallback_key='ACTION_UNAVAILABLE' WHERE id=:i",
                "DELETE FROM free_course_scene_presentations WHERE id=:i",
            ]:
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(text(sql), {"i": saved.id})
        down = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0038_free_scene_validation"],
            cwd=ROOT / "backend",
            env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert down.returncode != 0 and "free course data prevents downgrade" in down.stderr

    exercise(action)


def test_bad_candidate_cannot_bypass_hard_gate_by_claiming_static_fallback():
    async def action(engine, owner, other):
        raw = response()
        raw["actions"][0]["anchor_id"] = "external"
        async with AsyncSession(engine) as db:
            repo, cid, fence, vid, rid, pid, bindings = await setup(db, owner, raw)
            with pytest.raises(SnapshotError, match="HARD_GATE_REJECTED"):
                await prepare_presentation(
                    db, owner, cid, fence, validation_id=vid, fallback_reason="ACTION_UNAVAILABLE"
                )
            assert await db.scalar(select(func.count()).select_from(FreeScenePresentation)) == 0

    exercise(action)


@pytest.mark.parametrize(
    "mode",
    [
        "owner",
        "wrong_validation",
        "wrong_operation",
        "cancel",
        "expired",
        "stale",
        "new_epoch",
        "rollback",
    ],
)
def test_source_identity_and_live_bindings_required_even_for_static(mode):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, vid, rid, pid, bindings = await setup(db, owner)
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
                await prepare_presentation(db, owner, cid, fence, validation_id=vid)
                await db.rollback()
            else:
                with pytest.raises(SnapshotError):
                    await prepare_presentation(
                        db,
                        other if mode == "owner" else owner,
                        cid,
                        fence,
                        validation_id=uuid4() if mode == "wrong_validation" else vid,
                        fallback_reason="MEDIA_UNAVAILABLE",
                    )
                await db.rollback()
            assert await db.scalar(select(func.count()).select_from(FreeScenePresentation)) == 0
            assert (await repo.get_course(cid))["head_version"] == (2 if mode == "stale" else 1)

    exercise(action)
