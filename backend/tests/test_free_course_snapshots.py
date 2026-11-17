"""Real PG owner isolation, persistent receipts/CAS/fences; no generation or HTTP claims."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course import (
    FreeCourse,
    FreeCourseSceneVersion,
    FreeCourseVersion,
)
from app.models.free_course_writes import FreeCourseOperation, FreeCourseReceipt
from app.models.learning import StudentProfile, utc_now
from app.services.free_course_snapshots import (
    SnapshotError,
    SnapshotRepository,
    canonical,
    digest,
    parse_json,
)
from app.services.knowledge_graph_versions import graph_repository_for_version

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE = {
    "title": "synthetic storage fixture",
    "scenes": [
        {"scene_key": "first", "title": "first", "depends_on": []},
        {"scene_key": "second", "title": "second", "depends_on": ["first"]},
    ],
}
CONTENT = {"blocks": [{"type": "text", "markdown": "synthetic content, not a course approval"}]}


def url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual dedicated PG required; no environment skip"
    parsed = make_url(value)
    assert parsed.host == "127.0.0.1" and parsed.port == 15437
    assert (parsed.database or "").startswith("edumind_catalog_p15_t007_")
    return value


@pytest.fixture(scope="module", autouse=True)
def database_ready(record_testsuite_property):
    env = {**os.environ, "EDUMIND_DATABASE_URL": url()}
    old = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0034_free_course_snapshots"],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert old.returncode == 0, old.stderr

    async def previous_storage(*, create=False, clean=False):
        engine = create_database_engine(url())
        try:
            async with engine.begin() as conn:
                if create:
                    u, c, r, sc, p, v = [uuid4() for _ in range(6)]
                    await conn.execute(User.__table__.insert().values(id=u, is_guest=True))
                    await conn.execute(
                        FreeCourse.__table__.insert().values(
                            id=c, user_id=u, original_goal="synthetic pre0035", code_language="C"
                        )
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO free_course_requests "
                            "(id,user_id,course_id,version,kind,request_text,evidence_snapshot,"
                            "nonsecret_config_snapshot,schema_version,digest) "
                            "VALUES(:r,:u,:c,1,'original','synthetic pre0035','{}','{}','"
                            "fixture',:d)"
                        ),
                        dict(r=r, u=u, c=c, d="0" * 64),
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO free_course_scenes(id,user_id,course_id) VALUES(:s,:u,:c)"
                        ),
                        dict(s=sc, u=u, c=c),
                    )
                    plan = json.dumps({"scenes": [{"scene_id": str(sc), "depends_on": []}]})
                    await conn.execute(
                        text(
                            "INSERT INTO free_course_plans "
                            "(id,user_id,course_id,version,request_id,schema_version,dige"
                            "st,plan_json) "
                            "VALUES(:p,:u,:c,1,:r,'fixture',:d,CAST(:j AS jsonb))"
                        ),
                        dict(p=p, u=u, c=c, r=r, d="0" * 64, j=plan),
                    )
                    manifest = json.dumps(
                        {"scenes": [{"scene_id": str(sc), "scene_version_id": None}]}
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO free_course_versions "
                            "(id,user_id,course_id,version,plan_id,schema_version,digest,"
                            "manifest_json) "
                            "VALUES(:v,:u,:c,1,:p,'fixture',:d,CAST(:j AS jsonb))"
                        ),
                        dict(v=v, u=u, c=c, p=p, d="0" * 64, j=manifest),
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO free_course_node_links "
                            "(id,user_id,course_id,course_version_id,node_id,graph_versio"
                            "n,relation,"
                            "source,evidence_refs) VALUES(:i,:u,:c,:v,'stack','mvp-0.2.0','target',"
                            "'user_selected','[]')"
                        ),
                        dict(i=uuid4(), u=u, c=c, v=v),
                    )
                    await conn.execute(
                        text("UPDATE free_courses SET head_version_id=:v WHERE id=:c"),
                        dict(v=v, c=c),
                    )
                if clean:
                    await conn.execute(
                        text("DELETE FROM users WHERE id IN (SELECT user_id FROM free_courses)")
                    )
                    return None
                rows = []
                for table in [
                    "free_courses",
                    "free_course_requests",
                    "free_course_scenes",
                    "free_course_plans",
                    "free_course_versions",
                    "free_course_node_links",
                ]:
                    result = await conn.scalar(
                        text(
                            f"SELECT coalesce(jsonb_agg("
                            "to_jsonb(t)-'origin_operation_id'-'origin_lease_epoch'-'crea"
                            "tion_txid' "
                            f"ORDER BY id),'[]'::jsonb)::text FROM {table} t"
                        )
                    )
                    rows.append(result)
                return hashlib.sha256(json.dumps(rows).encode()).hexdigest()
        finally:
            await engine.dispose()

    before = asyncio.run(previous_storage(create=True))
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "EDUMIND_DATABASE_URL": url()},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert asyncio.run(previous_storage()) == before
    record_testsuite_property("populated_0034_storage_sha256", before)
    asyncio.run(previous_storage(clean=True))


def exercise(action):
    async def run():
        engine = create_database_engine(url())
        owners = [uuid4(), uuid4()]
        try:
            async with AsyncSession(engine) as db:
                db.add_all([User(id=u, is_guest=True) for u in owners])
                await db.commit()
            await action(engine, *owners)
        finally:
            async with engine.begin() as conn:
                for user in owners:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), {"u": user})
            await engine.dispose()

    asyncio.run(run())


async def setup(db, owner, *, profile=None):
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(" 原始目标 ", key="create", profile_id=profile)
    cid = UUID(created["course_id"])
    oid = UUID(created["operation_id"])
    fence = await repo.acquire_write_fence(cid, oid)
    plan = await repo.store_plan(cid, fence, expected_head=None, key="plan", candidate=CANDIDATE)
    pid = UUID(plan["plan_id"])
    info = await repo.get_plan(cid, pid)
    scenes = [UUID(s["scene_id"]) for s in info["scenes"]]
    initial = await repo.commit_manifest(
        cid, fence, expected_head=None, key="outline", plan_id=pid, bindings=[None, None]
    )
    return repo, cid, fence, pid, scenes, initial


@pytest.mark.parametrize(
    "raw",
    [
        '{"a":1,"a":2}',
        '{"x":{"a":1,"a":2}}',
        "[NaN]",
        "[Infinity]",
        "[-Infinity]",
        '{"a":"\\ud800"}',
        "{bad}",
    ],
)
def test_raw_json_rejects_duplicates_nonfinite_unicode(raw):
    with pytest.raises(SnapshotError):
        parse_json(raw)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        {"x": float("-inf")},
        {1: "x"},
        (1, 2),
        {"a": {"b": object()}},
        "\ud800",
    ],
)
def test_canonical_rejects_non_json(value):
    with pytest.raises(SnapshotError):
        canonical(value)


def test_canonical_is_stable_and_domain_separated():
    assert canonical({"b": 2, "a": "文"}) == '{"a":"文","b":2}'.encode()
    assert parse_json("[0.25,true,null]") == [0.25, True, None]
    assert digest("plan", body={}) != digest("scene", body={})


def test_version_history_sources_and_restart():
    async def action(engine, owner, other):
        async with AsyncSession(engine, expire_on_commit=False) as db:
            profile = StudentProfile(
                user_id=owner,
                version=1,
                merge_rule_version="synthetic",
                professional_background={"source": "self_report", "value": "student"},
            )
            db.add(profile)
            await db.flush()
            repo, cid, fence, pid, scenes, initial = await setup(db, owner, profile=profile.id)
            request = await repo.get_request(cid, 1)
            assert request["profile_version"] == 1 and request["profile_id"] == str(profile.id)
            assert request["evidence_snapshot"]["knowledge_base"] is None
            with pytest.raises(SnapshotError, match="SCENE_NOT_READY"):
                await repo.get_scene_snapshot(cid, 1, scenes[0])
            first = await repo.store_scene(
                cid,
                fence,
                expected_head=1,
                key="first",
                plan_id=pid,
                scene_id=scenes[0],
                content=CONTENT,
                actions=[],
                dependencies=[],
            )
            v2 = await repo.commit_manifest(
                cid,
                fence,
                expected_head=1,
                key="first-visible",
                plan_id=pid,
                bindings=[UUID(first["scene_version_id"]), None],
            )
            body = await repo.get_scene_snapshot(cid, 2, scenes[0])
            second = await repo.store_scene(
                cid,
                fence,
                expected_head=2,
                key="second",
                plan_id=pid,
                scene_id=scenes[1],
                content=CONTENT,
                actions=[],
                dependencies=[
                    {
                        "scene_id": str(scenes[0]),
                        "scene_version_id": first["scene_version_id"],
                        "content_digest": body["digest"],
                    }
                ],
            )
            v3 = await repo.commit_manifest(
                cid,
                fence,
                expected_head=2,
                key="full",
                plan_id=pid,
                bindings=[UUID(first["scene_version_id"]), UUID(second["scene_version_id"])],
            )
            assert v2["version"] == 2 and v3["version"] == 3
            body["content"]["blocks"].clear()
            assert (await repo.get_scene_snapshot(cid, 2, scenes[0]))["content"] == CONTENT
            await db.commit()
        async with AsyncSession(engine) as db:
            repo = SnapshotRepository(db, owner)
            assert (await repo.get_course(cid))["original_goal"] == " 原始目标 "
            assert (await repo.get_course(cid))["head_version"] == 3
            assert (await repo.get_version(cid, 1))["scenes"][0]["scene_version_id"] is None
            assert (await repo.get_scene_snapshot(cid, 3, scenes[1]))["content"] == CONTENT
            assert (await repo.get_plan(cid, pid))["candidate"] == CANDIDATE
            assert (await repo.get_request(cid, 1))["digest"] == request["digest"]
            with pytest.raises(SnapshotError, match="NOT_FOUND"):
                await repo.get_version(cid, 99)

    exercise(action)


@pytest.mark.parametrize(
    "method", ["course", "version", "scene", "request", "plan", "write", "cancel"]
)
def test_owner_isolation(method):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            _, cid, fence, pid, scenes, _ = await setup(db, owner)
            await db.commit()
        async with AsyncSession(engine) as db:
            repo = SnapshotRepository(db, other)
            with pytest.raises(SnapshotError, match="NOT_FOUND"):
                if method == "course":
                    await repo.get_course(cid)
                if method == "version":
                    await repo.get_version(cid, 1)
                if method == "scene":
                    await repo.get_scene_snapshot(cid, 1, scenes[0])
                if method == "request":
                    await repo.get_request(cid, 1)
                if method == "plan":
                    await repo.get_plan(cid, pid)
                if method == "write":
                    await repo.commit_manifest(
                        cid, fence, expected_head=1, key="hack", plan_id=pid, bindings=[None, None]
                    )
                if method == "cancel":
                    await repo.fence_cancellation(cid, fence.operation_id)
            await db.commit()

    exercise(action)


@pytest.mark.parametrize(
    "mutation", ["profile", "config_secret", "nested_config", "goal", "language", "key"]
)
def test_create_rejects_invalid_without_leaving_rows(mutation):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            profile = StudentProfile(user_id=other, version=1, merge_rule_version="synthetic")
            db.add(profile)
            await db.flush()
            repo = SnapshotRepository(db, owner)
            args = {"key": "k"}
            goal = "goal"
            if mutation == "profile":
                args["profile_id"] = profile.id
            if mutation == "config_secret":
                args["config"] = {"api_key": "synthetic-rejected"}
            if mutation == "nested_config":
                args["config"] = {"model": {"api_key": "synthetic-rejected"}}
            if mutation == "goal":
                goal = "   "
            if mutation == "language":
                args["teaching_language"] = "unsupported"
            if mutation == "key":
                args["key"] = "\n"
            with pytest.raises(SnapshotError):
                await repo.create_course(goal, **args)
            assert (
                await db.scalar(
                    select(func.count()).select_from(FreeCourse).where(FreeCourse.user_id == owner)
                )
                == 0
            )

    exercise(action)


def test_create_and_writes_idempotent_with_conflict_and_active_limit():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes, _ = await setup(db, owner)
            created = await repo.create_course(" 原始目标 ", key="create")
            assert created["course_id"] == str(cid)
            assert (
                await repo.store_plan(
                    cid, fence, expected_head=None, key="plan", candidate=CANDIDATE
                )
            )["plan_id"] == str(pid)
            assert (
                await repo.commit_manifest(
                    cid,
                    fence,
                    expected_head=None,
                    key="outline",
                    plan_id=pid,
                    bindings=[None, None],
                )
            )["version"] == 1
            with pytest.raises(SnapshotError, match="IDEMPOTENCY_CONFLICT"):
                await repo.create_course("different", key="create")
            with pytest.raises(SnapshotError, match="OPERATION_ACTIVE"):
                await repo.create_course("second", key="another")
            one = await repo.store_scene(
                cid,
                fence,
                expected_head=1,
                key="scene",
                plan_id=pid,
                scene_id=scenes[0],
                content=CONTENT,
                actions=[],
                dependencies=[],
            )
            assert (
                await repo.store_scene(
                    cid,
                    fence,
                    expected_head=1,
                    key="scene",
                    plan_id=pid,
                    scene_id=scenes[0],
                    content=CONTENT,
                    actions=[],
                    dependencies=[],
                )
                == one
            )
            with pytest.raises(SnapshotError, match="IDEMPOTENCY_CONFLICT"):
                await repo.store_scene(
                    cid,
                    fence,
                    expected_head=1,
                    key="scene",
                    plan_id=pid,
                    scene_id=scenes[0],
                    content={"blocks": []},
                    actions=[],
                    dependencies=[],
                )
            assert await db.scalar(select(func.count()).select_from(FreeCourseSceneVersion)) == 1
            await db.commit()

    exercise(action)


def test_transaction_rollback_does_not_consume_receipt_or_version():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes, _ = await setup(db, owner)
            await db.commit()
            first = await repo.commit_manifest(
                cid, fence, expected_head=1, key="attempt", plan_id=pid, bindings=[None, None]
            )
            assert first["version"] == 2
            await db.rollback()
        async with AsyncSession(engine) as db:
            repo = SnapshotRepository(db, owner)
            assert (await repo.get_course(cid))["head_version"] == 1
            result = await repo.commit_manifest(
                cid, fence, expected_head=1, key="attempt", plan_id=pid, bindings=[None, None]
            )
            assert result["version"] == 2
            await db.commit()

    exercise(action)


@pytest.mark.parametrize("cause", ["cancel", "expired_lease", "wrong_epoch", "wrong_token"])
def test_cancel_and_lease_fences_reject_late_mutations(cause):
    from app.services.free_course_snapshots import WriteFence

    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes, _ = await setup(db, owner)
            await db.commit()
            if cause == "cancel":
                await repo.fence_cancellation(cid, fence.operation_id)
            if cause == "expired_lease":
                await db.execute(
                    text(
                        "UPDATE free_course_operations SET "
                        "lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:o"
                    ),
                    {"o": fence.operation_id},
                )
            if cause == "wrong_epoch":
                fence = WriteFence(fence.operation_id, fence.epoch + 1, fence.token)
            if cause == "wrong_token":
                fence = WriteFence(fence.operation_id, fence.epoch, uuid4())
            await db.commit()
        async with AsyncSession(engine) as db:
            repo = SnapshotRepository(db, owner)
            with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
                await repo.commit_manifest(
                    cid, fence, expected_head=1, key="late", plan_id=pid, bindings=[None, None]
                )
            assert (await repo.get_course(cid))["head_version"] == 1
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(FreeCourseReceipt)
                    .where(FreeCourseReceipt.idempotency_key == "late")
                )
                == 0
            )

    exercise(action)


def test_reclaimed_lease_cannot_publish_private_old_epoch_candidate():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, old, pid, scenes, _ = await setup(db, owner)
            first = await repo.store_scene(
                cid,
                old,
                expected_head=1,
                key="private",
                plan_id=pid,
                scene_id=scenes[0],
                content=CONTENT,
                actions=[],
                dependencies=[],
            )
            await db.execute(
                text(
                    "UPDATE free_course_operations SET lease_expires_at=clock_timestamp() "
                    "-interval '1 second' WHERE id=:o"
                ),
                {"o": old.operation_id},
            )
            await db.commit()
        async with AsyncSession(engine) as db:
            repo = SnapshotRepository(db, owner)
            new = await repo.acquire_write_fence(cid, old.operation_id)
            assert new.epoch == old.epoch + 1
            with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
                await repo.commit_manifest(
                    cid,
                    new,
                    expected_head=1,
                    key="smuggle",
                    plan_id=pid,
                    bindings=[UUID(first["scene_version_id"]), None],
                )
            fresh = await repo.store_scene(
                cid,
                new,
                expected_head=1,
                key="fresh",
                plan_id=pid,
                scene_id=scenes[0],
                content=CONTENT,
                actions=[],
                dependencies=[],
            )
            await repo.commit_manifest(
                cid,
                new,
                expected_head=1,
                key="fresh-visible",
                plan_id=pid,
                bindings=[UUID(fresh["scene_version_id"]), None],
            )
            await db.commit()

    exercise(action)


def test_create_race_and_cas_race_are_persistent_single_winner():
    async def action(engine, owner, other):
        async def create():
            async with AsyncSession(engine) as db:
                value = await SnapshotRepository(db, owner).create_course("race", key="race")
                await db.commit()
                return value

        a, b = await asyncio.gather(create(), create())
        assert a == b
        cid, oid = UUID(a["course_id"]), UUID(a["operation_id"])
        async with AsyncSession(engine) as db:
            repo = SnapshotRepository(db, owner)
            fence = await repo.acquire_write_fence(cid, oid)
            pid = UUID(
                (
                    await repo.store_plan(
                        cid, fence, expected_head=None, key="p", candidate=CANDIDATE
                    )
                )["plan_id"]
            )
            await repo.commit_manifest(
                cid, fence, expected_head=None, key="m", plan_id=pid, bindings=[None, None]
            )
            await db.commit()

        async def append(key):
            async with AsyncSession(engine) as db:
                try:
                    result = await SnapshotRepository(db, owner).commit_manifest(
                        cid, fence, expected_head=1, key=key, plan_id=pid, bindings=[None, None]
                    )
                    await db.commit()
                    return result["version"]
                except SnapshotError as error:
                    await db.rollback()
                    return error.code

        outcomes = await asyncio.gather(append("a"), append("b"))
        assert outcomes.count(2) == 1 and outcomes.count("STALE_COURSE_VERSION") == 1
        async with AsyncSession(engine) as db:
            assert await db.scalar(select(func.count()).select_from(FreeCourse)) == 1
            assert await db.scalar(select(func.count()).select_from(FreeCourseVersion)) == 2

    exercise(action)


def test_all_approved_graph_nodes_and_corrupt_identifiers():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes, _ = await setup(db, owner)
            current = 1
            count = 0
            for version in ["mvp-0.2.0", "phase-1.1.0"]:
                nodes = graph_repository_for_version(version).all_nodes()
                links = [
                    {
                        "node_id": n.id,
                        "graph_version": version,
                        "relation": "target",
                        "source": "planner_suggestion",
                        "evidence_refs": [],
                    }
                    for n in nodes
                ]
                result = await repo.commit_manifest(
                    cid,
                    fence,
                    expected_head=current,
                    key=version,
                    plan_id=pid,
                    bindings=[None, None],
                    node_links=links,
                )
                current = result["version"]
                count += len(nodes)
            assert count == 40
            assert (await repo.get_version(cid, 1))["digest"] != (await repo.get_version(cid, 2))[
                "digest"
            ]
            with pytest.raises(SnapshotError):
                await repo.commit_manifest(
                    cid,
                    fence,
                    expected_head=current,
                    key="bad-node",
                    plan_id=pid,
                    bindings=[None, None],
                    node_links=[
                        {
                            "node_id": "circular- queue",
                            "graph_version": "mvp-0.2.0",
                            "relation": "target",
                            "source": "planner_suggestion",
                            "evidence_refs": [],
                        }
                    ],
                )
            assert (await repo.get_course(cid))["head_version"] == current
            await db.commit()

    exercise(action)


def test_cancelled_operation_candidates_cannot_be_rebound_to_new_operation():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, old, pid, scenes, _ = await setup(db, owner)
            stored = await repo.store_scene(
                cid,
                old,
                expected_head=1,
                key="old",
                plan_id=pid,
                scene_id=scenes[0],
                content=CONTENT,
                actions=[],
                dependencies=[],
            )
            await repo.fence_cancellation(cid, old.operation_id)
            op = await db.get(FreeCourseOperation, old.operation_id)
            op.state = "cancelled"
            # Synthetic T015 successor fixture; this task does not implement resume scheduling.
            successor = FreeCourseOperation(
                user_id=owner,
                course_id=cid,
                request_id=op.request_id,
                kind="resume",
                base_head_version=1,
                config_snapshot={},
                policy_snapshot={},
            )
            db.add(successor)
            await db.flush()
            successor_id = successor.id
            await db.commit()
            fresh = await repo.acquire_write_fence(cid, successor_id)
            with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
                await repo.commit_manifest(
                    cid,
                    fresh,
                    expected_head=1,
                    key="old-after-cancel",
                    plan_id=pid,
                    bindings=[UUID(stored["scene_version_id"]), None],
                )

    exercise(action)


def test_expired_deadline_refuses_fence():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes, _ = await setup(db, owner)
            op = await db.get(FreeCourseOperation, fence.operation_id)
            op.state = "succeeded"
            expired = FreeCourseOperation(
                user_id=owner,
                course_id=cid,
                request_id=op.request_id,
                kind="resume",
                config_snapshot={},
                policy_snapshot={},
                deadline_at=utc_now() - timedelta(seconds=1),
            )
            db.add(expired)
            await db.flush()
            with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
                await repo.acquire_write_fence(cid, expired.id)

    exercise(action)


def test_new_plan_preserves_retained_logical_scene_identities():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid, scenes, _ = await setup(db, owner)
            revision = await repo.store_plan(
                cid, fence, expected_head=1, key="revision-plan", candidate=CANDIDATE
            )
            new = await repo.get_plan(cid, UUID(revision["plan_id"]))
            assert UUID(new["id"]) != pid
            assert [UUID(s["scene_id"]) for s in new["scenes"]] == scenes
            assert (await repo.get_course(cid))["head_version"] == 1
            await db.commit()

    exercise(action)


def test_failed_receipt_rolls_back_new_manifest_links_and_cas():
    class FailedReceipt(SnapshotRepository):
        async def _record(self, *args, **kwargs):
            raise SnapshotError("SYNTHETIC_STORAGE_FAILURE")

    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            _, cid, fence, pid, _, _ = await setup(db, owner)
            await db.commit()
            repo = FailedReceipt(db, owner)
            with pytest.raises(SnapshotError, match="SYNTHETIC_STORAGE_FAILURE"):
                await repo.commit_manifest(
                    cid,
                    fence,
                    expected_head=1,
                    key="fail-receipt",
                    plan_id=pid,
                    bindings=[None, None],
                    node_links=[
                        {
                            "node_id": "stack",
                            "graph_version": "mvp-0.2.0",
                            "relation": "target",
                            "source": "planner_suggestion",
                            "evidence_refs": [],
                        }
                    ],
                )
            assert (await repo.get_course(cid))["head_version"] == 1
            assert await db.scalar(select(func.count()).select_from(FreeCourseVersion)) == 1
            assert await db.scalar(text("SELECT count(*) FROM free_course_node_links")) == 0
            await db.commit()

    exercise(action)


def test_fence_expiring_between_initial_check_and_cas_is_rejected():
    class ExpireBeforeCommit(SnapshotRepository):
        async def _fence(self, course_id, fence):
            op = await super()._fence(course_id, fence)
            op.lease_expires_at = await self._now() - timedelta(seconds=1)
            await self.db.flush()
            return op

    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            _, cid, fence, pid, _, _ = await setup(db, owner)
            await db.commit()
            repo = ExpireBeforeCommit(db, owner)
            with pytest.raises(SnapshotError, match="OPERATION_FENCED"):
                await repo.commit_manifest(
                    cid,
                    fence,
                    expected_head=1,
                    key="expires-at-cas",
                    plan_id=pid,
                    bindings=[None, None],
                )
            assert (await repo.get_course(cid))["head_version"] == 1
            assert await db.scalar(select(func.count()).select_from(FreeCourseVersion)) == 1

    exercise(action)


def test_read_refreshes_current_head_after_other_session_commits():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as initial:
            _, cid, fence, pid, _, _ = await setup(initial, owner)
            await initial.commit()
        async with AsyncSession(engine) as reader:
            repo = SnapshotRepository(reader, owner)
            assert (await repo.get_course(cid))["head_version"] == 1
            async with AsyncSession(engine) as writer:
                await SnapshotRepository(writer, owner).commit_manifest(
                    cid, fence, expected_head=1, key="new-head", plan_id=pid, bindings=[None, None]
                )
                await writer.commit()
            assert (await repo.get_course(cid))["head_version"] == 2

    exercise(action)
