"""Whole-unit binding and priority, using synthetic review responses."""

import asyncio
from copy import deepcopy

import pytest
from om_fixtures import material_fixture
from test_hybrid_resource_review import ReviewGateway, answer

from app.agents.hybrid_resource_review import UNIT_CHECKS, review_once
from app.agents.shared_learning_plan import CallWindow
from app.agents.unit_consistency_review import review_unit
from app.services.learning_contract import LearningContractError
from app.services.unit_material import restore_material


async def resource_records(w):
    return [
        await review_once(
            ReviewGateway([answer()]),
            CallWindow(),
            binding=w.binding,
            input_snapshot=w.input_snapshot,
            target_digest=c.content_digest,
            payload={
                "plan": w.plan,
                "candidate": c.payload(),
                "reference_context": w.reference_context,
            },
            candidates=(c,),
        )
        for c in w.candidates()
    ]


@pytest.mark.parametrize("changed", ["plan", "candidate", "actions", "scene", "dependency"])
def test_any_material_change_invalidates_unit(changed):
    w, m = material_fixture()
    bad = deepcopy(m)
    if changed == "plan":
        bad["plan"]["goal"] = "changed"
    if changed == "candidate":
        bad["candidates"][0]["envelope"]["content"]["markdown"] = "changed"
    if changed == "actions":
        bad["actions"]["actions"][0]["resource_id"] = "wrong"
    if changed == "scene":
        bad["scenes"][1]["scene_version"] = 2
    if changed == "dependency":
        bad["candidates"][1]["upstream"][0]["content_digest"] = "f" * 64
    with pytest.raises(LearningContractError):
        restore_material(bad)


@pytest.mark.parametrize(
    "verdict,expected",
    [("pass", "auto_ready"), ("needs_human", "needs_human"), ("reject", "rejected")],
)
def test_consistency_result_is_independent_and_no_correction(verdict, expected):
    async def exercise():
        w, m = material_fixture()
        records = await resource_records(w)
        a = answer(verdict, "unit")
        a["coverage"]["checked"] = sorted(UNIT_CHECKS)
        gateway = ReviewGateway([a])
        window = CallWindow()
        result = await review_unit(gateway, window, m, records, input_snapshot=w.input_snapshot)
        assert result["state"] == expected and window.used == 1
        assert result["review"]["target_digest"] == m["unit_digest"]

    asyncio.run(exercise())


def test_existing_reject_has_priority_and_stale_review_fails_without_call():
    async def exercise():
        w, m = material_fixture()
        records = await resource_records(w)
        g = ReviewGateway([])
        records[0]["local_routing"]["verdict"] = "reject"
        assert (await review_unit(g, CallWindow(), m, records, input_snapshot=w.input_snapshot))[
            "state"
        ] == "rejected"
        assert not g.requests
        records[0]["target_digest"] = "f" * 64
        with pytest.raises(LearningContractError):
            await review_unit(g, CallWindow(), m, records, input_snapshot=w.input_snapshot)

    asyncio.run(exercise())


def test_unit_revise_is_protocol_failure_and_uncertainty_stays_human():
    async def exercise():
        w, m = material_fixture()
        records = await resource_records(w)
        a = answer("revise", "unit")
        a["coverage"]["checked"] = sorted(UNIT_CHECKS)
        with pytest.raises(LearningContractError):
            await review_unit(
                ReviewGateway([a]), CallWindow(), m, records, input_snapshot=w.input_snapshot
            )
        records[0]["local_routing"]["verdict"] = "needs_human"
        a = answer("pass", "unit")
        a["coverage"]["checked"] = sorted(UNIT_CHECKS)
        outcome = await review_unit(
            ReviewGateway([a]), CallWindow(), m, records, input_snapshot=w.input_snapshot
        )
        assert outcome["state"] == "needs_human"

    asyncio.run(exercise())
