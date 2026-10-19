"""Whole-unit request/routing regressions; scripted replies do not prove model quality."""

import asyncio
import json
from copy import deepcopy

import pytest
from test_hybrid_resource_review import ReviewGateway, answer
from test_review_input import fixture
from test_unit_consistency_review import resource_records

from app.agents.hybrid_resource_review import INSTRUCTION, UNIT_CHECKS, review_once
from app.agents.shared_learning_plan import CallWindow
from app.agents.unit_consistency_review import review_unit
from app.services.learning_contract import LearningContractError


def unit_answer(verdict="pass", gap=None):
    value = answer(verdict, "unit")
    value["coverage"]["checked"] = sorted(UNIT_CHECKS)
    if gap:
        value["unresolved"] = [gap]
    return value


@pytest.mark.parametrize(
    "case,verdict,gap",
    [
        ("trace-complete", "pass", None),
        ("trace-distributed", "pass", None),
        (
            "plan-only-gap",
            "needs_human",
            "学生内容缺明确total状态变化及i=3退出教学，内部轨迹不算交付。",
        ),
        ("assessment-gap", "needs_human", "已教过程但题目仅问最终数值/下标，未要求使用过程知识。"),
    ],
)
def test_unit_gets_full_final_material_original_goals_and_six_checks(case, verdict, gap):
    w, material = fixture(case)

    async def run():
        prior = await resource_records(w)
        g = ReviewGateway([unit_answer(verdict, gap)])
        window = CallWindow()
        result = await review_unit(g, window, material, prior, input_snapshot=w.input_snapshot)
        assert result["state"] == ("auto_ready" if verdict == "pass" else "needs_human")
        sent = json.loads(g.requests[0].prompt.messages[1].content)
        assert set(sent["mandatory_checks"]) == UNIT_CHECKS and len(UNIT_CHECKS) == 6
        assert "objectives" in UNIT_CHECKS
        assert sent["unit"]["candidates"] == material["candidates"]
        assert sent["unit"]["actions"] == material["actions"]
        assert sent["review_responsibilities"]["sibling_content_supplied"]
        assert sent["review_responsibilities"]["resource_role"] is None
        assert (
            sent["authoritative_teaching_goal"]["user_request"]
            == w.input_snapshot["metadata"]["goal"]
        )
        assert "Internal plan traces and action references" in INSTRUCTION
        assert window.used == 1 and len(g.requests) == 1

    asyncio.run(run())


def test_old_five_ids_do_not_become_new_objective_coverage():
    w, material = fixture()
    value = unit_answer()
    value["coverage"]["checked"].remove("objectives")
    before = deepcopy(value)
    record = asyncio.run(
        review_once(
            ReviewGateway([value]),
            CallWindow(),
            binding=w.binding,
            target_digest=material["unit_digest"],
            payload={"unit": material, "reference_context": w.reference_context},
            candidates=w.candidates(),
            scope="unit",
            input_snapshot=w.input_snapshot,
        )
    )
    assert record["local_routing"]["verdict"] == "needs_human"
    assert "COVERAGE_INCOMPLETE" in record["local_routing"]["reason_codes"]
    assert record["result"] == before


@pytest.mark.parametrize("state", ["needs_human", "reject", "masked_unknown"])
def test_unit_pass_never_overrides_resource_unknown_or_rejection(state):
    w, material = fixture()

    async def run():
        prior = await resource_records(w)
        if state == "masked_unknown":
            prior[0]["result"]["unresolved"] = ["原始资源实际未决仍存在。"]
        else:
            prior[0]["local_routing"]["verdict"] = state
        g = ReviewGateway([unit_answer()])
        result = await review_unit(
            g, CallWindow(), material, prior, input_snapshot=w.input_snapshot
        )
        assert result["state"] == ("rejected" if state == "reject" else "needs_human")
        assert len(g.requests) == (0 if state == "reject" else 1)

    asyncio.run(run())


