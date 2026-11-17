"""Owner-private bounded record references; bodies remain behind original read guards."""

from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.free_course_answers import FreeCourseAnswerAttempt
from app.models.free_course_quality import FreeCourseFeedback
from app.models.free_course_tutor import FreeCourseTutorTurn
from app.models.free_course_writes import FreeCourseOperation
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository

RecordKind = Literal["attempt", "operation", "feedback", "tutor"]
RecordModel = (
    type[FreeCourseAnswerAttempt]
    | type[FreeCourseOperation]
    | type[FreeCourseFeedback]
    | type[FreeCourseTutorTurn]
)
MODELS: dict[RecordKind, RecordModel] = {
    "attempt": FreeCourseAnswerAttempt,
    "operation": FreeCourseOperation,
    "feedback": FreeCourseFeedback,
    "tutor": FreeCourseTutorTurn,
}


async def read_records(
    db: AsyncSession,
    owner: UUID,
    course: UUID,
    kind: RecordKind,
    *,
    limit: int = 20,
    before_id: UUID | None = None,
) -> dict[str, Any]:
    if not 1 <= limit <= 50 or kind not in MODELS:
        raise SnapshotError("INVALID_API_INPUT")
    await SnapshotRepository(db, owner).get_course(course)
    model = MODELS[kind]
    owned = select(model.id, model.created_at).where(
        model.user_id == owner, model.course_id == course
    )
    query = owned
    if before_id is not None:
        cursor = (await db.execute(owned.where(model.id == before_id))).one_or_none()
        if cursor is None:
            raise SnapshotError("NOT_FOUND")
        query = query.where(tuple_(model.created_at, model.id) < (cursor.created_at, cursor.id))
    rows = (
        await db.execute(query.order_by(model.created_at.desc(), model.id.desc()).limit(limit + 1))
    ).all()
    page = rows[:limit]
    return dict(
        course_id=str(course),
        kind=kind,
        items=[dict(record_id=str(row.id), created_at=row.created_at.isoformat()) for row in page],
        next_before_id=str(page[-1].id) if len(rows) > limit else None,
    )
