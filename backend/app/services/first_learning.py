"""Prepare an anonymous transient profile and the first temporary explanation stream."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.profile_agent import ProfileAgent
from app.services.provider_gateway import ChatMessage, ProviderGateway, TaskProfile, TextRequest
from app.services.transient_profiles import create_transient_profile


@dataclass(frozen=True, slots=True)
class PreparedFirstLearning:
    """Profile persistence result and the prompt for unreviewed first-screen text."""

    prompt: TextRequest
    profile_degraded: bool


async def prepare_first_learning(
    db: AsyncSession,
    *,
    owner_id: UUID,
    goal: str,
    gateway: ProviderGateway,
) -> PreparedFirstLearning:
    """Persist a conservative profile, never a temporary model response as a resource."""
    persisted = await create_transient_profile(
        db,
        owner_id=owner_id,
        initial_query=goal,
        profile_agent=ProfileAgent(gateway),
    )
    await db.commit()
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
                        "a saved or verified resource."
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
    )