def test_mixed_defect_reject_retains_independent_gap():
    w, material = fixture("assessment-gap", unsafe_code=True)
    value = unit_answer("reject", "三题未考过程，严重越界检出不消除独立测量缺口。")
    from app.services.teaching_actions import anchor_catalog

    value["findings"][0]["anchors"] = [
        next(
            a["anchor_id"] for a in anchor_catalog(w.candidates()) if a["json_pointer"] == "/source"
        )
    ]
    value["findings"][0]["category"] = "code_safety"
    value["findings"][0]["condition_or_counterexample"] = "长度3数组实际访问a[4]，可达越界。"
    value["findings"][0]["impact"] = "发生未定义行为，不能保证任何具体返回数值。"
    g = ReviewGateway([value])
    record = asyncio.run(
        review_once(
            g,
            CallWindow(),
            binding=w.binding,
            target_digest=material["unit_digest"],
            payload={"unit": material, "reference_context": w.reference_context},
            candidates=w.candidates(),
            scope="unit",
            input_snapshot=w.input_snapshot,
        )
    )
    assert record["local_routing"]["verdict"] == "reject"
    assert record["result"] == value and record["result"]["unresolved"]
    assert (
        "not the same storage" in INSTRUCTION
        and "not make a claim that the callee performed it true" in INSTRUCTION
    )


def test_incomplete_unit_cannot_be_reviewed_as_complete():
    w, material = fixture()
    material["candidates"].pop()
    g = ReviewGateway([])
    with pytest.raises(LearningContractError):
        asyncio.run(
            review_once(
                g,
                CallWindow(),
                binding=w.binding,
                target_digest=material["unit_digest"],
                payload={"unit": material},
                candidates=w.candidates()[:2],
                scope="unit",
                input_snapshot=w.input_snapshot,
            )
        )
    assert not g.requests


def prior_policy(monkeypatch):
    """Reconstruct the approved T058 version identifiers/Prompt and five unit IDs."""
    from pathlib import Path

    from app.services.learning_policy import POLICY

    old_checks = UNIT_CHECKS - {"objectives"}
    monkeypatch.setattr("app.agents.hybrid_resource_review.UNIT_CHECKS", old_checks)
    monkeypatch.setattr("test_learning_review_cases.UNIT_CHECKS", old_checks)
    monkeypatch.setattr("test_hybrid_learning_publication.UNIT_CHECKS", old_checks)
    monkeypatch.setattr(
        "app.agents.hybrid_resource_review.REVIEW_V4_PROMPT", "evidence-resource-review-v4.7"
    )
    monkeypatch.setattr(
        "app.agents.hybrid_resource_review.REVIEW_SCOPE_VERSION", "role-learner-review-scope-v4"
    )
    monkeypatch.setattr(
        "app.agents.hybrid_resource_review.INSTRUCTION",
        (
            Path(__file__).resolve().parents[2]
            / "docs/agents/prompts/evidence-resource-review-v4.7.txt"
        ).read_text(),
    )
    monkeypatch.setitem(POLICY, "resource_review_prompt", "evidence-resource-review-v4.7")
    monkeypatch.setitem(POLICY, "review_scope", "role-learner-review-scope-v4")
    monkeypatch.setitem(POLICY, "review_coverage", "fixed-check-ids-v1")


