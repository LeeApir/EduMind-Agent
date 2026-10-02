"""Deployment scope blocks legacy routes before model dependencies are evaluated."""

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.product_mode import catalog_only
from app.core.provider_factory import build_server_provider_gateway
from app.main import app
from app.services.profile_behavior_updates import update_profile_from_summary
from app.services.provider_gateway import ProviderError


@pytest.mark.parametrize("mode", [None, "catalog_only", "invalid", "DYNAMIC"])
def test_default_and_invalid_scope_fail_closed(monkeypatch, mode):
    if mode is None:
        monkeypatch.delenv("EDUMIND_PRODUCT_MODE", raising=False)
    else:
        monkeypatch.setenv("EDUMIND_PRODUCT_MODE", mode)
    assert catalog_only()
    def forbidden(*_args):
        pytest.fail("Adapter must not be constructed")
    with pytest.raises(ProviderError):
        build_server_provider_gateway(forbidden)
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/runtime").json() == {"mode": "catalog_only"}


def test_profile_updates_stop_before_db_or_gateway(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    def forbidden(*_args):
        pytest.fail("No database or Provider update")
    assert asyncio.run(update_profile_from_summary(forbidden, owner_id=uuid4(),
        evidence_id=uuid4(), observed_at=None, summary={"event_type": "quiz_attempt"},
        gateway_factory=forbidden)) == "no_change"


@pytest.mark.skipif(not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="isolated DB required")
def test_direct_http_dynamic_routes_auth_csrf_and_dependency_order(monkeypatch):
    monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
    monkeypatch.setenv("EDUMIND_DATABASE_URL", os.environ["EDUMIND_TEST_DATABASE_URL"])
    from app.api.classroom import provider_gateway
    from app.api.learning_sessions import provider_gateway as learning_gateway
    def forbidden():
        pytest.fail("Blocked route evaluated a model dependency")
    app.dependency_overrides[provider_gateway] = forbidden
    app.dependency_overrides[learning_gateway] = forbidden
    node = str(uuid4())
    routes = [
        ("POST", "/api/learning-sessions"),
        ("POST", f"/api/learning-units/{node}/classroom/messages"),
        ("PATCH", f"/api/learning-units/{node}/classroom/mode"),
        ("POST", f"/api/learning-units/{node}/classroom/scenes/intro/reexplanations"),
        ("POST", f"/api/learning-units/{node}/classroom/debate"),
    ]
    try:
        with TestClient(app, base_url="https://testserver") as client:
            for method, path in routes:
                assert client.request(method, path, json={}).status_code == 401
            csrf = client.post("/api/auth/guest", headers={"Origin": "https://testserver"}).json()
            for method, path in routes:
                assert client.request(method, path, json={}).status_code == 403
                response = client.request(method, path, json={}, headers={
                    "Origin": "https://testserver", "X-CSRF-Token": csrf["csrf_token"]})
                assert response.status_code == 409, response.text
                assert response.json()["code"] == "FEATURE_UNAVAILABLE"
    finally:
        app.dependency_overrides.pop(provider_gateway, None)
        app.dependency_overrides.pop(learning_gateway, None)


@pytest.mark.skipif(not os.getenv("EDUMIND_TEST_DATABASE_URL"), reason="isolated DB required")
def test_catalog_never_relabels_old_generated_resources(monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.database import create_database_engine
    from app.models.auth import User
    from app.models.learning import GeneratedResource, LearningScene, LearningUnit, utc_now
    from app.services.owned_learning import published_resource, published_scenes, visible_unit

    async def run():
        engine = create_database_engine(os.environ["EDUMIND_TEST_DATABASE_URL"])
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                owner = User(is_guest=True)
                db.add(owner)
                await db.flush()
                unit = LearningUnit(user_id=owner.id, status="ready")
                db.add(unit)
                await db.flush()
                scene = LearningScene(learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                                      scene_type="explanation", review_status="passed")
                db.add(scene)
                await db.flush()
                resource = GeneratedResource(user_id=owner.id, learning_unit_id=unit.id,
                    scene_id=scene.id, resource_type="explanation", content={"markdown": "old"},
                    origin_type="generated", review_status="passed", published_at=utc_now())
                db.add(resource)
                await db.commit()
                monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "catalog_only")
                assert await visible_unit(db, owner.id, unit.id) is None
                assert await published_resource(db, owner.id, resource.id) is None
                assert await published_scenes(db, owner.id, unit.id) == []
                monkeypatch.setenv("EDUMIND_PRODUCT_MODE", "dynamic")
                assert await visible_unit(db, owner.id, unit.id) is unit
                assert await published_resource(db, owner.id, resource.id) is resource
                assert len(await published_scenes(db, owner.id, unit.id)) == 1
        finally:
            await engine.dispose()
    asyncio.run(run())
