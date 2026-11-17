"""Mixed-protocol PG/HTTP compatibility. Synthetic reviews; real Provider/network forbidden."""

import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from catalog_fixtures import approval_fixture, package_fixture
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_free_course_answers import practice
from test_free_course_evidence import qualify
from test_free_course_feedback import applied, draft
from test_free_scene_generation import response
from test_hybrid_learning_publication import flow_inputs, sequence
from test_hybrid_resource_review import ReviewGateway
from test_resource_publication import outcome
from test_teaching_node_publication_binding import bound_inputs

from app.agents.review_schema import ReviewVerdict
from app.core.database import create_database_engine
from app.main import app
from app.models.learning import GeneratedResource, LearningOperation, LearningScene, LearningUnit
from app.services.catalog_package import validate_package
from app.services.catalog_publication import publish_catalog, revoke_catalog
from app.services.free_course_quality import Maintenance, local_authority
from app.services.free_course_scheduler import Scheduler
from app.services.hybrid_learning_publication import publish_approved_case, withdraw_publication
from app.services.learning_contract import LearningContractError
from app.services.planned_learning_flow import run_planned_operation
from app.services.resource_publication import ResourcePublicationError, record_reviewed_resource

ROOT = Path(__file__).resolve().parents[2]
SECRET = "TEST_ONLY_T021_IN_MEMORY_SECRET"


def database_url():
    value = os.getenv("EDUMIND_TEST_DATABASE_URL")
    assert value, "Actual isolated PG required"
    url = make_url(value)
    assert (
        url.host == "127.0.0.1"
        and url.port == 15437
        and (url.database or "").startswith("edumind_catalog_p15_t021_")
    )
    return value


@pytest.fixture(scope="module", autouse=True)
def migrate():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT / "backend",
        env={**os.environ, "EDUMIND_DATABASE_URL": database_url()},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr


def dbwork(action):
    async def run():
        engine = create_database_engine(database_url())
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            return await action(sessions)
        finally:
            await engine.dispose()

    return asyncio.run(run())


@pytest.fixture
def compat(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", database_url())
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")

    def forbidden(*args, **kwargs):
        pytest.fail("Real Provider forbidden in T021")

    async def no_http(*args, **kwargs):
        pytest.fail("Outbound HTTP forbidden in combined T021 tests")

    monkeypatch.setattr("app.core.provider_factory.build_default_provider_gateway", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "send", no_http)
    monkeypatch.setattr("app.api.provider_connections.resolve_addresses", lambda *args: ["8.8.8.8"])
    monkeypatch.setenv("EDUMIND_PROVIDER_DEPLOYMENT", "cloud")
    monkeypatch.delenv("EDUMIND_PROVIDER_LOCAL_ALLOWLIST", raising=False)
    monkeypatch.setenv("EDUMIND_CREDENTIAL_ACTIVE_KEY_ID", "t021-test")
    monkeypatch.setenv(
        "EDUMIND_CREDENTIAL_KEYRING_JSON",
        json.dumps({"t021-test": base64.b64encode(b"t" * 32).decode()}),
    )
    owners = []
    clients = []

    def guest():
        client = TestClient(app, base_url="https://testserver")
        r = client.post("/api/auth/guest")
        assert r.status_code == 201
        owner = UUID(r.json()["user"]["id"])
        owners.append(owner)
        clients.append(client)
        return (
            client,
            owner,
            {
                "X-CSRF-Token": r.json()["csrf_token"],
                "Origin": "https://testserver",
                "Idempotency-Key": str(uuid4()),
            },
        )

    from test_profile_behavior_updates import StubGateway

    from app.services.profile_behavior_updates import profile_behavior_gateway_factory
    from app.services.provider_gateway import StructuredResult

    previous = app.dependency_overrides.copy()
    # No-change synthetic behavior callbacks exercise the existing HTTP write path.
    app.dependency_overrides[profile_behavior_gateway_factory] = lambda: lambda: StubGateway(
        StructuredResult(value={"updates": {}}, model_id="TEST_ONLY_t021")
    )
    yield guest
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)
    for client in clients:
        client.close()

    # Historical planned audit is deliberately RESTRICT/append-only. Retain synthetic
    # history in this fresh dedicated database, close clients and revoke their sessions.
    async def clean(sessions):
        async with sessions() as db, db.begin():
            await db.execute(
                text(
                    "UPDATE free_course_capacity SET state='free',user_id=NULL,course_id=NULL,"
                    "operation_id=NULL,epoch=NULL,expires_at=NULL,pending_attempt_id=NULL"
                )
            )
            for owner in owners:
                await db.execute(text("DELETE FROM auth_sessions WHERE user_id=:u"), dict(u=owner))

    dbwork(clean)


