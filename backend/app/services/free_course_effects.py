"""Transaction extension point for free-course replacement evidence (T019)."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def replacement_effects(
    db: AsyncSession,
    owner: UUID,
    cid: UUID,
    before: dict[str, Any],
    after: dict[str, Any],
    changed: set[str],
) -> None:
    # T016 has no exercise/admission writes. T019 implements the shared atomic invalidation here
    # before any public API is opened. Legacy evidence is never altered by this placeholder.
    return None
