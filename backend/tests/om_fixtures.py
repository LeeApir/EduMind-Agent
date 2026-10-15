"""Synthetic owner/plan factory for isolated PG tests; no real model or approval."""

from uuid import uuid4

from test_learning_plan_persistence import PLAN, REFS

from app.models.auth import User
from app.models.learning import LearningOperation, LearningUnit
from app.services.learning_plans import save_plan
from app.services.learning_policy import POLICY


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
        policy=POLICY,
    )
    return user, unit, operation, plan


def material_fixture():
    from uuid import uuid4

    from test_learning_unit_generator import valid_results
    from test_planned_scene_generation import workspace

    from app.services.teaching_actions import assemble_actions
    from app.services.unit_material import unit_material

    w = workspace()
    for role, result in valid_results().items():
        envelope = dict(result.value)
        if role.value == "exercise":
            envelope["content"] = {
                "items": [
                    {
                        "id": f"q{i}",
                        "question": "[判断题] 栈后进先出。仅填 T 或 F（T=正确，F=错误）",
                        "answer": "T",
                        "explanation": "合成格式示例，不是实际课程签核。",
                    }
                    for i in range(1, 4)
                ]
            }
        c = w.stage(role.value, envelope)
        w.disposition(c.role, c.id, "pass")
    scenes = [
        {
            "role": c.role,
            "scene_key": c.role,
            "scene_id": str(uuid4()),
            "scene_version": 1,
            "resource_id": c.id,
            "resource_digest": c.content_digest,
            "dependency_digest": c.dependency_digest,
        }
        for c in w.candidates()
    ]
    return w, unit_material(w, scenes, assemble_actions(w.candidates()))