def seed_catalog(client, headers):
    async def publish(sessions):
        async with sessions() as db, db.begin():
            package = package_fixture()
            package.manifest["package_id"] = "t021-" + uuid4().hex
            package = validate_package(package.payload())
            release = await publish_catalog(
                db, package, approval=approval_fixture(package), trusted_digest=package.digest
            )
            return release.id

    rid = dbwork(publish)
    created = client.post(
        "/api/catalog/sessions", json=dict(release_id=str(rid), node_id="array"), headers=headers
    )
    assert created.status_code == 201, created.text
    unit = client.get("/api/learning-units/" + created.json()["learning_unit_id"])
    assert unit.status_code == 200
    quiz = next(r for s in unit.json()["scenes"] for r in s["resources"] if r["type"] == "exercise")
    return dict(
        release_id=rid,
        receipt=created.json(),
        unit_id=UUID(created.json()["learning_unit_id"]),
        quiz=quiz,
    )


def seed_legacy(owner):
    async def insert(sessions):
        async with sessions() as db, db.begin():
            unit = LearningUnit(
                user_id=owner,
                title="TEST_ONLY old reviewed legacy",
                status="ready",
                knowledge_point_id="array",
            )
            db.add(unit)
            await db.flush()
            scene = LearningScene(
                learning_unit_id=unit.id,
                scene_key="intro",
                scene_order=1,
                scene_type="explanation",
                generation_status="complete",
                review_status="passed",
            )
            db.add(scene)
            await db.flush()
            resources = []
            for markdown, verdict in [
                ("TEST_ONLY old v1", ReviewVerdict.PASS),
                ("TEST_ONLY rejected", ReviewVerdict.REJECT),
                ("TEST_ONLY old v3", ReviewVerdict.PASS),
            ]:
                resources.append(
                    await record_reviewed_resource(
                        db,
                        owner_id=owner,
                        learning_unit_id=unit.id,
                        scene_id=scene.id,
                        review=outcome(markdown, verdict),
                        knowledge_point_id="array",
                    )
                )
            return unit.id, [r.id for r in resources]

    return dbwork(insert)


def seed_planned(owner, *, bound=True):
    async def create(sessions):
        async with sessions() as db:
            op = LearningOperation(
                user_id=owner,
                idempotency_key=str(uuid4()),
                request_digest="a" * 64,
                goal="synthetic stack",
                preferred_language="C",
            )
            db.add(op)
            await db.commit()
            gateway = ReviewGateway(sequence())
            result = await run_planned_operation(
                db,
                owner_id=owner,
                operation_id=op.id,
                inputs=bound_inputs(owner) if bound else flow_inputs(),
                gateway=gateway,
            )
            assert result["status"] == "completed" and len(gateway.requests) == 9
            quiz = next(c for c in result["material"]["candidates"] if c["role"] == "exercise")
            return dict(
                unit_id=UUID(result["learning_unit_id"]),
                publication_id=(
                    await db.get(LearningUnit, UUID(result["learning_unit_id"]))
                ).current_publication_id,
                quiz_id=UUID(quiz["resource_id"]),
                material=result["material"],
            )

    return dbwork(create)


def seed_free(owner, *, raw=None):
    async def create(sessions):
        return await practice(
            Scheduler(sessions, graph_version="mvp-0.2.0"), sessions, owner, raw=raw
        )

    return dbwork(create)


def capture_history(owner):
    # Keep exact original rows/columns. New derived revisions may append, never replace these facts.
    async def capture(sessions):
        async with sessions() as db:
            names = [
                "learning_units",
                "generated_resources",
                "learning_plan_versions",
                "learning_review_records",
                "learning_publications",
                "learning_review_cases",
                "learning_review_decisions",
                "student_profiles",
                "learning_evidence",
                "node_mastery_revisions",
            ]
            captured = {}
            for name in names:
                rows = (
                    await db.execute(
                        text(
                            f"SELECT id::text,to_jsonb(r)::text FROM {name} r "
                            "WHERE user_id=:u ORDER BY id"
                        ),
                        dict(u=owner),
                    )
                ).all()
                captured[name] = dict(rows)
            captured["learning_scenes"] = dict(
                (
                    await db.execute(
                        text(
                            "SELECT r.id::text,to_jsonb(r)::text FROM learning_scenes r "
                            "JOIN learning_units u ON u.id=r.learning_unit_id "
                            "WHERE u.user_id=:u ORDER BY r.id"
                        ),
                        dict(u=owner),
                    )
                ).all()
            )
            return captured

    return dbwork(capture)


