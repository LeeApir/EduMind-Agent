"""Student delivery is indexed from actual candidates, never inferred from a plan."""

import asyncio
import json
from copy import deepcopy

from om_fixtures import material_fixture
from test_hybrid_resource_review import ReviewGateway, answer

from app.agents.hybrid_resource_review import UNIT_CHECKS, review_once
from app.agents.review_delivery import delivery_manifest
from app.agents.shared_learning_plan import CallWindow


def test_manifest_indexes_all_student_fields_but_not_internal_plan():
    w, material = material_fixture()
    before = deepcopy(material)
    value = delivery_manifest({"unit": material}, w.candidates())
    assert len(value["resources"]) == 3
    assert not value["unindexed_candidate_ids"]
    by_role = {r["role"]: r for r in value["resources"]}
    assert by_role["code"]["teaching_fields"] == ["source", "expected_output", "key_steps"]
    assert "items/*/explanation" in by_role["exercise"]["teaching_fields"]
    assert "feedback" in by_role["exercise"]["availability"]
    assert value["semantic_coverage_assessed_by_this_index"] is False
    for index, resource in enumerate(value["resources"]):
        assert resource["content_pointer"] == f"/unit/candidates/{index}/envelope/content"
    assert material == before


def test_plan_actions_and_animation_placeholders_cannot_become_delivery():
    w, material = material_fixture()
    value = delivery_manifest(
        {
            "plan": material["plan"],
            "actions": material["actions"],
            "animation": {"status": "requested"},
        },
        w.candidates(),
    )
    assert value["resources"] == []
    assert len(value["unindexed_candidate_ids"]) == 3
    assert "not supplied" in value["verified_animation_evidence"]


def test_review_replaces_caller_supplied_delivery_flags_and_routes_pure_gap_to_human():
    async def check():
        w, material = material_fixture()
        value = answer("needs_human", "unit")
        value["coverage"]["checked"] = sorted(UNIT_CHECKS)
        value["unresolved"] = [
            (
                "The displayed lesson lacks explicit states and "
                "termination support; plan trace is internal."
            )
        ]
        gateway = ReviewGateway([value])
        record = await review_once(
            gateway,
            CallWindow(),
            binding=w.binding,
            input_snapshot=w.input_snapshot,
            target_digest=material["unit_digest"],
            payload={
                "unit": material,
                "reference_context": w.reference_context,
                "student_delivery": {"plan_is_visible": True},
            },
            candidates=w.candidates(),
            scope="unit",
        )
        sent = json.loads(gateway.requests[0].prompt.messages[1].content)
        assert "plan_is_visible" not in sent["student_delivery"]
        assert len(sent["student_delivery"]["resources"]) == 3
        assert record["result"] == value and record["result"]["findings"] == []
        assert record["local_routing"]["verdict"] == "needs_human"

    asyncio.run(check())


def test_resource_can_request_supplement_without_a_fabricated_fact_category():
    async def check():
        w, material = material_fixture()
        c = w.candidates()[0]
        value = answer("needs_human")
        value["unresolved"] = [
            "Supplement the promised explicit state transition; other resources were not supplied."
        ]
        record = await review_once(
            ReviewGateway([value]),
            CallWindow(),
            binding=w.binding,
            input_snapshot=w.input_snapshot,
            target_digest=c.content_digest,
            payload={
                "plan": material["plan"],
                "candidate": c.payload(),
                "reference_context": w.reference_context,
            },
            candidates=(c,),
        )
        assert record["local_routing"]["verdict"] == "needs_human"
        assert record["result"]["findings"] == []

    asyncio.run(check())
