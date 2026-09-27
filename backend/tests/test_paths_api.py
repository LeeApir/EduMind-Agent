"""Owner-isolated path contracts, stale versions, replay, and local query latency."""

import asyncio
import json
import os
import time
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.agents.profile_schema import apply_manual_correction, empty_transient_profile
from app.core.database import create_database_engine
from app.main import app
from app.models.learning_state import LearningEvidence, NodeMasteryCurrent, NodeMasteryRevision
from app.services.owned_learning import latest_profile
from app.services.profile_updates import persist_profile_version, snapshot_profile

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def validate_contract(name: str, payload: object) -> None:
    specification = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/api/openapi.yaml").read_text(encoding="utf-8")
    )
    Draft202012Validator(
        {"components": specification["components"], "$ref": f"#/components/schemas/{name}"}
    ).validate(payload)


def guest() -> tuple[TestClient, UUID, str]:
    client = TestClient(app, base_url="https://testserver")
    created = client.post("/api/auth/guest")
    assert created.status_code == 201
    return client, UUID(created.json()["user"]["id"]), created.json()["csrf_token"]


def headers(csrf: str, key: str, version: int | None = None) -> dict[str, str]:
    result = {"X-CSRF-Token": csrf, "Origin": "https://testserver", "Idempotency-Key": key}
    if version is not None:
        result["If-Match-Path-Version"] = str(version)
    return result


def seed_profile(owner_id: UUID, *, correction: bool = False) -> None:
    assert TEST_DATABASE_URL is not None

    async def insert() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as db:
                if correction:
                    previous = await latest_profile(db, owner_id)
                    assert previous is not None
                    profile = apply_manual_correction(
                        snapshot_profile(previous),
                        {"engineering_preference": {"code_first": True}},
                        observed_at="2026-09-26T10:40:00+08:00",
                    )
                else:
                    profile = empty_transient_profile("想学习单链表")
                await persist_profile_version(db, owner_id=owner_id, profile=profile)
        finally:
            await engine.dispose()

    asyncio.run(insert())


def test_plan_current_contract_owner_isolation_and_no_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setattr(
        "app.core.provider_factory.build_default_provider_gateway",
        lambda: pytest.fail("path query constructed a Provider"),
    )
    client, owner_id, csrf = guest()
    seed_profile(owner_id)
    first = client.post(
        "/api/path/plan",
        json={"target_node_id": "single-linked-list"},
        headers=headers(csrf, "path-plan-contract-001"),
    )
    assert first.status_code == 201
    body = first.json()
    validate_contract("LearningPath", body)
    assert body["version"] == 1 and body["is_stale"] is False
    assert body["current_node_id"] == "c-pointer"
    assert body["nodes"][-1] == "single-linked-list"
    assert body["node_details"][0]["estimated_minutes"] > 0
    assert all(reason["summary"] for reason in body["reasons"])
    read = client.get("/api/path/current", params={"target_node_id": "single-linked-list"})
    assert read.status_code == 200 and read.json() == body
    assert read.headers["Cache-Control"] == "no-store"
    other, other_id, other_csrf = guest()
    assert (
        other.get("/api/path/current", params={"target_node_id": "single-linked-list"}).status_code
        == 404
    )
    assert other.get("/api/mastery").json()["items"] == []
    seed_profile(other_id)
    own_plan = other.post(
        "/api/path/plan",
        json={"target_node_id": "array"},
        headers=headers(other_csrf, "path-plan-contract-001"),
    )
    assert own_plan.status_code == 201 and own_plan.json()["target_node_id"] == "array"
    unknown = client.post(
        "/api/path/plan",
        json={"target_node_id": "missing-node"},
        headers=headers(csrf, "path-plan-missing-001"),
    )
    assert unknown.status_code == 404 and unknown.json()["code"] == "GRAPH_NODE_NOT_FOUND"
    forged = client.post(
        "/api/path/plan",
        json={"target_node_id": "array", "owner_id": str(owner_id)},
        headers=headers(csrf, "path-plan-forged-0001"),
    )
    assert forged.status_code == 422