def assert_history(owner, before):
    after = capture_history(owner)
    for name, rows in before.items():
        for rid, value in rows.items():
            assert after[name][rid] == value, f"Changed historical {name} row"
    return hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()


@pytest.mark.parametrize("mode", ["dynamic", "catalog_only"])
def test_mixed_catalog_planned_legacy_free_visibility_owner_and_originals(
    compat, monkeypatch, mode, record_property
):
    client, owner, headers = compat()
    other, _, other_headers = compat()
    catalog = seed_catalog(client, headers)
    legacy_id, legacy_resources = seed_legacy(owner)
    planned = seed_planned(owner)
    cid, manifest, body, _ = seed_free(owner)
    before = capture_history(owner)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", mode)
    for uid, expected in [
        (catalog["unit_id"], 200),
        (legacy_id, 200 if mode == "dynamic" else 404),
        (planned["unit_id"], 200 if mode == "dynamic" else 404),
    ]:
        url = f"/api/learning-units/{uid}"
        assert client.get(url).status_code == expected
        assert other.get(url).status_code == 404
    for rid in [legacy_resources[0], legacy_resources[2]]:
        assert client.get(f"/api/resource/{rid}").status_code == (200 if mode == "dynamic" else 404)
    assert client.get(f"/api/resource/{legacy_resources[1]}").status_code == 404
    free = f"/api/free-courses/{cid}"
    assert client.get(free).status_code == 200 and other.get(free).status_code == 404
    assert client.get(f"/api/learning-units/{cid}").status_code == 404
    assert client.get(f"/api/free-courses/{catalog['unit_id']}").status_code == 404
    assert client.get(f"{free}/versions/3").status_code == 200
    assert other.get(f"{free}/versions/3").status_code == 404
    assert (
        client.post(
            "/api/catalog/sessions",
            json=dict(release_id=str(cid), node_id="array"),
            headers={**headers, "Idempotency-Key": "free-as-release-t021"},
        ).status_code
        == 409
    )
    assert client.post(f"{free}/publish", json={}, headers=headers).status_code == 404
    assert (
        client.post(
            "/api/catalog/publish", json=dict(course_id=str(cid)), headers=headers
        ).status_code
        == 404
    )
    assert other.post(f"{free}/attempts", json=body, headers=other_headers).status_code == (
        404 if mode == "dynamic" else 409
    )
    record_property("historical_rows_sha256", assert_history(owner, before))


def test_free_identity_cannot_satisfy_old_trusted_publication_contract(compat):
    client, owner, headers = compat()
    cid, manifest, body, _ = seed_free(owner)

    async def reject(sessions):
        async with sessions() as db:
            with pytest.raises(ResourcePublicationError):
                await record_reviewed_resource(
                    db,
                    owner_id=owner,
                    learning_unit_id=cid,
                    scene_id=UUID(body["scene_id"]),
                    review=outcome(
                        "TEST_ONLY synthetic pass cannot confer identity", ReviewVerdict.PASS
                    ),
                )
            with pytest.raises(LearningContractError):
                await publish_approved_case(db, owner_id=owner, case_id=cid)
            await db.rollback()
            assert await db.scalar(select(LearningUnit.id).where(LearningUnit.id == cid)) is None

    dbwork(reject)
    assert client.get(f"/api/free-courses/{cid}").json()["endorsement"] == "unendorsed"


