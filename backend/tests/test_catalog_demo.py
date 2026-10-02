"""Real preset REST start/refresh/exit, replay, conflicts and withdrawn content."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from catalog_fixtures import approval_fixture, package_fixture
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.main import app
from app.models.classroom import ClassroomSession
from app.services.catalog_package import validate_package
from app.services.catalog_publication import publish_catalog, revoke_catalog

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="isolated PostgreSQL URL not set")


@pytest.mark.parametrize("paused", [False, True])
def test_preset_rest_restores_progress_resource_and_pause_without_model(monkeypatch, paused):
    monkeypatch.setenv("EDUMIND_DATABASE_URL", URL)
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")

    async def setup():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                package = package_fixture()
                package.manifest["package_id"] = "demo-" + uuid4().hex
                package = validate_package(package.payload())
                release = await publish_catalog(db, package, approval=approval_fixture(package),
                                                trusted_digest=package.digest)
                await db.commit()
                return str(release.id), package.demo
        finally:
            await engine.dispose()
    release_id, script = asyncio.run(setup())
    with TestClient(app, base_url="https://testserver") as client:
        guest = client.post("/api/auth/guest").json()
        headers = {"X-CSRF-Token": guest["csrf_token"], "Idempotency-Key": uuid4().hex}
        unit = client.post("/api/catalog/sessions", headers=headers,
            json={"release_id": release_id, "node_id": "array"}).json()["learning_unit_id"]
        classroom_path = f"/api/learning-units/{unit}/classroom"
        assert client.post(classroom_path, headers={**headers,
            "Idempotency-Key": uuid4().hex}).status_code == 201

        async def move_progress():
            engine = create_database_engine(URL)
            try:
                async with async_sessionmaker(engine)() as db:
                    session = await db.scalar(select(ClassroomSession).where(
                        ClassroomSession.learning_unit_id == UUID(unit)))
                    session.scene_progress = 7
                    session.paused = paused
                    await db.commit()
            finally:
                await engine.dispose()
        asyncio.run(move_progress())
        demo_path = f"/api/catalog/learning-units/{unit}/demo"
        initial = client.get(demo_path).json()
        assert initial["script"] == script and initial["preset"] is True
        assert "generation_model_id" not in initial and "review_model_id" not in initial
        body = {"action": "begin", "return_resource_type": "exercise"}
        begin_headers = {**headers, "Idempotency-Key": uuid4().hex,
                         "If-Match-Classroom-Revision": "1"}
        assert client.post(demo_path, json=body).status_code == 403
        wrong_revision = client.post(demo_path, json=body,
            headers={**begin_headers, "If-Match-Classroom-Revision": "9"})
        assert wrong_revision.status_code == 409
        begun = client.post(demo_path, json=body, headers=begin_headers)
        assert begun.status_code == 200, begun.text
        begun = begun.json()
        assert begun["classroom"]["revision"] == 2
        assert begun["classroom"]["paused"] is True
        assert begun["classroom"]["detour"]["kind"] == "catalog_demo"
        assert client.post(demo_path, json=body, headers=begin_headers).json() == begun
        # Fresh read restores active demo after reload; no new command or Provider replay.
        refreshed = client.get(demo_path).json()
        assert refreshed["classroom"] == begun["classroom"]
        assert client.post(demo_path, json=body, headers={**begin_headers,
            "Idempotency-Key": uuid4().hex, "If-Match-Classroom-Revision": "2"}).status_code == 409
        assert client.post(classroom_path + "/controls", json={"action": "resume"}, headers={
            **begin_headers, "Idempotency-Key": uuid4().hex,
            "If-Match-Classroom-Revision": "2"}).status_code == 409
        with TestClient(app, base_url="https://testserver") as other:
            other_guest = other.post("/api/auth/guest").json()
            assert other.get(demo_path).status_code == 404
            assert other.post(demo_path, json=body, headers={**begin_headers,
                "X-CSRF-Token": other_guest["csrf_token"]}).status_code == 404
        exit_headers = {**headers, "Idempotency-Key": uuid4().hex,
                        "If-Match-Classroom-Revision": "2"}
        exited = client.post(demo_path, json={"action": "exit"}, headers=exit_headers)
        assert exited.status_code == 200, exited.text
        exited = exited.json()
        state = exited["classroom"]
        assert state["revision"] == 3 and state["scene_progress"] == 7
        assert state["scene_key"] == "intro" and state["scene_version"] == 1
        assert state["paused"] is paused and "detour" not in state
        assert exited["return_resource_type"] == "exercise"
        assert client.post(demo_path, json={"action": "exit"},
                           headers=exit_headers).json() == exited
        assert client.get(classroom_path).json() == state
        assert client.post(demo_path, json={"action": "exit"}, headers={**begin_headers,
            "If-Match-Classroom-Revision": "3"}).status_code == 409

        async def revoke():
            engine = create_database_engine(URL)
            try:
                async with async_sessionmaker(engine)() as db:
                    await revoke_catalog(db, UUID(release_id))
                    await db.commit()
            finally:
                await engine.dispose()
        asyncio.run(revoke())
        assert client.get(demo_path).status_code == 404
        assert client.get(classroom_path).status_code == 404
        assert client.post(demo_path, json={"action": "exit"},
                           headers=exit_headers).status_code == 404
        assert client.post(classroom_path, headers={**headers,
            "Idempotency-Key": uuid4().hex}).status_code == 404