def test_mastery_read_returns_only_owner_safe_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, _ = guest()
    other, _, _ = guest()

    async def seed() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        try:
            sessions = async_sessionmaker(engine)
            async with sessions() as db:
                fact = LearningEvidence(
                    user_id=owner_id,
                    idempotency_key="mastery-read-evidence-001",
                    request_digest="a" * 64,
                    evidence_type="quiz_attempt",
                    knowledge_node_id="c-pointer",
                    schema_version=1,
                    rule_version="quiz-v1",
                    payload={"raw_answer": "private raw answer"},
                )
                db.add(fact)
                await db.flush()
                revision = NodeMasteryRevision(
                    user_id=owner_id,
                    knowledge_node_id="c-pointer",
                    revision=1,
                    previous_score=0.0,
                    score=0.5,
                    status="learning",
                    rule_version="mastery-v1",
                    evidence_id=fact.id,
                    evidence_summary=["quiz_score=0.5000;wrong_streak=0"],
                )
                db.add(revision)
                await db.flush()
                db.add(
                    NodeMasteryCurrent(
                        user_id=owner_id,
                        knowledge_node_id="c-pointer",
                        revision_id=revision.id,
                        revision=1,
                        score=0.5,
                        status="learning",
                        rule_version="mastery-v1",
                    )
                )
                await db.commit()
        finally:
            await engine.dispose()

    asyncio.run(seed())
    read = client.get("/api/mastery")
    assert read.status_code == 200
    validate_contract("MasteryList", read.json())
    assert read.json()["items"][0]["knowledge_node_id"] == "c-pointer"
    assert "private raw answer" not in read.text
    assert str(owner_id) not in read.text
    assert other.get("/api/mastery").json()["items"] == []


def test_replan_requires_version_and_replays_original_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, csrf = guest()
    seed_profile(owner_id)
    target = {"target_node_id": "single-linked-list"}
    first = client.post("/api/path/plan", json=target, headers=headers(csrf, "path-first-key-0001"))
    assert first.status_code == 201
    seed_profile(owner_id, correction=True)
    assert client.get("/api/path/current", params=target).json()["is_stale"] is True
    replan = client.post(
        "/api/path/replan",
        json={**target, "reason": "profile_changed"},
        headers=headers(csrf, "path-replan-key-001", 1),
    )
    assert replan.status_code == 200
    assert replan.json()["version"] == 2 and replan.json()["is_stale"] is False
    replay = client.post(
        "/api/path/replan",
        json={**target, "reason": "profile_changed"},
        headers=headers(csrf, "path-replan-key-001", 1),
    )
    assert replay.status_code == 200 and replay.json()["version"] == 2
    old = client.post("/api/path/plan", json=target, headers=headers(csrf, "path-first-key-0001"))
    assert old.status_code == 201 and old.json()["version"] == 1 and old.json()["is_stale"] is True
    conflict = client.post(
        "/api/path/replan",
        json=target,
        headers=headers(csrf, "path-stale-key-0001", 1),
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "PATH_VERSION_CONFLICT"
    key_conflict = client.post(
        "/api/path/plan",
        json={"target_node_id": "array"},
        headers=headers(csrf, "path-first-key-0001"),
    )
    assert key_conflict.status_code == 409 and key_conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_local_path_read_p95_is_below_200ms(monkeypatch: pytest.MonkeyPatch) -> None:
    assert TEST_DATABASE_URL is not None
    monkeypatch.setenv("EDUMIND_DATABASE_URL", TEST_DATABASE_URL)
    client, owner_id, csrf = guest()
    seed_profile(owner_id)
    target = {"target_node_id": "single-linked-list"}
    assert (
        client.post(
            "/api/path/plan", json=target, headers=headers(csrf, "path-perf-key-0001")
        ).status_code
        == 201
    )
    samples = []
    for _ in range(20):
        started = time.perf_counter()
        result = client.get("/api/path/current", params=target)
        samples.append(time.perf_counter() - started)
        assert result.status_code == 200
    p95 = sorted(samples)[18]
    assert p95 < 0.2, f"local TestClient + PostgreSQL path P95={p95:.4f}s"
