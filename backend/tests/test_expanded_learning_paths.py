"""Expanded paths preserve evidence/history and revalidate actual course authority."""

import asyncio
import json
import os
from pathlib import Path
from time import perf_counter

import pytest
from catalog_fixtures import approval_fixture, package_fixture
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_path_versions import add_mastered_pointer
from test_paths_api import guest, headers, seed_profile, validate_contract

from app.core.database import create_database_engine
from app.models.catalog import CatalogRelease
from app.models.learning_state import LearningEvidence, NodeMasteryRevision
from app.services.catalog_publication import publish_catalog, revoke_catalog
from app.services.knowledge_graph_versions import graph_repository_for_version
from app.services.path_rules import PathMastery, plan_learning_path

DATABASE = os.getenv("EDUMIND_TEST_DATABASE_URL")
pg = pytest.mark.skipif(not DATABASE, reason="isolated PostgreSQL URL not set")


def run_db(work):
    async def exercise():
        assert DATABASE is not None
        engine = create_database_engine(DATABASE)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            return await work(sessions)
        finally:
            await engine.dispose()

    return asyncio.run(exercise())


def test_all_thirty_targets_preserve_unknowns_and_prerequisite_order():
    graph = graph_repository_for_version("phase-1.1.0")
    for node in graph.all_nodes():
        result = plan_learning_path(
            graph,
            target_node_id=node.id,
            mastery={"c-pointer": PathMastery(0.9, "mastered", ("quiz",))},
        )
        ids = [step.node_id for step in result.steps]
        assert "c-pointer" not in ids
        for step in result.steps:
            assert step.status == "unseen" and step.score == 0
            assert step.reason
            current = graph.get_node(step.node_id)
            assert current is not None
            assert all(
                prereq == "c-pointer" or ids.index(prereq) < ids.index(step.node_id)
                for prereq in current.prerequisites
            )


@pg
def test_graph_switch_replay_rollback_does_not_rescore(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", DATABASE)
    monkeypatch.delenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", raising=False)
    client, owner, csrf = guest()
    seed_profile(owner)
    run_db(lambda sessions: add_mastered_pointer(sessions, owner))

    async def counts(sessions):
        async with sessions() as db:
            return tuple(
                [
                    await db.scalar(
                        select(func.count()).select_from(model).where(model.user_id == owner)
                    )
                    for model in (LearningEvidence, NodeMasteryRevision)
                ]
            )

    before = run_db(counts)
    initial_mastery = client.get("/api/mastery").json()["items"]
    target = {"target_node_id": "single-linked-list"}
    first = client.post(
        "/api/path/plan", json=target, headers=headers(csrf, "expanded-old-plan-001")
    )
    assert first.status_code == 201
    old = first.json()
    assert "c-pointer" not in old["nodes"]
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "phase-1.1.0")
    restored = client.get("/api/path/current", params=target)
    assert restored.status_code == 200
    assert restored.json()["graph_version"] == "mvp-0.2.0"
    assert restored.json()["is_stale"]
    assert restored.json()["node_details"] == old["node_details"]
    new = client.post(
        "/api/path/replan", json=target, headers=headers(csrf, "expanded-new-plan-001", 1)
    )
    assert new.status_code == 200
    assert new.json()["version"] == 2
    assert new.json()["graph_version"] == "phase-1.1.0"
    replay = client.post(
        "/api/path/plan", json=target, headers=headers(csrf, "expanded-old-plan-001")
    )
    assert replay.json()["version"] == 1 and replay.json()["is_stale"]
    assert replay.json()["node_details"] == old["node_details"]
    # Expanded targets persist unknown mastery rather than fabricated evidence.
    expanded = client.post(
        "/api/path/plan",
        json={"target_node_id": "breadth-first-search"},
        headers=headers(csrf, "expanded-bfs-plan-001"),
    )
    assert expanded.status_code == 201
    validate_contract("LearningPath", expanded.json())
    assert all(item["mastery_known"] is False for item in expanded.json()["node_details"])
    assert all(
        item["reason"] == "no_reviewed_course" for item in expanded.json()["learning_availability"]
    )
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "mvp-0.2.0")
    historic = client.get("/api/path/current", params={"target_node_id": "breadth-first-search"})
    assert historic.status_code == 200 and historic.json()["is_stale"]
    assert historic.json()["graph_version"] == "phase-1.1.0"
    rollback = client.post(
        "/api/path/replan", json=target, headers=headers(csrf, "expanded-rollback-001", 2)
    )
    assert rollback.status_code == 200 and rollback.json()["version"] == 3
    assert rollback.json()["mastery_revision_watermark"] == old["mastery_revision_watermark"]
    assert run_db(counts) == before == (1, 1)
    assert client.get("/api/mastery").json()["items"] == initial_mastery
    other, _, _ = guest()
    assert (
        other.get(
            "/api/path/current", params={"target_node_id": "breadth-first-search"}
        ).status_code
        == 404
    )