@pytest.mark.skipif(
    not __import__("os").getenv("EDUMIND_TEST_DATABASE_URL"), reason="actual PG required"
)
@pytest.mark.parametrize("approved", [False, True])
def test_prior_policy_pending_and_approved_cases_cannot_publish_under_new_policy(
    monkeypatch, approved
):
    import os

    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from test_learning_review_cases import case_fixture, decision_args

    from app.core.database import create_database_engine
    from app.models.learning_publication import LearningPublication
    from app.models.learning_review_case import LearningReviewDecision
    from app.services.hybrid_learning_publication import publish_approved_case
    from app.services.learning_policy import active_policy_digest
    from app.services.learning_review_cases import decide_case

    async def run():
        engine = create_database_engine(os.environ["EDUMIND_TEST_DATABASE_URL"])
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                with monkeypatch.context() as patch:
                    prior_policy(patch)
                    user, unit, op, plan, case = await case_fixture(db)
                    before = deepcopy(case.payload)
                    old_digest = plan.policy_digest
                    await db.commit()
                    if approved:
                        await decide_case(db, **decision_args(case))
                        await db.commit()
                assert active_policy_digest() != old_digest
                with pytest.raises(LearningContractError):
                    if approved:
                        await publish_approved_case(db, owner_id=user.id, case_id=case.id)
                    else:
                        await decide_case(db, **decision_args(case))
                await db.refresh(case)
                assert case.payload == before
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(LearningPublication)
                        .where(LearningPublication.learning_unit_id == unit.id)
                    )
                    == 0
                )
                assert await db.scalar(
                    select(func.count())
                    .select_from(LearningReviewDecision)
                    .where(LearningReviewDecision.case_id == case.id)
                ) == (1 if approved else 0)
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.mark.skipif(
    not __import__("os").getenv("EDUMIND_TEST_DATABASE_URL"), reason="actual PG required"
)
def test_exact_old_publication_is_readable_after_policy_upgrade(monkeypatch):
    import os
    from uuid import UUID

    from sqlalchemy.ext.asyncio import async_sessionmaker
    from test_hybrid_learning_publication import flow_inputs, fresh_operation, sequence

    from app.core.database import create_database_engine
    from app.services.hybrid_learning_publication import current_publication
    from app.services.planned_learning_flow import run_planned_operation

    async def run():
        engine = create_database_engine(os.environ["EDUMIND_TEST_DATABASE_URL"])
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                with monkeypatch.context() as patch:
                    prior_policy(patch)
                    uid, oid = await fresh_operation(db)
                    result = await run_planned_operation(
                        db,
                        owner_id=uid,
                        operation_id=oid,
                        inputs=flow_inputs(),
                        gateway=ReviewGateway(sequence()),
                    )
                    unit_id = UUID(result["learning_unit_id"])
                    old = await current_publication(db, owner_id=uid, unit_id=unit_id, version=1)
                    old_snapshot = deepcopy(old.material)
                    await db.commit()
                row = await current_publication(db, owner_id=uid, unit_id=unit_id, version=1)
                assert row and row.material == old_snapshot
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_free_list_attribution_and_caller_assignment_are_both_visible_with_exact_anchors():
    from app.services.teaching_actions import anchor_catalog, assemble_actions
    from app.services.unit_material import unit_material

    w, template = fixture(false_claim="free_list会将调用者的head置空。")
    originals = w.candidates()
    code = deepcopy(originals[1].envelope)
    code["content"]["source"] = (
        "#include <stdlib.h>\n"
        "typedef struct Node { struct Node *next; } Node;\n"
        "void free_list(Node *head) { while (head) { Node *next = head->next; "
        "free(head); head = next; } }\n"
        "int main(void) { Node *head = NULL; free_list(head); head = NULL; return 0; }\n"
    )
    c = w.stage("code", code)
    w.disposition("code", c.id, "pass")
    c = w.stage("exercise", originals[2].envelope)
    w.disposition("exercise", c.id, "pass")
    scenes = [
        {
            **s,
            "resource_id": c.id,
            "resource_digest": c.content_digest,
            "dependency_digest": c.dependency_digest,
        }
        for s, c in zip(template["scenes"], w.candidates(), strict=True)
    ]
    material = unit_material(w, scenes, assemble_actions(w.candidates()))
    value = unit_answer("reject")
    anchors = anchor_catalog(w.candidates())
    value["findings"][0].update(
        category="fact",
        severity="minor",
        anchors=[a["anchor_id"] for a in anchors if a["json_pointer"] in ("/markdown", "/source")],
        condition_or_counterexample="free_list仅更新局部形参；调用者head=NULL由main另行执行，与讲解归属矛盾。",
        impact="学生会误解传值参数能修改调用者指针变量；此处并未证明实际释放后使用。",
    )

    async def run():
        g = ReviewGateway([value])
        result = await review_unit(
            g, CallWindow(), material, await resource_records(w), input_snapshot=w.input_snapshot
        )
        sent = json.loads(g.requests[0].prompt.messages[1].content)
        assert result["state"] == "rejected"
        assert sent["unit"]["candidates"] == material["candidates"]
        assert result["review"]["result"]["findings"][0] == value["findings"][0]
        assert "head = NULL" in sent["unit"]["candidates"][1]["envelope"]["content"]["source"]

    asyncio.run(run())
