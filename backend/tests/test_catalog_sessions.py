"""Real database REST, owner isolation, stable replay and revocation checks."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from catalog_fixtures import approval_fixture, package_fixture
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.main import app
from app.models.learning import LearningUnit, StudentProfile
from app.services.catalog_package import validate_package
from app.services.catalog_publication import publish_catalog, revoke_catalog

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="isolated PostgreSQL URL not set")


def test_catalog_rest_has_no_provider_dependency_and_atomic_owner_snapshots(monkeypatch):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.delenv("EDUMIND_PROVIDER_API_KEY", raising=False)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Catalog must not construct a Provider")
    monkeypatch.setattr("app.core.provider_factory.build_default_provider_gateway", forbidden)

    async def setup():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                package = package_fixture()
                package.manifest["package_id"] = "rest-" + uuid4().hex
                package = validate_package(package.payload())
                release = await publish_catalog(db, package, approval=approval_fixture(package),
                                                trusted_digest=package.digest)
                await db.commit()
                return str(release.id)
        finally:
            await engine.dispose()
    release_id = asyncio.run(setup())
    with TestClient(app, base_url="https://testserver") as client:
        assert client.get("/api/catalog").status_code == 401
        guest = client.post("/api/auth/guest", headers={"Origin": "https://testserver"}).json()
        owner_id = UUID(guest["user"]["id"])
        headers = {"Origin": "https://testserver", "X-CSRF-Token": guest["csrf_token"],
                   "Idempotency-Key": "catalog-test-" + uuid4().hex}
        body = {"release_id": release_id, "node_id": "array"}
        assert client.post("/api/catalog/sessions", json=body).status_code == 403
        listing = client.get("/api/catalog").json()
        assert any(r["id"] == release_id and len(r["nodes"]) == 10 for r in listing["releases"])
        assert "answer" not in str(listing)
        first = client.post("/api/catalog/sessions", json=body, headers=headers)
        assert first.status_code == 201, first.text
        receipt = first.json()
        repeat = client.post("/api/catalog/sessions", json=body, headers=headers)
        assert repeat.status_code == 200 and repeat.json() == receipt
        conflict = client.post("/api/catalog/sessions", headers=headers,
                               json={**body, "node_id": "stack"})
        assert conflict.status_code == 409
        unit_path = "/api/learning-units/" + receipt["learning_unit_id"]
        published = client.get(unit_path)
        assert published.status_code == 200
        resources = published.json()["scenes"][0]["resources"]
        assert {r["type"] for r in resources} == {"code", "exercise", "explanation"}
        quiz = next(r for r in resources if r["type"] == "exercise")
        assert all(set(q) == {"id", "question"} for q in quiz["content"]["items"])
        assert client.get("/api/resource/" + quiz["id"]).json() == quiz
        with TestClient(app, base_url="https://testserver") as other:
            other.post("/api/auth/guest", headers={"Origin": "https://testserver"})
            assert other.get(unit_path).status_code == 404
            assert other.get("/api/resource/" + quiz["id"]).status_code == 404

        async def check_and_revoke():
            engine = create_database_engine(URL)
            try:
                async with async_sessionmaker(engine)() as db:
                    assert await db.scalar(select(func.count()).select_from(LearningUnit).where(
                        LearningUnit.user_id == owner_id)) == 1
                    profile = await db.scalar(select(StudentProfile).where(
                        StudentProfile.user_id == owner_id))
                    assert profile.professional_background is None
                    assert profile.knowledge_base is None
                    await revoke_catalog(db, UUID(release_id))
                    await db.commit()
            finally:
                await engine.dispose()
        asyncio.run(check_and_revoke())
        assert client.get(unit_path).status_code == 404
        assert client.post("/api/catalog/sessions", json=body, headers=headers).status_code == 409
        assert not any(r["id"] == release_id for r in client.get("/api/catalog").json()["releases"])
        invalid_headers = {**headers, "Idempotency-Key": "catalog-invalid-" + uuid4().hex}
        assert client.post("/api/catalog/sessions", json={**body, "release_id": str(uuid4())},
                           headers=invalid_headers).status_code == 409
        assert client.post("/api/catalog/sessions", json={**body, "goal": "自由生成"},
                           headers=invalid_headers).status_code == 422
