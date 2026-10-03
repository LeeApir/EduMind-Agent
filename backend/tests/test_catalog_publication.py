"""Actual PostgreSQL publication, owner reads, withdrawal and immutable versions."""

import asyncio
import os
from uuid import uuid4

import pytest
from catalog_fixtures import approval_fixture, package_fixture
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.database import create_database_engine
from app.models.auth import User
from app.models.learning import GeneratedResource, LearningScene, LearningUnit, utc_now
from app.services.catalog_package import CatalogError, content_digest, validate_package
from app.services.catalog_publication import publish_catalog, revoke_catalog
from app.services.owned_learning import published_resource

TEST_DATABASE_URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="isolated PostgreSQL URL not set")


def test_atomic_approval_provenance_owner_tampering_and_revocation() -> None:
    async def run() -> None:
        engine = create_database_engine(TEST_DATABASE_URL)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sessions() as db:
                package = package_fixture()
                package.manifest["package_id"] = "test-" + uuid4().hex
                package = validate_package(package.payload())
                with pytest.raises(CatalogError):
                    await publish_catalog(db, package, approval={}, trusted_digest="")
                release = await publish_catalog(db, package, approval=approval_fixture(package),
                                                trusted_digest=package.digest)
                owner, other = User(is_guest=True), User(is_guest=True)
                db.add_all([owner, other])
                await db.flush()
                unit = LearningUnit(user_id=owner.id, title="TEST_ONLY", status="ready",
                                    catalog_release_id=release.id)
                db.add(unit)
                await db.flush()
                scene = LearningScene(learning_unit_id=unit.id, scene_key="intro", scene_order=1,
                                      scene_type="catalog", review_status="passed")
                db.add(scene)
                await db.flush()
                content = package.nodes["array"]["explanation"]
                resource = GeneratedResource(user_id=owner.id, learning_unit_id=unit.id,
                    scene_id=scene.id, resource_type="explanation", knowledge_point_id="array",
                    content=content, origin_type="curated", catalog_release_id=release.id,
                    catalog_content_digest=content_digest(content), review_status="passed",
                    published_at=utc_now(), version=1)
                db.add(resource)
                await db.commit()
                assert await published_resource(db, owner.id, resource.id) is resource
                assert await published_resource(db, other.id, resource.id) is None
                same = await publish_catalog(db, package, approval=approval_fixture(package),
                                             trusted_digest=package.digest)
                assert same.id == release.id
                release_id, owner_id, resource_id = release.id, owner.id, resource.id
                resource.content = {"markdown": "UNREVIEWED"}
                with pytest.raises(IntegrityError):
                    await db.flush()
                await db.rollback()
            async with sessions() as db:
                await revoke_catalog(db, release_id)
                await db.commit()
                assert await published_resource(db, owner_id, resource_id) is None
                with pytest.raises(CatalogError):
                    await publish_catalog(db, package, approval=approval_fixture(package),
                                          trusted_digest=package.digest)
        finally:
            await engine.dispose()
    asyncio.run(run())
