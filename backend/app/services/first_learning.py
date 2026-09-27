"""Prepare an anonymous transient profile and the first temporary explanation stream."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profile_agent import ProfileAgent
from app.services.knowledge_graph import KnowledgeGraphRepository
from app.services.path_commands import path_payload
from app.services.path_versions import plan_or_replan_path
from app.services.provider_gateway import ChatMessage, ProviderGateway, TaskProfile, TextRequest
from app.services.transient_profiles import create_transient_profile


@dataclass(frozen=True, slots=True)
class PreparedFirstLearning:
    """Profile persistence result and the prompt for unreviewed first-screen text."""

    prompt: TextRequest
    profile_degraded: bool
    knowledge_node_id: str
    path_snapshot: dict[str, object]


async def prepare_first_learning(
    db: AsyncSession,
    *,
    owner_id: UUID,
    goal: str,
    gateway: ProviderGateway,
    target_node_id: str,
    graph: KnowledgeGraphRepository,
) -> PreparedFirstLearning:
    """Persist a conservative profile, never a temporary model response as a resource."""
    persisted = await create_transient_profile(
        db,
        owner_id=owner_id,
        initial_query=goal,
        profile_agent=ProfileAgent(gateway),
    )
    await db.commit()
    path, _ = await plan_or_replan_path(
        db,
        owner_id=owner_id,
        target_node_id=target_node_id,
        graph=graph,
        trigger_reason="initial_plan",
    )
    node_id = path.current_node_id or target_node_id
    node = graph.get_node(node_id)
    assert node is not None
    profile = persisted.profile
    context = profile.learning_goals or {}
    return PreparedFirstLearning(
        prompt=TextRequest(
            messages=(
                ChatMessage(
                    role="system",
                    content=(
                        "Give the first short Chinese explanation for this data-structure learning "
                        "goal. This is temporary, unreviewed first-screen text; do not claim it is "
                        "a saved or verified resource. "
                        f"Current course node: {node.name}. Teaching context: {node.ai_context}."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=f"Goal: {goal.strip()}\nKnown explicit goals: {context}",
                ),
            ),
            task_profile=TaskProfile.FAST,
        ),
        profile_degraded=persisted.degraded,
        knowledge_node_id=node_id,
        path_snapshot={"id": str(path.id), **path_payload(path, is_stale=False)},
    )
