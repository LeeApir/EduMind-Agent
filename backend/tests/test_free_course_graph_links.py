"""Exact optional suggestions and real PG history; no model quality/learning claims."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.free_course import FreeCourseNodeLink, FreeCourseVersion
from app.models.learning_state import LearningEvidence, LearningPathVersion, NodeMasteryRevision
from app.services.free_course_graph_links import (
    LINK_RULE_VERSION,
    _mentions,
    commit_linked_manifest,
    read_graph_context,
    suggest_node_links,
)
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository
from app.services.knowledge_graph import KnowledgeGraphValidationError
from app.services.knowledge_graph_versions import graph_repository_for_version

ROOT = Path(__file__).resolve().parents[2]


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual dedicated PostgreSQL is required; no environment skip"
    parsed = make_url(value)
    assert parsed.host == "127.0.0.1" and parsed.port == 15437
    assert (parsed.database or "").startswith("edumind_catalog_p15_t009_")
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


async def prepare(db, owner, goal, scenes):
    repo = SnapshotRepository(db, owner)
    created = await repo.create_course(goal, key="create")
    cid = UUID(created["course_id"])
    fence = await repo.acquire_write_fence(cid, UUID(created["operation_id"]))
    candidate = {
        "title": "synthetic optional graph fixture",
        "scenes": [
            dict(scene_key=f"s{i}", title=title, purpose=purpose, depends_on=[])
            for i, (title, purpose) in enumerate(scenes)
        ],
    }
    saved = await repo.store_plan(cid, fence, expected_head=None, key="plan", candidate=candidate)
    await db.commit()
    return repo, cid, fence, UUID(saved["plan_id"])


@pytest.mark.parametrize("version", ["mvp-0.2.0", "phase-1.1.0"])
@pytest.mark.parametrize(
    "phrase,expected",
    [
        ("理解抽象容器的取舍", set()),
        ("学习数组", {"array"}),
        ("比较数组、单链表、栈和队列", {"array", "single-linked-list", "stack", "queue"}),
        ("循环队列", {"circular-queue"}),
        ("array array", {"array"}),
        ("not-array array-stack", set()),
    ],
)
def test_conservative_mentions_and_longest_match(version, phrase, expected):
    if version == "phase-1.1.0" and phrase == "not-array array-stack":
        expected = {"array-stack"}
    found = _mentions(phrase, graph_repository_for_version(version))
    assert {item["node_id"] for item in found} == expected
    for item in found:
        assert phrase[item["start"] : item["end"]] == item["excerpt"]


@pytest.mark.parametrize("version", ["mvp-0.2.0", "phase-1.1.0"])
def test_all_approved_node_names_and_ids_have_exact_provenance(version):
    graph = graph_repository_for_version(version)
    for node in graph.all_nodes():
        for token in (node.id, node.name):
            mentions = _mentions(token, graph)
            assert {item["node_id"] for item in mentions} == {node.id}
            assert mentions[0]["excerpt"] == token


@pytest.mark.parametrize("goal,n", [("抽象容器的取舍", 0), ("数组", 1), ("数组和单链表", 2)])
def test_zero_one_many_course_links_do_not_change_goal_or_create_scores(goal, n):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(db, owner, goal, [("first", "compare")])
            suggestion = await suggest_node_links(db, owner, cid, pid, graph_version="mvp-0.2.0")
            assert len(suggestion["links"]) == n
            assert suggestion["status"] == ("suggested" if n else "no_match")
            assert all(link["source"] == "planner_suggestion" for link in suggestion["links"])
            saved = await commit_linked_manifest(
                db,
                owner,
                cid,
                fence,
                plan_id=pid,
                expected_head=None,
                bindings=[None],
                key="manifest",
                graph_version="mvp-0.2.0",
            )
            replay = await commit_linked_manifest(
                db,
                owner,
                cid,
                fence,
                plan_id=pid,
                expected_head=None,
                bindings=[None],
                key="manifest",
                graph_version="mvp-0.2.0",
            )
            assert saved == replay
            await db.commit()
        async with AsyncSession(engine) as db:
            context = await read_graph_context(db, owner, cid, version=1)
            assert context["original_goal"] == goal
            assert context["scoring_eligible"] is False
            assert len(context["node_links"]) == len(context["recommended_paths"]) == n
            assert await db.scalar(select(func.count()).select_from(FreeCourseVersion)) == 1
            rows = list((await db.scalars(select(FreeCourseNodeLink))).all())
            assert len(rows) == n
            for row in rows:
                ref = row.evidence_refs[0]
                assert ref["course_id"] == str(cid) and ref["kind"] == "original_goal"
                assert ref["rule_version"] == LINK_RULE_VERSION
                assert goal[ref["start"] : ref["end"]] == ref["excerpt"]
            for model in (LearningEvidence, NodeMasteryRevision, LearningPathVersion):
                assert await db.scalar(select(func.count()).select_from(model)) == 0
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 1

    exercise(action)


def test_scenes_keep_separate_many_links_and_exact_plan_evidence():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(
                db,
                owner,
                "一个自由目标",
                [("数组与栈", "再次比较数组和队列"), ("例子", "抽象容器")],
            )
            plan = await repo.get_plan(cid, pid)
            suggestions = await suggest_node_links(db, owner, cid, pid, graph_version="phase-1.1.0")
            assert len(suggestions["links"]) == 3
            for link in suggestions["links"]:
                assert link["scene_id"] == plan["scenes"][0]["scene_id"]
                assert link["relation"] == "supporting"
                for ref in link["evidence_refs"]:
                    assert ref["plan_id"] == str(pid) and ref["plan_digest"] == plan["digest"]
                    s = plan["scenes"][0][ref["field"]]
                    assert s[ref["start"] : ref["end"]] == ref["excerpt"]
            array = next(link for link in suggestions["links"] if link["node_id"] == "array")
            assert len(array["evidence_refs"]) == 2
            await commit_linked_manifest(
                db,
                owner,
                cid,
                fence,
                plan_id=pid,
                expected_head=None,
                bindings=[None, None],
                key="manifest",
                graph_version="phase-1.1.0",
            )
            await db.commit()
            context = await read_graph_context(db, owner, cid, version=1)
            assert context["recommended_paths"] == []
            assert len(context["node_links"]) == 3

    exercise(action)


@pytest.mark.parametrize("unavailable", ["unknown", "damaged-release"])
def test_optional_graph_unavailable_does_not_block_manifest(monkeypatch, unavailable):
    if unavailable == "damaged-release":

        def fail(_version):
            raise KnowledgeGraphValidationError("synthetic release unavailable")

        monkeypatch.setattr(
            "app.services.free_course_graph_links.graph_repository_for_version", fail
        )

    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(db, owner, "数组", [("数组", "数组")])
            suggestions = await suggest_node_links(db, owner, cid, pid, graph_version=unavailable)
            assert suggestions == dict(
                status="graph_unavailable", graph_version=unavailable, links=[]
            )
            await commit_linked_manifest(
                db,
                owner,
                cid,
                fence,
                plan_id=pid,
                expected_head=None,
                bindings=[None],
                key="manifest",
                graph_version=unavailable,
            )
            await db.commit()
            assert (await repo.get_version(cid, 1))["node_links"] == []

    exercise(action)


def test_history_pins_graph_versions_and_path_is_only_suggestion(monkeypatch):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(db, owner, "学习单链表", [("first", "example")])
            for i, version in enumerate(["mvp-0.2.0", "phase-1.1.0"]):
                await commit_linked_manifest(
                    db,
                    owner,
                    cid,
                    fence,
                    plan_id=pid,
                    expected_head=i or None,
                    bindings=[None],
                    key=f"manifest-{i}",
                    graph_version=version,
                )
            await db.commit()
        monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "invalid-current-config")
        async with AsyncSession(engine) as db:
            for i, version in enumerate(["mvp-0.2.0", "phase-1.1.0"], 1):
                context = await read_graph_context(db, owner, cid, version=i)
                assert context["original_goal"] == "学习单链表"
                path = context["recommended_paths"][0]
                assert path["kind"] == "suggestion" and path["graph_version"] == version
                assert path["target_node_id"] == "single-linked-list"
                assert path["suggested_start_node_id"] == "c-pointer"
                assert all(s["mastery_known"] is False for s in path["nodes"])
                assert all("score" not in s["reason"] for s in path["nodes"])
                assert context["node_links"][0]["graph_version"] == version
            assert (await SnapshotRepository(db, owner).get_course(cid))["head_version"] == 2
            assert await db.scalar(select(func.count()).select_from(LearningPathVersion)) == 0

    exercise(action)


def test_read_is_detached_and_missing_historical_graph_keeps_links(monkeypatch):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(db, owner, "数组", [("数组", "比较")])
            await commit_linked_manifest(
                db,
                owner,
                cid,
                fence,
                plan_id=pid,
                expected_head=None,
                bindings=[None],
                key="manifest",
                graph_version="mvp-0.2.0",
            )
            await db.commit()
            context = await read_graph_context(db, owner, cid, version=1)
            context["node_links"][0]["node_id"] = "forged"

            def fail(_version):
                raise KnowledgeGraphValidationError("synthetic missing graph")

            monkeypatch.setattr(
                "app.services.free_course_graph_links.graph_repository_for_version", fail
            )
            context = await read_graph_context(db, owner, cid, version=1)
            assert context["node_links"][0]["node_id"] == "array"
            assert context["recommended_paths"] == []

    exercise(action)


def test_owner_and_plan_isolation_are_not_swallowed_as_optional_failure():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(db, owner, "数组", [("first", "example")])
            for uid, plan in [(other, pid), (owner, uuid4())]:
                with pytest.raises(SnapshotError, match="NOT_FOUND"):
                    await suggest_node_links(db, uid, cid, plan, graph_version="unknown")
            with pytest.raises(SnapshotError, match="NOT_FOUND"):
                await read_graph_context(db, other, cid, version=1)
            assert (await repo.get_course(cid))["head_version"] is None

    exercise(action)


@pytest.mark.parametrize("graph_version", ["mvp-0.2.0", "unknown"])
def test_no_mapping_does_not_hide_existing_scene_content(graph_version):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(
                db, owner, "自定义容器", [("例子", "抽象的存取操作")]
            )
            plan = await repo.get_plan(cid, pid)
            sid = UUID(plan["scenes"][0]["scene_id"])
            content = {"blocks": [{"type": "text", "markdown": "synthetic private fixture"}]}
            stored = await repo.store_scene(
                cid,
                fence,
                expected_head=None,
                key="scene",
                plan_id=pid,
                scene_id=sid,
                content=content,
                actions=[],
                dependencies=[],
            )
            await commit_linked_manifest(
                db,
                owner,
                cid,
                fence,
                plan_id=pid,
                expected_head=None,
                bindings=[UUID(stored["scene_version_id"])],
                key="manifest",
                graph_version=graph_version,
            )
            await db.commit()
        async with AsyncSession(engine) as db:
            snapshot = await SnapshotRepository(db, owner).get_scene_snapshot(cid, 1, sid)
            assert snapshot["content"] == content
            context = await read_graph_context(db, owner, cid, version=1)
            assert context["node_links"] == context["recommended_paths"] == []
            assert context["scoring_eligible"] is False

    exercise(action)


def test_historical_private_plan_without_purpose_remains_usable():
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(db, owner, "自由目标", [("first", "example")])
            stored = await repo.store_plan(
                cid,
                fence,
                expected_head=None,
                key="sparse-plan",
                candidate={"scenes": [{"scene_key": "sparse", "title": "数组", "depends_on": []}]},
            )
            context = await suggest_node_links(
                db, owner, cid, UUID(stored["plan_id"]), graph_version="mvp-0.2.0"
            )
            assert len(context["links"]) == 1 and context["links"][0]["node_id"] == "array"

    exercise(action)


@pytest.mark.parametrize("mode", ["cancel", "expired", "stale", "rollback"])
def test_no_links_escape_fence_or_transaction(mode):
    async def action(engine, owner, other):
        async with AsyncSession(engine) as db:
            repo, cid, fence, pid = await prepare(db, owner, "数组", [("first", "example")])
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
            await db.commit()
            if mode == "rollback":
                await commit_linked_manifest(
                    db,
                    owner,
                    cid,
                    fence,
                    plan_id=pid,
                    expected_head=None,
                    bindings=[None],
                    key="manifest",
                    graph_version="mvp-0.2.0",
                )
                await db.rollback()
            else:
                with pytest.raises(SnapshotError):
                    await commit_linked_manifest(
                        db,
                        owner,
                        cid,
                        fence,
                        plan_id=pid,
                        expected_head=99 if mode == "stale" else None,
                        bindings=[None],
                        key="manifest",
                        graph_version="mvp-0.2.0",
                    )
                await db.rollback()
            assert await db.scalar(select(func.count()).select_from(FreeCourseNodeLink)) == 0
            assert await db.scalar(select(func.count()).select_from(FreeCourseVersion)) == 0
            assert (await repo.get_course(cid))["head_version"] is None

    exercise(action)
