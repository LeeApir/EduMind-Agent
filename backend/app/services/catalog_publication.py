"""Trusted offline publication and immutable content authorization, no model review."""

from copy import deepcopy
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import CatalogRelease
from app.models.learning import GeneratedResource, LearningUnit, utc_now
from app.services.catalog_package import (
    CatalogError,
    CatalogPackage,
    content_digest,
    validate_approval,
    validate_package,
)


async def publish_catalog(
    db: AsyncSession, package: CatalogPackage, *, approval: object, trusted_digest: str
) -> CatalogRelease:
    """Caller is a trusted local publisher, never a student request handler.

    Commits belong to the caller; no partial release is exposed. A revoked release
    cannot be silently reapproved using an old approval file.
    """
    package = validate_package(deepcopy(package.payload()))
    checked = validate_approval(package, approval, trusted_digest=trusted_digest)
    existing = await db.scalar(select(CatalogRelease).where(
        CatalogRelease.package_id == package.manifest["package_id"],
        CatalogRelease.version == package.manifest["version"]))
    if existing is not None:
        if existing.manifest_digest != package.digest or existing.status != "approved":
            raise CatalogError("CATALOG_VERSION_CONFLICT")
        return existing
    release = CatalogRelease(
        package_id=cast(str, package.manifest["package_id"]),
        version=cast(str, package.manifest["version"]), manifest_digest=package.digest,
        graph_version=cast(str, package.manifest["graph_version"]),
        payload=package.payload(), approval=deepcopy(checked), status="approved")
    db.add(release)
    await db.flush()
    return release


async def revoke_catalog(db: AsyncSession, release_id: UUID) -> None:
    release = await db.get(CatalogRelease, release_id, with_for_update=True)
    if release is None:
        raise CatalogError("CATALOG_NOT_FOUND")
    release.status = "revoked"
    release.revoked_at = utc_now()
    await db.flush()


def release_package(release: CatalogRelease) -> CatalogPackage:
    if release.status != "approved":
        raise CatalogError("CATALOG_REVOKED")
    package = validate_package(release.payload)
    if (package.digest != release.manifest_digest
            or package.manifest["package_id"] != release.package_id
            or package.manifest["version"] != release.version
            or package.manifest["graph_version"] != release.graph_version):
        raise CatalogError("CATALOG_INTEGRITY_FAILED")
    validate_approval(package, release.approval, trusted_digest=release.manifest_digest)
    return package


async def approved_release(db: AsyncSession, release_id: UUID) -> CatalogRelease | None:
    release = await db.get(CatalogRelease, release_id)
    if release is None:
        return None
    try:
        release_package(release)
    except (CatalogError, ValueError, TypeError, KeyError):
        return None
    return release


async def resource_provenance_valid(
    db: AsyncSession, resource: GeneratedResource, unit: LearningUnit
) -> bool:
    if resource.origin_type == "generated":
        return unit.catalog_release_id is None
    if (resource.origin_type != "curated" or resource.catalog_release_id is None
            or resource.catalog_release_id != unit.catalog_release_id):
        return False
    release = await approved_release(db, resource.catalog_release_id)
    if release is None:
        return False
    nodes = release_package(release).nodes
    node_id = resource.knowledge_point_id
    if node_id not in nodes or resource.resource_type not in nodes[node_id]:
        return False
    expected = nodes[node_id][resource.resource_type]
    return (content_digest(resource.content) == content_digest(expected)
            == resource.catalog_content_digest)