@pg
def test_course_eligibility_revalidates_withdrawal_and_corruption(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", DATABASE)
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "phase-1.1.0")
    client, owner, csrf = guest()
    seed_profile(owner)
    package = package_fixture()

    async def publish(sessions):
        async with sessions() as db:
            release = await publish_catalog(
                db, package, approval=approval_fixture(package), trusted_digest=package.digest
            )
            await db.commit()
            return release.id

    release_id = run_db(publish)
    target = {"target_node_id": "breadth-first-search"}
    result = client.post(
        "/api/path/plan", json=target, headers=headers(csrf, "expanded-courses-001")
    )
    assert result.status_code == 201
    availability = {item["node_id"]: item for item in result.json()["learning_availability"]}
    assert availability["breadth-first-search"]["status"] == "unavailable"
    assert availability["array"]["reason"] == "approved_catalog"

    from sqlalchemy.exc import IntegrityError

    from app.services.catalog_package import CatalogError

    async def reject_tamper(sessions):
        async with sessions() as db:
            release = await db.get(CatalogRelease, release_id)
            release.manifest_digest = "0" * 64
            with pytest.raises(IntegrityError, match="immutable"):
                await db.commit()
            await db.rollback()

    run_db(reject_tamper)
    # Simulate a decode/integrity failure; real DB immutability remains enforced.
    with monkeypatch.context() as failure_context:

        def invalid_release(_release):
            raise CatalogError("CATALOG_INTEGRITY_FAILED")

        failure_context.setattr("app.services.path_availability.release_package", invalid_release)
        failure = client.get("/api/path/current", params=target)
        assert failure.status_code == 503
        assert failure.json()["code"] == "LEARNING_AVAILABILITY_UNAVAILABLE"

    async def withdraw(sessions):
        async with sessions() as db:
            await revoke_catalog(db, release_id)
            await db.commit()

    run_db(withdraw)
    withdrawn = client.get("/api/path/current", params=target)
    assert withdrawn.status_code == 200
    assert all(
        item["status"] == "unavailable" for item in withdrawn.json()["learning_availability"]
    )
    assert withdrawn.json()["version"] == result.json()["version"]


