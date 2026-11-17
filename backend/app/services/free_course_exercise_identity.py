"""Server-derived stable group identity and exact scene-version group identity."""

from uuid import UUID, uuid5

NAMESPACE = UUID("e0705f8a-c1bf-52a0-94a1-b43333585137")


def exercise_identity(owner: UUID, cid: UUID, sid: UUID, sv: UUID, key: str) -> tuple[UUID, UUID]:
    logical = uuid5(NAMESPACE, f"{owner}:{cid}:{sid}:{key}")
    return logical, uuid5(logical, str(sv))
