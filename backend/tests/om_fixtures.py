"""Synthetic owner/plan factory for isolated PG tests; no real model or approval."""

from uuid import uuid4

from test_learning_plan_persistence import PLAN, REFS

from app.models.auth import User
from app.models.learning import LearningOperation, LearningUnit
from app.services.learning_plans import save_plan


async def plan_fixture(db):
    user = User(is_guest=True)
    db.add(user)
    await db.flush()
    unit = LearningUnit(user_id=user.id, title="synthetic stack", knowledge_point_id="stack")
    db.add(unit)
    await db.flush()
    operation = LearningOperation(
        user_id=user.id,
        learning_unit_id=unit.id,
        idempotency_key=str(uuid4()),
        request_digest="0" * 64,
        goal="synthetic stack",
        preferred_language="C",
    )
    db.add(operation)
    await db.flush()
    plan = await save_plan(
        db,
        owner_id=user.id,
        unit_id=unit.id,
        operation_id=operation.id,
        plan=PLAN,
        input_snapshot={},
        references=REFS,
        node_ids={"stack"},
        policy_version="hybrid-review-v1",
        policy={},
    )
    return user, unit, operation, plan