@pg
def test_expanded_ordinary_path_request_p95(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", DATABASE)
    monkeypatch.setenv("EDUMIND_KNOWLEDGE_GRAPH_VERSION", "phase-1.1.0")
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda: pytest.fail("path constructed a Provider"),
    )
    client, owner, csrf = guest()
    seed_profile(owner)
    from app.services.catalog_package import validate_package

    package = package_fixture()
    payload = package.payload()
    payload["manifest"]["package_id"] = "test-t033-perf"
    package = validate_package(payload)

    async def publish(sessions):
        async with sessions() as db:
            release = await publish_catalog(
                db, package, approval=approval_fixture(package), trusted_digest=package.digest
            )
            await db.commit()
            return release.id

    release_id = run_db(publish)
    timings = {"plan": [], "read": []}
    for index, node in enumerate(graph_repository_for_version("phase-1.1.0").all_nodes()):
        target = {"target_node_id": node.id}
        started = perf_counter()
        result = client.post(
            "/api/path/plan", json=target, headers=headers(csrf, f"expanded-latency-{index:03d}")
        )
        timings["plan"].append((perf_counter() - started) * 1000)
        assert result.status_code == 201
        started = perf_counter()
        result = client.get("/api/path/current", params=target)
        timings["read"].append((perf_counter() - started) * 1000)
        assert result.status_code == 200

    async def withdraw(sessions):
        async with sessions() as db:
            await revoke_catalog(db, release_id)
            await db.commit()

    run_db(withdraw)
    p95 = {kind: sorted(samples)[28] for kind, samples in timings.items()}
    evidence = Path(__file__).resolve().parents[2] / "local-materials/phase-1-t033/latency.json"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(
        json.dumps(
            {
                "environment": "TestClient + isolated PG + signed TEST_ONLY catalog",
                "denominator": {"plan": 30, "read": 30},
                "samples_ms": timings,
                "nearest_rank_p95_ms": p95,
                "provider_requests": 0,
            },
            indent=2,
        )
        + "\n"
    )
    assert all(value <= 200 for value in p95.values()), p95


@pg
def test_reviewed_owner_unit_requires_complete_matching_visible_resources(monkeypatch):
    from uuid import uuid4

    from app.models.auth import User
    from app.models.learning import GeneratedResource, LearningScene, LearningUnit, utc_now
    from app.services.path_availability import path_learning_availability

    async def exercise(sessions):
        async with sessions() as db:
            owner = User(is_guest=True)
            db.add(owner)
            await db.flush()
            unit = LearningUnit(
                user_id=owner.id,
                title="TEST_ONLY",
                status="ready",
                knowledge_point_id="breadth-first-search",
            )
            db.add(unit)
            await db.flush()
            scene = LearningScene(
                learning_unit_id=unit.id,
                scene_key="intro",
                scene_order=1,
                scene_type="explanation",
                review_status="passed",
            )
            db.add(scene)
            await db.flush()
            for kind in ("explanation", "code"):
                db.add(
                    GeneratedResource(
                        user_id=owner.id,
                        learning_unit_id=unit.id,
                        scene_id=scene.id,
                        resource_type=kind,
                        knowledge_point_id="breadth-first-search",
                        content={"TEST_ONLY": True},
                        origin_type="generated",
                        review_status="passed",
                        published_at=utc_now(),
                    )
                )
            await db.commit()

            async def available(for_owner=owner.id):
                return (
                    await path_learning_availability(
                        db, owner_id=for_owner, node_ids=["breadth-first-search"]
                    )
                )[0]

            monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
            assert (await available())["status"] == "unavailable"
            quiz = GeneratedResource(
                user_id=owner.id,
                learning_unit_id=unit.id,
                scene_id=scene.id,
                resource_type="exercise",
                knowledge_point_id="array",
                content={"TEST_ONLY": True},
                origin_type="generated",
                review_status="passed",
                published_at=utc_now(),
            )
            db.add(quiz)
            await db.commit()
            assert (await available())["status"] == "unavailable"
            db.add(
                GeneratedResource(
                    user_id=owner.id,
                    learning_unit_id=unit.id,
                    scene_id=scene.id,
                    resource_type="exercise",
                    knowledge_point_id="breadth-first-search",
                    content={"TEST_ONLY": True},
                    origin_type="generated",
                    review_status="passed",
                    published_at=utc_now(),
                    version=2,
                )
            )
            await db.commit()
            assert (await available())["reason"] == "reviewed_owner_unit"
            assert (await available())["learning_unit_id"] == str(unit.id)
            assert (await available(uuid4()))["status"] == "unavailable"
            monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
            assert (await available())["status"] == "unavailable"
            monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
            scene.review_status = "failed"
            await db.commit()
            assert (await available())["status"] == "unavailable"

    run_db(exercise)
