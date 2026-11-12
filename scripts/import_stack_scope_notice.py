"""Attach the reviewed T148 scope notice to the original C guest's private workspace."""

import asyncio
import json
import os
import sys
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import create_database_engine
from app.services.free_course_snapshots import SnapshotError, SnapshotRepository
from scripts import stack_goal_continuation as continuation
from scripts import stack_goal_selection_trial as selection
from scripts import stack_multiscene_trial as stack
from scripts.head_course_goal import raw_io_audit

SOURCE = stack.PACK / "t148-scope-replay.json"
REASON = "STACK_SCOPE_ARCHIVED"
NOTICE = "当前支持固定容量栈的正常操作及满栈、空栈拒绝。动态扩容暂不支持。"


def reviewed_source():
    reviewed = stack.read(SOURCE)
    replay = continuation.replay_scope(reviewed["review"])
    if reviewed != dict(
        **replay, source_batch=stack.basis.SELECTION_BATCH,
        original_verdict="STACK_SELECTION_EVIDENCE", original_stop=True, new_provider_calls=0,
    ) or replay["outcome"]["plan"] is not None or replay["body_allowed"]:
        raise SnapshotError("STACK_ARCHIVE_BINDING")
    run = stack.read(selection.VAULT / "C" / "run.json")
    origin = dict(course_id=run["course_id"], operation_id=run["operation_id"])
    return UUID(run["approval"]["owner"]), origin, reviewed


async def import_notice(url):
    selection.require_database(url)
    owner, origin, reviewed = reviewed_source()
    policy = {"archived_stack_scope": dict(origin=origin, replay=reviewed)}
    engine = create_database_engine(url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db, db.begin():
            repo = SnapshotRepository(db, owner)
            await repo._owner_lock()
            original_id = UUID(origin["course_id"])
            old = await repo._operation(original_id, UUID(origin["operation_id"]))
            original = await repo.get_course(original_id)
            if (
                old.state != "cancelled" or original["head_version"] is not None
                or original["original_goal"] != reviewed["original_goal"]
            ):
                raise SnapshotError("STACK_ARCHIVE_BINDING")
            created = await repo.create_course(
                reviewed["original_goal"], key="t152:" + reviewed["replay_digest"],
                config={"prompt_version": stack.basis.SELECTION_BATCH}, policy_snapshot=policy,
            )
            course_id, operation_id = UUID(created["course_id"]), UUID(created["operation_id"])
            operation = await repo._operation(course_id, operation_id)
            if operation.state == "queued":
                fence = await repo.acquire_write_fence(course_id, operation_id)
                operation = await repo._fence(course_id, fence)
                operation.state = "awaiting_clarification"
                operation.reason_code = REASON
                operation.clarification_questions = [NOTICE]
                operation.lease_token = operation.lease_expires_at = None
                await db.flush()
            if (
                operation.state != "awaiting_clarification" or operation.reason_code != REASON
                or operation.policy_snapshot != policy or operation.clarification_questions != [NOTICE]
                or (await repo.get_course(course_id))["head_version"] is not None
            ):
                raise SnapshotError("STACK_ARCHIVE_BINDING")
            return dict(**created, state=operation.state, replay_digest=reviewed["replay_digest"])
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.addaudithook(raw_io_audit)
    print(json.dumps(asyncio.run(import_notice(os.environ["EDUMIND_DATABASE_URL"]))))
