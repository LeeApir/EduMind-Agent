"""Apply course approval and exact template identity to every animation access."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import CatalogRelease
from app.models.learning import LearningScene
from app.services.catalog_package import CatalogError
from app.services.catalog_publication import release_package
from app.services.owned_learning import published_scenes, visible_unit


async def animation_target_approved(
    db: AsyncSession, *, owner_id: UUID, unit_id: UUID, scene_id: UUID,
    scene_version: int, template_id: str, template_version: str, lock_release: bool = False,
) -> bool:
    unit = await visible_unit(db, owner_id, unit_id)
    if unit is None:
        return False
    if unit.catalog_release_id is None:
        return True  # Keep the original dynamic publication rules in explicit dynamic mode.
    release = await db.get(CatalogRelease, unit.catalog_release_id,
        with_for_update=lock_release, populate_existing=lock_release)
    if release is None:
        return False
    try:
        package = release_package(release)
    except CatalogError:
        return False
    templates = package.manifest["templates"]
    assert isinstance(templates, dict)
    if (unit.knowledge_point_id != template_id or templates.get(template_id) != template_version):
        return False
    scene = await db.get(LearningScene, scene_id)
    if (scene is None or scene.learning_unit_id != unit.id or scene.version != scene_version
            or scene.generation_status != "complete" or scene.review_status != "passed"):
        return False
    pairs = await published_scenes(db, owner_id, unit_id)
    return {resource.resource_type for current, resource in pairs if current.id == scene_id} == {
        "explanation", "code", "exercise"}
