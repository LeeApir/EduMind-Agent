"""Serialize one owner's derived learning-state snapshots within short transactions."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User


async def lock_learning_owner(db: AsyncSession, owner_id: UUID) -> None:
    """Coordinate profile, mastery, and path commits on the same owner row."""
    found = await db.scalar(select(User.id).where(User.id == owner_id).with_for_update())
    if found is None:
        raise ValueError("Learning owner does not exist.")
