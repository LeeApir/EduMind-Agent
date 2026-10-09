"""Current template or private DSL qualification shared by claim/lifecycle/media reads."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.product_mode import catalog_only
from app.models.animation import AnimationJob
from app.services.animation_dsl_candidates import DSLCandidateUnavailable
from app.services.catalog_animation_access import animation_target_approved
from app.services.knowledge_graph import KnowledgeGraphRepository


def current_animation_graph() -> KnowledgeGraphRepository:
    return KnowledgeGraphRepository.from_file(
        Path(__file__).resolve().parents[3] / "data/knowledge_graph.yaml"
    )


async def animation_job_approved(
    db: AsyncSession,
    job: AnimationJob,
    *,
    lock: bool = False,
    graph: KnowledgeGraphRepository | None = None,
) -> bool:
    if job.render_kind == "template":
        if job.template_id is None or job.template_version is None or job.candidate_id is not None:
            return False
        return await animation_target_approved(
            db,
            owner_id=job.user_id,
            unit_id=job.learning_unit_id,
            scene_id=job.scene_id,
            scene_version=job.scene_version,
            template_id=job.template_id,
            template_version=job.template_version,
            lock_release=lock,
        )
    if (
        job.render_kind != "dsl"
        or job.candidate_id is None
        or job.template_id is not None
        or job.template_version is not None
        or catalog_only()
    ):
        return False
    try:
        from app.workers.dsl_render import qualification_in_transaction

        await qualification_in_transaction(
            db,
            graph or current_animation_graph(),
            job,
            job.candidate_id,
            lock=lock,
        )
    except (DSLCandidateUnavailable, ValueError):
        return False
    return True
