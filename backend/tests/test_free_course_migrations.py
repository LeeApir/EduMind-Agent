"""Real isolated PG migration and adversarial constraints; synthetic data only."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.catalog import CatalogRelease
from app.models.free_course import (
    FreeCourse,
    FreeCourseNodeLink,
    FreeCoursePlan,
    FreeCourseRequest,
    FreeCourseScene,
    FreeCourseSceneVersion,
    FreeCourseVersion,
)
from app.models.learning import (
    GeneratedResource,
    LearningOperation,
    LearningScene,
    LearningUnit,
    StudentProfile,
    utc_now,
)
from app.models.learning_plan import LearningPlanVersion
from app.models.learning_publication import LearningPublication
from app.models.learning_review import LearningReviewRecord
from app.models.learning_review_case import LearningReviewCase, LearningReviewDecision
from app.models.learning_state import LearningEvidence, NodeMasteryCurrent, NodeMasteryRevision

ROOT = Path(__file__).resolve().parents[2]
OLD = "0033_learning_shared_budget"
HEAD = "0048_free_course_tutor_events"
DIGEST = "0" * 64


def database_url():
    value = os.environ.get("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual isolated PostgreSQL required; missing configuration is failure, not skip"
    parsed = make_url(value)
    assert parsed.host == "127.0.0.1" and parsed.port == 15437
    assert (parsed.database or "").startswith("edumind_catalog_p15_t006_")
    return value


def migrate(target, *, downgrade=False):
    env = {k: v for k, v in os.environ.items() if not k.startswith("EDUMIND_PROVIDER")}
    env["EDUMIND_DATABASE_URL"] = database_url()
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade" if downgrade else "upgrade", target],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result


async def legacy_digest(engine):
    async with engine.connect() as conn:
        tables = (
            (
                await conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                        "AND tablename<>'alembic_version' AND tablename NOT LIKE 'free_course%' "
                        "ORDER BY tablename"
                    )
                )
            )
            .scalars()
            .all()
        )
        payload = {}
        source_columns = await conn.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
                "WHERE table_name='learning_evidence' AND column_name='source_protocol')"
            )
        )
        for table in tables:
            projection = "to_jsonb(t)"
            if table == "learning_evidence" and source_columns:
                assert (
                    await conn.scalar(
                        text(
                            "SELECT count(*) FROM learning_evidence WHERE "
                            "source_protocol IS NULL AND free_course_attempt_id IS NOT NULL"
                        )
                    )
                    == 0
                )
                projection = "(to_jsonb(t)-ARRAY['source_protocol','free_course_attempt_id'])"
            payload[table] = await conn.scalar(
                text(
                    f"SELECT coalesce(jsonb_agg({projection} ORDER BY {projection}::text),"
                    f"'[]'::jsonb)::text FROM \"{table}\" t"
                )
            )
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def seed_legacy(engine):
    """Synthetic approved/rejected history proves byte preservation, no real attestation."""
    async with AsyncSession(engine) as db:
        user = User(is_guest=True)
        db.add(user)
        await db.flush()
        release = CatalogRelease(
            package_id="synthetic-migration-fixture",
            version="test-only",
            manifest_digest=DIGEST,
            graph_version="mvp-0.2.0",
            payload={"test_only": True},
            approval={"test_only": True, "not_real_human_signoff": True},
        )
        db.add(release)
        await db.flush()
        units = [
            LearningUnit(user_id=user.id, title=title, knowledge_point_id="stack", status=status)
            for title, status in [
                ("curated", "published"),
                ("legacy", "published"),
                ("planned", "published"),
                ("pending", "draft"),
                ("failed", "failed"),
            ]
        ]
        units[0].catalog_release_id = release.id
        db.add_all(units)
        await db.flush()
        scenes = [
            LearningScene(
                learning_unit_id=u.id, scene_key="intro", scene_order=1, scene_type="explanation"
            )
            for u in units
        ]
        db.add_all(scenes)
        await db.flush()
        resources = [
            GeneratedResource(
                user_id=user.id,
                learning_unit_id=u.id,
                scene_id=sc.id,
                resource_type="explanation",
                content={"test_only": u.title},
                review_status="passed" if i < 3 else "pending",
                published_at=utc_now() if i < 3 else None,
            )
            for i, (u, sc) in enumerate(zip(units, scenes, strict=True))
        ]
        resources[0].origin_type = "curated"
        resources[0].catalog_release_id = release.id
        resources[0].catalog_content_digest = DIGEST
        db.add_all(resources)
        await db.flush()
        op = LearningOperation(
            user_id=user.id,
            learning_unit_id=units[2].id,
            idempotency_key="synthetic",
            request_digest=DIGEST,
            goal="stack",
            preferred_language="C",
        )
        db.add(op)
        await db.flush()
        plan = LearningPlanVersion(
            user_id=user.id,
            learning_unit_id=units[2].id,
            origin_operation_id=op.id,
            version=1,
            schema_version="synthetic",
            input_snapshot={},
            references_snapshot={},
            policy_snapshot={},
            plan_json={"test_only": True},
            plan_digest=DIGEST,
            input_digest=DIGEST,
            references_digest=DIGEST,
            policy_version="synthetic",
            policy_digest=DIGEST,
        )
        db.add(plan)
        await db.flush()
        review = LearningReviewRecord(
            id=uuid4(),
            user_id=user.id,
            learning_unit_id=units[2].id,
            plan_id=plan.id,
            operation_id=op.id,
            target_digest=DIGEST,
            record={"test_only": True, "decision": "reject"},
        )
        case = LearningReviewCase(
            id=uuid4(),
            user_id=user.id,
            learning_unit_id=units[2].id,
            plan_id=plan.id,
            operation_id=op.id,
            case_digest=DIGEST,
            state="approved",
            payload={"test_only": True},
        )
        db.add_all([review, case])
        await db.flush()
        decision = LearningReviewDecision(
            id=uuid4(),
            user_id=user.id,
            learning_unit_id=units[2].id,
            case_id=case.id,
            reviewer_id="synthetic-fixture-not-human",
            identity_source="test-only",
            idempotency_key="fixture",
            case_digest=DIGEST,
            verdict="approve",
            reason="synthetic preservation fixture, not approval of real content",
        )
        db.add(decision)
        await db.flush()
        publication = LearningPublication(
            user_id=user.id,
            learning_unit_id=units[2].id,
            plan_id=plan.id,
            operation_id=op.id,
            version=1,
            unit_digest=DIGEST,
            material={"test_only": True},
            review_ids=[str(review.id)],
            approval_source="human_assisted",
            decision_id=decision.id,
        )
        db.add(publication)
        await db.flush()
        units[2].current_publication_id = publication.id
        evidence = LearningEvidence(
            user_id=user.id,
            idempotency_key="synthetic-score",
            request_digest=DIGEST,
            evidence_type="quiz_attempt",
            knowledge_node_id="stack",
            learning_unit_id=units[0].id,
            schema_version=1,
            rule_version="mastery-v1",
            payload={"test_only": True, "score": 1},
        )
        from sqlalchemy import MetaData, Table

        evidence.id = uuid4()
        evidence.created_at = utc_now()
        table = await db.run_sync(
            lambda sync: Table("learning_evidence", MetaData(), autoload_with=sync.connection())
        )
        values = {c.name: getattr(evidence, c.name) for c in table.columns}
        await db.execute(table.insert().values(**values))
        await db.flush()
        revision = NodeMasteryRevision(
            user_id=user.id,
            knowledge_node_id="stack",
            revision=1,
            previous_score=0,
            score=0.2,
            status="learning",
            rule_version="mastery-v1",
            evidence_id=evidence.id,
            evidence_summary=[],
        )
        db.add(revision)
        await db.flush()
        db.add(
            NodeMasteryCurrent(
                user_id=user.id,
                knowledge_node_id="stack",
                revision_id=revision.id,
                revision=1,
                rule_version="mastery-v1",
                score=0.2,
                status="learning",
            )
        )
        await db.commit()


@pytest.fixture(scope="module", autouse=True)
def migrated_database(record_testsuite_property):
    async def prepare():
        engine = create_database_engine(database_url())
        try:
            async with engine.connect() as conn:
                assert (
                    await conn.scalar(text("SELECT to_regclass('public.alembic_version')")) is None
                )
        finally:
            await engine.dispose()

    asyncio.run(prepare())
    assert migrate("head").returncode == 0, "Empty database upgrade failed"
    result = migrate(OLD, downgrade=True)
    assert result.returncode == 0, result.stderr
    engine = create_database_engine(database_url())

    async def populate():
        try:
            await seed_legacy(engine)
            return await legacy_digest(engine)
        finally:
            await engine.dispose()

    before = asyncio.run(populate())
    result = migrate("head")
    assert result.returncode == 0, result.stderr

    async def verify():
        eng = create_database_engine(database_url())
        try:
            assert before == await legacy_digest(eng)
        finally:
            await eng.dispose()

    asyncio.run(verify())
    record_testsuite_property("legacy_sha256", before)
    record_testsuite_property("database", make_url(database_url()).database)
    record_testsuite_property(
        "migration", "empty upgrade/downgrade; synthetic legacy populated upgrade"
    )
    print("Empty upgrade/downgrade and populated upgrade: legacy SHA256=" + before)
    yield before
    asyncio.run(verify())


async def seed(db):
    owner, other = User(is_guest=True), User(is_guest=True)
    db.add_all([owner, other])
    await db.flush()
    profile = StudentProfile(user_id=owner.id, version=1, merge_rule_version="synthetic")
    db.add(profile)
    await db.flush()
    course = FreeCourse(user_id=owner.id, original_goal=" 原始目标 ", code_language="C")
    other_course = FreeCourse(user_id=owner.id, original_goal="other")
    db.add_all([course, other_course])
    await db.flush()
    req = FreeCourseRequest(
        user_id=owner.id,
        course_id=course.id,
        version=1,
        kind="original",
        request_text=course.original_goal,
        profile_id=profile.id,
        profile_version=1,
        evidence_snapshot={},
        nonsecret_config_snapshot={},
        schema_version="free-course-v1",
        digest=DIGEST,
    )
    scenes = [FreeCourseScene(user_id=owner.id, course_id=course.id) for _ in range(3)]
    db.add_all([req, *scenes])
    await db.flush()
    entries = [
        {
            "scene_id": str(sc.id),
            "title": str(i),
            "depends_on": [] if i == 0 else [str(scenes[0].id)],
        }
        for i, sc in enumerate(scenes[:2])
    ]
    plan = FreeCoursePlan(
        user_id=owner.id,
        course_id=course.id,
        version=1,
        request_id=req.id,
        schema_version="free-course-v1",
        digest=DIGEST,
        plan_json={"scenes": entries},
    )
    db.add(plan)
    await db.flush()
    first = FreeCourseSceneVersion(
        user_id=owner.id,
        course_id=course.id,
        scene_id=scenes[0].id,
        version=1,
        plan_id=plan.id,
        schema_version="free-course-v1",
        content_json={"blocks": [{"type": "text", "markdown": "example"}]},
        actions_json=[],
        dependency_bindings=[],
        content_digest=DIGEST,
    )
    db.add(first)
    await db.flush()
    second = FreeCourseSceneVersion(
        user_id=owner.id,
        course_id=course.id,
        scene_id=scenes[1].id,
        version=1,
        plan_id=plan.id,
        schema_version="free-course-v1",
        content_json={"blocks": []},
        actions_json=[],
        content_digest=DIGEST,
        dependency_bindings=[
            {
                "scene_id": str(scenes[0].id),
                "scene_version_id": str(first.id),
                "content_digest": DIGEST,
            }
        ],
    )
    db.add(second)
    await db.flush()
    manifest = {
        "scenes": [
            {"scene_id": str(sc.id), "scene_version_id": str(v.id)}
            for sc, v in zip(scenes, [first, second])
        ]
    }
    version = FreeCourseVersion(
        user_id=owner.id,
        course_id=course.id,
        version=1,
        plan_id=plan.id,
        schema_version="free-course-v1",
        digest=DIGEST,
        manifest_json=manifest,
    )
    db.add(version)
    await db.flush()
    course.head_version_id = version.id
    await db.flush()
    return dict(
        owner=owner,
        other=other,
        profile=profile,
        course=course,
        other_course=other_course,
        req=req,
        scenes=scenes,
        plan=plan,
        first=first,
        second=second,
        version=version,
    )


def run_transaction(action):
    async def exercise():
        engine = create_database_engine(database_url())
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                state = await seed(db)
                await action(db, state)
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())


def test_partial_manifest_and_private_draft_defaults():
    async def action(db, s):
        m = deepcopy(s["version"].manifest_json)
        m["scenes"][1]["scene_version_id"] = None
        v = FreeCourseVersion(
            user_id=s["owner"].id,
            course_id=s["course"].id,
            version=2,
            plan_id=s["plan"].id,
            schema_version="free-course-v1",
            digest=DIGEST,
            manifest_json=m,
        )
        db.add(v)
        await db.flush()
        assert s["course"].course_kind == "ai_draft"
        assert s["course"].endorsement == "unendorsed"
        s["course"].head_version_id = v.id
        await db.flush()
        await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert (await db.get(FreeCourseVersion, s["version"].id)).manifest_json == s[
            "version"
        ].manifest_json

    run_transaction(action)


@pytest.mark.parametrize(
    "mutation",
    [
        "owner",
        "course",
        "profile_owner",
        "profile_version",
        "version_duplicate",
        "version_zero",
        "parent_foreign",
        "goal_overwrite",
        "request_parent_cycle",
    ],
)
def test_request_constraints(mutation):
    async def action(db, s):
        values = dict(
            user_id=s["owner"].id,
            course_id=s["course"].id,
            version=2,
            kind="adjustment",
            parent_request_id=s["req"].id,
            request_text="adjust",
            schema_version="free-course-v1",
            digest=DIGEST,
            evidence_snapshot={},
            nonsecret_config_snapshot={},
        )
        if mutation == "owner":
            values["user_id"] = s["other"].id
        if mutation == "course":
            values["course_id"] = s["other_course"].id
        if mutation == "profile_owner":
            values.update(profile_id=s["profile"].id, profile_version=1, user_id=s["other"].id)
        if mutation == "profile_version":
            values.update(profile_id=s["profile"].id, profile_version=9)
        if mutation == "version_duplicate":
            values["version"] = 1
        if mutation == "version_zero":
            values["version"] = 0
        if mutation == "parent_foreign":
            values["parent_request_id"] = uuid4()
        if mutation == "goal_overwrite":
            values.update(
                version=1, kind="original", parent_request_id=None, course_id=s["other_course"].id
            )
        if mutation == "request_parent_cycle":
            values.update(id=uuid4())
            values["parent_request_id"] = values["id"]
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                db.add(FreeCourseRequest(**values))
                await db.flush()
                await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    run_transaction(action)


@pytest.mark.parametrize(
    "mutation",
    [
        "foreign_scene",
        "duplicate_scene",
        "forward_dep",
        "cycle",
        "duplicate_dep",
        "no_scenes",
        "nine_scenes",
    ],
)
def test_plan_constraints(mutation):
    async def action(db, s):
        data = deepcopy(s["plan"].plan_json)
        if mutation == "foreign_scene":
            data["scenes"][0]["scene_id"] = str(uuid4())
        if mutation == "duplicate_scene":
            data["scenes"][1]["scene_id"] = data["scenes"][0]["scene_id"]
        if mutation == "forward_dep":
            data["scenes"][0]["depends_on"] = [data["scenes"][1]["scene_id"]]
        if mutation == "cycle":
            data["scenes"][0]["depends_on"] = [data["scenes"][0]["scene_id"]]
        if mutation == "duplicate_dep":
            data["scenes"][1]["depends_on"] *= 2
        if mutation == "no_scenes":
            data["scenes"] = []
        if mutation == "nine_scenes":
            data["scenes"] *= 5
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                db.add(
                    FreeCoursePlan(
                        user_id=s["owner"].id,
                        course_id=s["course"].id,
                        version=2,
                        request_id=s["req"].id,
                        schema_version="v1",
                        digest=DIGEST,
                        plan_json=data,
                    )
                )
                await db.flush()

    run_transaction(action)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "reordered",
        "foreign_content",
        "wrong_scene",
        "upstream_null",
        "wrong_plan",
        "missing_version_key",
    ],
)
def test_manifest_exact_bindings(mutation):
    async def action(db, s):
        m = deepcopy(s["version"].manifest_json)
        plan = s["plan"].id
        if mutation == "missing":
            m["scenes"].pop()
        if mutation == "reordered":
            m["scenes"].reverse()
        if mutation == "foreign_content":
            m["scenes"][0]["scene_version_id"] = str(uuid4())
        if mutation == "wrong_scene":
            m["scenes"][0]["scene_version_id"] = str(s["second"].id)
        if mutation == "upstream_null":
            m["scenes"][0]["scene_version_id"] = None
        if mutation == "wrong_plan":
            p = FreeCoursePlan(
                user_id=s["owner"].id,
                course_id=s["course"].id,
                version=2,
                request_id=s["req"].id,
                schema_version="v1",
                digest=DIGEST,
                plan_json=s["plan"].plan_json,
            )
            db.add(p)
            await db.flush()
            plan = p.id
        if mutation == "missing_version_key":
            del m["scenes"][0]["scene_version_id"]
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                db.add(
                    FreeCourseVersion(
                        user_id=s["owner"].id,
                        course_id=s["course"].id,
                        version=2,
                        plan_id=plan,
                        schema_version="v1",
                        digest=DIGEST,
                        manifest_json=m,
                    )
                )
                await db.flush()

    run_transaction(action)


@pytest.mark.parametrize(
    "table",
    [
        "free_courses",
        "free_course_requests",
        "free_course_plans",
        "free_course_scenes",
        "free_course_scene_versions",
        "free_course_versions",
        "free_course_node_links",
    ],
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_append_only_guards(table, operation):
    async def action(db, s):
        link = FreeCourseNodeLink(
            user_id=s["owner"].id,
            course_id=s["course"].id,
            course_version_id=s["version"].id,
            scene_id=None,
            node_id="stack",
            graph_version="mvp-0.2.0",
            relation="target",
            source="planner_suggestion",
            evidence_refs=[],
        )
        db.add(link)
        await db.flush()
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                sql = (
                    f"UPDATE {table} SET user_id=user_id"
                    if operation == "UPDATE"
                    else f"DELETE FROM {table}"
                )
                if table == "free_courses" and operation == "UPDATE":
                    sql = "UPDATE free_courses SET original_goal='changed'"
                await db.execute(text(sql))

    run_transaction(action)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_node",
        "unknown_graph",
        "unlisted_scene",
        "duplicate_course",
        "duplicate_scene",
        "cross_owner",
    ],
)
def test_node_links(mutation):
    async def action(db, s):
        v = dict(
            user_id=s["owner"].id,
            course_id=s["course"].id,
            course_version_id=s["version"].id,
            node_id="stack",
            graph_version="mvp-0.2.0",
            relation="target",
            source="user_selected",
            evidence_refs=[],
        )
        if mutation == "unknown_node":
            v["node_id"] = "not-a-node"
        if mutation == "unknown_graph":
            v["graph_version"] = "not-a-version"
        if mutation == "unlisted_scene":
            v["scene_id"] = s["scenes"][2].id
        if mutation == "cross_owner":
            v["user_id"] = s["other"].id
        if mutation in ["duplicate_course", "duplicate_scene"]:
            if mutation == "duplicate_scene":
                v["scene_id"] = s["scenes"][0].id
            db.add(FreeCourseNodeLink(**v))
            await db.flush()
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                db.add(FreeCourseNodeLink(**v))
                await db.flush()
                await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    run_transaction(action)


def test_deferred_head_foreign_course_and_rollback():
    async def action(db, s):
        old = s["course"].head_version_id
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(
                    text("UPDATE free_courses SET head_version_id=:v WHERE id=:c"),
                    dict(v=s["version"].id, c=s["other_course"].id),
                )
                await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert (
            await db.scalar(
                text("SELECT head_version_id FROM free_courses WHERE id=:c"), dict(c=s["course"].id)
            )
            == old
        )

    run_transaction(action)


def test_persisted_links_are_frozen_downgrade_refuses_and_user_cascades():
    async def prepare():
        engine = create_database_engine(database_url())
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                s = await seed(db)
                await db.commit()
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        db.add(
                            FreeCourseNodeLink(
                                user_id=s["owner"].id,
                                course_id=s["course"].id,
                                course_version_id=s["version"].id,
                                node_id="stack",
                                graph_version="mvp-0.2.0",
                                relation="target",
                                source="user_selected",
                                evidence_refs=[],
                            )
                        )
                        await db.flush()
                return s["owner"].id, s["other"].id
        finally:
            await engine.dispose()

    ids = asyncio.run(prepare())
    result = migrate(OLD, downgrade=True)
    assert result.returncode != 0 and "free course data prevents downgrade" in result.stderr

    async def clean():
        engine = create_database_engine(database_url())
        try:
            async with engine.begin() as conn:
                assert await conn.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
                for uid in ids:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), dict(u=uid))
                assert await conn.scalar(text("SELECT count(*) FROM free_courses")) == 0
        finally:
            await engine.dispose()

    asyncio.run(clean())


@pytest.mark.parametrize("mutation", ["foreign_profile", "wrong_profile_version"])
def test_profile_binding_rejects_other_owner_with_own_course(mutation):
    async def action(db, s):
        other_profile = StudentProfile(
            user_id=s["other"].id, version=1, merge_rule_version="synthetic"
        )
        db.add(other_profile)
        await db.flush()
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                db.add(
                    FreeCourseRequest(
                        user_id=s["owner"].id,
                        course_id=s["course"].id,
                        version=2,
                        kind="adjustment",
                        parent_request_id=s["req"].id,
                        request_text="adjust",
                        profile_id=other_profile.id
                        if mutation == "foreign_profile"
                        else s["profile"].id,
                        profile_version=1 if mutation == "foreign_profile" else 2,
                        schema_version="v1",
                        digest=DIGEST,
                        evidence_snapshot={},
                        nonsecret_config_snapshot={},
                    )
                )
                await db.flush()
                await db.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    run_transaction(action)


@pytest.mark.parametrize(
    "mutation",
    [
        "not_in_plan",
        "missing_dependency",
        "wrong_digest",
        "wrong_upstream",
        "reused_old_plan",
        "duplicate_version",
    ],
)
def test_exact_scene_version_dependencies(mutation):
    async def action(db, s):
        values = dict(
            user_id=s["owner"].id,
            course_id=s["course"].id,
            scene_id=s["scenes"][1].id,
            version=2,
            plan_id=s["plan"].id,
            schema_version="v1",
            content_json={"blocks": []},
            actions_json=[],
            content_digest=DIGEST,
            dependency_bindings=deepcopy(s["second"].dependency_bindings),
        )
        if mutation == "not_in_plan":
            values.update(scene_id=s["scenes"][2].id, dependency_bindings=[])
        if mutation == "missing_dependency":
            values["dependency_bindings"] = []
        if mutation == "wrong_digest":
            values["dependency_bindings"][0]["content_digest"] = "1" * 64
        if mutation == "wrong_upstream":
            values["dependency_bindings"][0]["scene_version_id"] = str(s["second"].id)
        if mutation == "duplicate_version":
            values["version"] = 1
        if mutation == "reused_old_plan":
            p = FreeCoursePlan(
                user_id=s["owner"].id,
                course_id=s["course"].id,
                version=2,
                request_id=s["req"].id,
                schema_version="v1",
                digest=DIGEST,
                plan_json=s["plan"].plan_json,
            )
            db.add(p)
            await db.flush()
            values["plan_id"] = p.id
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                db.add(FreeCourseSceneVersion(**values))
                await db.flush()

    run_transaction(action)


def test_manifest_rejects_changed_upstream_even_with_same_digest():
    async def action(db, s):
        upstream = FreeCourseSceneVersion(
            user_id=s["owner"].id,
            course_id=s["course"].id,
            scene_id=s["scenes"][0].id,
            version=2,
            plan_id=s["plan"].id,
            schema_version="v1",
            content_json={},
            actions_json=[],
            dependency_bindings=[],
            content_digest=DIGEST,
        )
        db.add(upstream)
        await db.flush()
        manifest = deepcopy(s["version"].manifest_json)
        manifest["scenes"][0]["scene_version_id"] = str(upstream.id)
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                db.add(
                    FreeCourseVersion(
                        user_id=s["owner"].id,
                        course_id=s["course"].id,
                        version=2,
                        plan_id=s["plan"].id,
                        schema_version="v1",
                        digest=DIGEST,
                        manifest_json=manifest,
                    )
                )
                await db.flush()

    run_transaction(action)


def test_head_cannot_regress_and_failed_transaction_leaves_old_head():
    async def action(db, s):
        v = FreeCourseVersion(
            user_id=s["owner"].id,
            course_id=s["course"].id,
            version=3,
            plan_id=s["plan"].id,
            schema_version="v1",
            digest=DIGEST,
            manifest_json=s["version"].manifest_json,
        )
        db.add(v)
        await db.flush()
        s["course"].head_version_id = v.id
        await db.flush()
        with pytest.raises(DBAPIError):
            async with db.begin_nested():
                await db.execute(
                    text("UPDATE free_courses SET head_version_id=:v WHERE id=:c"),
                    dict(v=s["version"].id, c=s["course"].id),
                )
        assert (
            await db.scalar(
                text("SELECT head_version_id FROM free_courses WHERE id=:c"), dict(c=s["course"].id)
            )
            == v.id
        )

    run_transaction(action)


def test_concurrent_duplicate_version_has_single_winner():
    async def action():
        engine = create_database_engine(database_url())
        try:
            async with AsyncSession(engine, expire_on_commit=False) as db:
                s = await seed(db)
                await db.commit()
                ids = (s["owner"].id, s["other"].id)
                values = dict(
                    user_id=s["owner"].id,
                    course_id=s["course"].id,
                    version=2,
                    plan_id=s["plan"].id,
                    schema_version="v1",
                    digest=DIGEST,
                    manifest_json=s["version"].manifest_json,
                )

            async def write():
                async with AsyncSession(engine) as db:
                    try:
                        db.add(FreeCourseVersion(**values))
                        await db.commit()
                        return "committed"
                    except DBAPIError:
                        await db.rollback()
                        return "rejected"

            assert sorted(await asyncio.gather(write(), write())) == ["committed", "rejected"]
            async with engine.begin() as conn:
                assert (
                    await conn.scalar(
                        text(
                            "SELECT count(*) FROM free_course_versions "
                            "WHERE course_id=:c AND version=2"
                        ),
                        dict(c=s["course"].id),
                    )
                    == 1
                )
                for uid in ids:
                    await conn.execute(text("DELETE FROM users WHERE id=:u"), dict(u=uid))
        finally:
            await engine.dispose()

    asyncio.run(action())
