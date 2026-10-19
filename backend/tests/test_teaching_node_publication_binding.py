"""Real PG immutable operation/plan/material/publication teaching boundaries."""

import asyncio
import os
from copy import deepcopy
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from test_hybrid_learning_publication import flow_inputs, fresh_operation, sequence
from test_hybrid_resource_review import ReviewGateway

from app.agents.shared_learning_plan import PlanInputs
from app.core.database import create_database_engine
from app.models.learning import LearningOperation, LearningUnit
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.learning_contract import LearningContractError
from app.services.planned_learning_flow import run_planned_operation
from app.services.teaching_binding import select_teaching_context, verify_persisted_teaching
from app.services.unit_material import restore_material

URL = os.getenv("EDUMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="actual isolated PG required")


def bound_inputs(owner, *, mode="target", path=None):
    graph = default_knowledge_graph_repository()
    c = select_teaching_context(
        owner_id=owner,
        target_node_id="stack",
        original_request="synthetic stack",
        mode=mode,
        graph=graph,
        path=path,
    )
    i = flow_inputs()
    return PlanInputs(
        {
            **i.metadata,
            "goal": c["segment_goal"],
            "node_id": c["teaching_node_id"],
            "graph_version": c["graph_version"],
            "graph_digest": c["graph_digest"],
        },
        i.references,
        frozenset(n.id for n in graph.all_nodes()),
        i.learner_evidence,
        i.reference_context,
        teaching_context=c,
    )


def test_context_is_immutable_once_and_v2_material_cannot_be_downgraded():
    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                result = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=bound_inputs(uid),
                    gateway=ReviewGateway(sequence()),
                )
                assert result["status"] == "completed"
                op = await db.get(LearningOperation, oid)
                m = result["material"]
                assert m["teaching_context"] == op.teaching_context
                assert op.teaching_context["teaching_node_id"] == "stack"
                restore_material(m)
                for replacement in ("'{}'::jsonb", "NULL"):
                    with pytest.raises(DBAPIError):
                        async with db.begin_nested():
                            await db.execute(
                                text(
                                    "UPDATE learning_operations SET "
                                    f"teaching_context={replacement} "
                                    "WHERE id=:id"
                                ),
                                {"id": oid},
                            )
                bad = deepcopy(m)
                del bad["teaching_context"]
                with pytest.raises(LearningContractError):
                    restore_material(bad)
                bad = deepcopy(m)
                bad["teaching_context"]["original_request"] = "tampered"
                with pytest.raises(LearningContractError):
                    restore_material(bad)
                assert op.teaching_context["original_request"] == "synthetic stack"
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("change", ["unit", "material", "operation_goal"])
def test_persisted_cross_layer_mismatch_is_not_repaired(change):
    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                result = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=bound_inputs(uid),
                    gateway=ReviewGateway(sequence()),
                )
                m = deepcopy(result["material"])
                if change == "unit":
                    unit = await db.get(LearningUnit, UUID(result["learning_unit_id"]))
                    unit.knowledge_point_id = "array"
                elif change == "operation_goal":
                    op = await db.get(LearningOperation, oid)
                    op.goal = "changed"
                else:
                    m["teaching_context"]["segment_goal"] = "changed"
                with pytest.raises(LearningContractError, match="TEACHING_BINDING_MISMATCH"):
                    await verify_persisted_teaching(
                        db,
                        plan_id=UUID(m["binding"]["plan_id"]),
                        operation_id=oid,
                        material=m,
                        check_graph=True,
                    )
                await db.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("action", ["simpler", "another_example"])
def test_reexplanation_preserves_exact_bound_teaching_context(action):
    from test_hybrid_learning_publication import classroom_reexplanation

    from app.services.hybrid_learning_publication import current_publication
    from app.services.planned_reexplanation import run_planned_reexplanation

    async def run():
        engine = create_database_engine(URL)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                uid, oid = await fresh_operation(db)
                first = await run_planned_operation(
                    db,
                    owner_id=uid,
                    operation_id=oid,
                    inputs=bound_inputs(uid),
                    gateway=ReviewGateway(sequence()),
                )
                unit_id = UUID(first["learning_unit_id"])
                before = deepcopy(first["material"]["teaching_context"])
                parent, _ = await classroom_reexplanation(db, uid, unit_id, action)
                values = sequence()
                if action == "simpler":
                    values = [values[1], values[2], values[4], values[6], values[7]]
                else:
                    values[0] = deepcopy(values[0])
                    values[0]["shared_example"]["input_description"] = "push(30),pop()"
                result = await run_planned_reexplanation(
                    db,
                    owner_id=uid,
                    classroom_operation_id=parent.id,
                    gateway=ReviewGateway(values),
                )
                assert result["status"] == "completed"
                p = await current_publication(db, owner_id=uid, unit_id=unit_id)
                assert p.material["teaching_context"] == before
                old = await current_publication(db, owner_id=uid, unit_id=unit_id, version=1)
                assert old.material["teaching_context"] == before
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_late_node_change_cannot_publish_even_after_model_pass():
    from sqlalchemy import func, select

    from app.models.learning_publication import LearningPublication

    class DriftGateway(ReviewGateway):
        async def generate_structured(self, request, *, retry_safe=False):
            if len(self.values) == 1:
                async with factory() as other:
                    op = await other.get(LearningOperation, operation_id)
                    unit = await other.get(LearningUnit, op.learning_unit_id)
                    unit.knowledge_point_id = "array"
                    await other.commit()
            return await super().generate_structured(request, retry_safe=retry_safe)

    async def run():
        nonlocal factory, operation_id
        engine = create_database_engine(URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as db:
                uid, operation_id = await fresh_operation(db)
                with pytest.raises(LearningContractError, match="TEACHING_BINDING_MISMATCH"):
                    await run_planned_operation(
                        db,
                        owner_id=uid,
                        operation_id=operation_id,
                        inputs=bound_inputs(uid),
                        gateway=DriftGateway(sequence()),
                    )
                op = await db.get(LearningOperation, operation_id, populate_existing=True)
                assert op.status == "failed"
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(LearningPublication)
                        .where(LearningPublication.learning_unit_id == op.learning_unit_id)
                    )
                    == 0
                )
        finally:
            await engine.dispose()

    factory = None
    operation_id = None
    asyncio.run(run())