@pytest.mark.parametrize(
    "payload",
    [
        "<script>alert(1)</script>",
        "[click](javascript:alert(1))",
        "&#x3c;img src=x onerror=boom&#x3e;",
    ],
)
def test_inert_free_markdown_and_quality_withdrawal_do_not_change_old_reviews(
    compat, payload, record_property
):
    from html.parser import HTMLParser

    client, owner, headers = compat()
    catalog = seed_catalog(client, headers)
    raw = response(["text", "exercise"])
    raw["blocks"][0]["markdown"] = payload
    cid, manifest, body, _ = seed_free(owner, raw=raw)
    baseline = capture_history(owner)
    url = f"/api/free-courses/{cid}/versions/3/scenes/{body['scene_id']}"
    served = client.get(url)
    assert served.status_code == 200 and served.headers["content-type"].startswith(
        "application/json"
    )
    text_block = served.json()["blocks"][0]["markdown"]

    class Tags(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []

        def handle_starttag(self, tag, attrs):
            self.tags.append(tag)

    parser = Tags()
    parser.feed(text_block)
    assert not parser.tags and "<" not in text_block
    if "[click]" in payload:
        assert "\\[click\\]" in text_block
    report = dict(
        **{k: body[k] for k in ["course_version", "scene_id", "scene_version_id"]},
        anchor_id="t",
        exercise_id=None,
        exercise_version_id=None,
        description=payload,
    )
    feedback = client.post(f"/api/free-courses/{cid}/feedback", json=report, headers=headers)
    assert feedback.status_code == 201
    fid = feedback.json()["feedback_id"]
    assert client.get(f"/api/free-courses/{cid}/feedback/{fid}").json()["status"] == "pending"

    async def disable(sessions):
        return await applied(
            Maintenance(sessions, local_authority()), owner, draft(cid, manifest, index=0)
        )

    dbwork(disable)
    assert client.get(url).status_code == 409
    assert client.get(f"/api/free-courses/{cid}/versions/3").status_code == 200
    assert client.get(f"/api/learning-units/{catalog['unit_id']}").status_code == 200
    record_property("old_reviews_preserved_sha256", assert_history(owner, baseline))


def test_legacy_planned_and_catalog_scores_survive_new_defect_and_mode_switch(
    compat, monkeypatch, record_property
):
    client, owner, headers = compat()
    catalog = seed_catalog(client, headers)
    planned = seed_planned(owner)
    catalog_answers = [dict(question_id=f"q{i}", answer=str(i)) for i in range(1, 4)]
    first = client.post(
        "/api/quiz-submissions",
        json=dict(resource_id=catalog["quiz"]["id"], resource_version=1, answers=catalog_answers),
        headers=headers,
    )
    assert first.status_code in (200, 201), first.text
    receipt = first.json()
    assert receipt["score"] == 1

    async def answers_for(sessions):
        async with sessions() as db:
            r = await db.get(GeneratedResource, planned["quiz_id"])
            return [dict(question_id=q["id"], answer=q["answer"]) for q in r.content["items"]]

    planned_answers = dbwork(answers_for)
    planned_key = {**headers, "Idempotency-Key": "planned-signed-answer"}
    scored = client.post(
        "/api/quiz-submissions",
        json=dict(resource_id=str(planned["quiz_id"]), resource_version=1, answers=planned_answers),
        headers=planned_key,
    )
    assert scored.status_code in (200, 201), scored.text
    planned_receipt = scored.json()
    assert planned_receipt["score"] == 1
    cid, manifest, body, _ = seed_free(owner)
    baseline = capture_history(owner)
    aid = client.post(f"/api/free-courses/{cid}/attempts", json=body, headers=headers)
    assert aid.status_code == 201

    async def disable(sessions):
        return await applied(
            Maintenance(sessions, local_authority()), owner, draft(cid, manifest, index=0)
        )

    dbwork(disable)
    for mode in ["catalog_only", "dynamic"]:
        monkeypatch.setenv("EDUMIND_PRODUCT_MODE", mode)
        assert (
            client.get(f"/api/free-courses/{cid}/attempts/{aid.json()['attempt_id']}").json()[
                "reliability"
            ]
            == "withdrawn"
        )
        replay = client.post(
            "/api/quiz-submissions",
            json=dict(
                resource_id=catalog["quiz"]["id"], resource_version=1, answers=catalog_answers
            ),
            headers=headers,
        )
        assert replay.status_code in (200, 201) and replay.json() == receipt
        if mode == "dynamic":
            again = client.post(
                "/api/quiz-submissions",
                json=dict(
                    resource_id=str(planned["quiz_id"]), resource_version=1, answers=planned_answers
                ),
                headers=planned_key,
            )
            assert again.json() == planned_receipt
    record_property("old_score_and_review_bytes_sha256", assert_history(owner, baseline))


def test_publication_and_catalog_revocation_remain_isolated_from_free_course(compat, monkeypatch):
    client, owner, headers = compat()
    other, _, other_headers = compat()
    catalog = seed_catalog(client, headers)
    planned = seed_planned(owner)
    cid, manifest, body, _ = seed_free(owner)

    async def revoke(sessions):
        async with sessions() as db, db.begin():
            await revoke_catalog(db, catalog["release_id"])
            await withdraw_publication(
                db,
                owner_id=owner,
                publication_id=planned["publication_id"],
                reason_code="TEST_ONLY_COMPATIBILITY_WITHDRAWAL",
            )

    dbwork(revoke)
    for mode in ["dynamic", "catalog_only"]:
        monkeypatch.setenv("EDUMIND_PRODUCT_MODE", mode)
        for uid in [catalog["unit_id"], planned["unit_id"]]:
            assert client.get(f"/api/learning-units/{uid}").status_code == 404
        assert client.get(f"/api/resource/{planned['quiz_id']}").status_code == 404
        assert (
            client.get(f"/api/free-courses/{cid}/versions/3/scenes/{body['scene_id']}").status_code
            == 200
        )
        assert other.get(f"/api/free-courses/{cid}").status_code == 404
    denied = client.post(
        "/api/catalog/sessions",
        json=dict(release_id=str(catalog["release_id"]), node_id="array"),
        headers=headers,
    )
    assert denied.status_code == 409


def test_profile_path_replay_effective_mastery_and_explicit_preferences_survive_revocation(
    compat, monkeypatch
):
    client, owner, headers = compat()
    other, _, _ = compat()
    seed_catalog(client, headers)
    original = client.get("/api/profile/me").json()
    changed = client.patch(
        "/api/profile/me",
        json=dict(engineering_preference={"code_first": True}),
        headers={**headers, "If-Match-Profile-Version": str(original["version"])},
    )
    assert changed.status_code == 200
    saved = changed.json()
    assert saved["knowledge_base"] is None
    planned = client.post(
        "/api/path/plan",
        json=dict(target_node_id="array"),
        headers={**headers, "Idempotency-Key": str(uuid4())},
    )
    assert planned.status_code == 201, planned.text
    cid, manifest, body, _ = seed_free(owner)

    async def attest(sessions):
        await qualify(sessions, owner, cid, body)

    dbwork(attest)
    receipt = client.post(f"/api/free-courses/{cid}/attempts", json=body, headers=headers)
    assert receipt.status_code == 201
    mastery = client.get("/api/mastery").json()["items"]
    array = next(i for i in mastery if i["knowledge_node_id"] == "array")
    assert (
        array["score"] == 0.55
        and client.get("/api/path/current", params={"target_node_id": "array"}).json()["is_stale"]
        is True
    )

    async def disable(sessions):
        return await applied(
            Maintenance(sessions, local_authority()), owner, draft(cid, manifest, index=0)
        )

    dbwork(disable)
    for mode in ["catalog_only", "dynamic"]:
        monkeypatch.setenv("EDUMIND_PRODUCT_MODE", mode)
        assert client.get("/api/profile/me").json() == saved
        current = next(
            i
            for i in client.get("/api/mastery").json()["items"]
            if i["knowledge_node_id"] == "array"
        )
        assert current["score"] == 0 and current["status"] == "unseen"
        path = client.get("/api/path/current", params={"target_node_id": "array"}).json()
        assert path["is_stale"] is True
        assert other.get("/api/mastery").json()["items"] == []
        assert other.get("/api/path/current", params={"target_node_id": "array"}).status_code == 404
    raw = client.get(f"/api/free-courses/{cid}/attempts/{receipt.json()['attempt_id']}").json()
    assert raw["mastery_effect"] == "revoked" and raw["answers"] == body["answers"]


def test_model_preferences_owner_keys_and_mode_changes_have_no_provider_or_course_side_effect(
    compat, monkeypatch, caplog
):
    client, owner, headers = compat()
    other, _, other_headers = compat()
    created = client.post(
        "/api/providers/connections",
        headers=headers,
        json=dict(
            provider_type="openai-compatible",
            display_name="TEST_ONLY compatibility",
            base_url="https://provider.test/v1",
            credential_mode="persistent",
            secret=dict(api_key=SECRET),
        ),
    )
    assert created.status_code == 201, created.text
    connection = created.json()["id"]
    route = dict(
        connection_id=connection,
        config_version=1,
        model_id="TEST_ONLY_private_model",
        data_categories=["learning_goal"],
    )
    for profile in ["fast", "default", "quality", "review"]:
        value = client.put(
            f"/api/model-preferences/{profile}",
            json=dict(expected_version=0, route=route, fallbacks=[], consent_accepted=True),
            headers=headers,
        )
        assert value.status_code == 200, value.text
        assert SECRET not in value.text
    saved = client.get("/api/model-preferences").json()
    cid, manifest, body, _ = seed_free(owner)
    for mode in ["catalog_only", "dynamic"]:
        monkeypatch.setenv("EDUMIND_PRODUCT_MODE", mode)
        assert client.get("/api/model-preferences").json() == saved
        assert client.get("/api/providers/connections/" + connection).status_code == 200
        assert other.get("/api/providers/connections/" + connection).status_code == 404
        assert other.get("/api/model-preferences").json() == {"preferences": []}
        denied = other.put(
            "/api/model-preferences/default",
            json=dict(expected_version=0, route=route, fallbacks=[], consent_accepted=True),
            headers=other_headers,
        )
        assert denied.status_code == 404
        assert client.get(f"/api/free-courses/{cid}").json()["endorsement"] == "unendorsed"
    conflict = client.put(
        "/api/model-preferences/default",
        json=dict(expected_version=0, route=route, fallbacks=[], consent_accepted=True),
        headers=headers,
    )
    assert conflict.status_code == 409
    private = (
        client.get("/api/providers/connections").text
        + client.get("/api/model-preferences").text
        + client.get(f"/api/free-courses/{cid}").text
    )
    assert SECRET not in private and SECRET not in caplog.text


def test_old_unbound_planned_reads_but_does_not_requalify_new_score(compat):
    client, owner, headers = compat()
    seed_catalog(client, headers)
    planned = seed_planned(owner, bound=False)
    read = client.get(f"/api/learning-units/{planned['unit_id']}")
    assert read.status_code == 200 and read.json()["binding_status"] == "legacy_unverified"

    async def answers(sessions):
        async with sessions() as db:
            r = await db.get(GeneratedResource, planned["quiz_id"])
            return [dict(question_id=q["id"], answer=q["answer"]) for q in r.content["items"]]

    denied = client.post(
        "/api/quiz-submissions",
        headers=headers,
        json=dict(resource_id=str(planned["quiz_id"]), resource_version=1, answers=dbwork(answers)),
    )
    assert denied.status_code == 409 and denied.json()["code"] == "TEACHING_BINDING_UNVERIFIED"
    cid, manifest, body, _ = seed_free(owner)
    assert client.get(f"/api/learning-units/{planned['unit_id']}").json() == read.json()
    assert client.get(f"/api/free-courses/{cid}").status_code == 200


def test_archived_ledgers_and_approved_contract_bytes_stay_frozen(record_property):
    archives = {}
    for p in sorted((ROOT / "docs/tasks").glob("*.json")):
        relative = p.relative_to(ROOT).as_posix()
        assert p.read_bytes() == subprocess.check_output(
            ["git", "show", f"HEAD:{relative}"], cwd=ROOT
        )
        archives[relative] = hashlib.sha256(p.read_bytes()).hexdigest()
    old = json.loads((ROOT / "docs/tasks/phase-1.json").read_text())
    for tid in ["PHASE-1-T040", "PHASE-1-T041"]:
        assert next(t for t in old["tasks"] if t["id"] == tid)["status"] == "blocked"
    mvp = json.loads((ROOT / "docs/tasks/mvp-0.3.json").read_text())
    assert next(t for t in mvp["tasks"] if t["id"] == "MVP-0.3-T033")["status"] == "blocked"
    records = [
        "docs/ADR/0024-approval-20261021.json",
        "docs/ADR/0025-approval-20261021.json",
        "docs/ADR/0026-approval-20261022.json",
        "docs/design/phase-1.5-ui-approval-20261022.json",
        "docs/ADR/0027-approval-20261022.json",
    ]
    files = 0
    for relative in records:
        record = json.loads((ROOT / relative).read_text())
        assert (
            hashlib.sha256((ROOT / record["proposal_manifest"]).read_bytes()).hexdigest()
            == record["proposal_manifest_sha256"]
        )
        for f in record["files"]:
            assert hashlib.sha256((ROOT / f["path"]).read_bytes()).hexdigest() == f["sha256"]
            files += 1
    assert files == 30
    record_property("archive_sha256", json.dumps(archives, sort_keys=True))
    record_property("frozen_contract_files", files)
