"""Characterize current recovery gaps on development data; not desired future semantics."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.om_diagnostic import Capture, valid_review  # noqa:E402
from app.agents.hybrid_resource_review import review_resource, review_once  # noqa:E402
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan  # noqa:E402
from app.services.learning_contract import LearningContractError, SCHEMA, canonical  # noqa:E402
from app.services.learning_review_cases import decide_case  # noqa:E402
from app.services.provider_gateway import StructuredResult, TransportAudit  # noqa:E402
from app.services.unit_material import restore_material  # noqa:E402

BASE = ROOT / "docs/acceptance/phase-1-defect-regression-r01"


def fixture():
    return json.loads((BASE / "cases/plan-consistency--error.json").read_text())


def test_schema_valid_plan_contradiction_is_accepted_without_semantic_repair():
    c = fixture()
    plan = deepcopy(c["material"]["plan"])
    s = c["input_snapshot"]
    inputs = PlanInputs(
        s["metadata"],
        s["references"],
        frozenset(s["node_ids"]),
        s["learner_evidence"],
        c["material"]["reference_context"],
        teaching_context=s.get("teaching_context"),
    )
    props = SCHEMA["$defs"]["plan_generation"]["properties"]
    draft = {k: plan[k] for k in props if k != "reference_ids"}
    draft["reference_ids"] = list(s["references"])
    g = Capture(draft)
    value = asyncio.run(generate_shared_plan(g, inputs, CallWindow()))
    assert len(g.requests) == 1
    assert "返回17" in value["objectives"][0]["text"] and "返回19" in value["goal"]
    assert "19" in value["shared_example"]["steps"][0]["expected_state"]


def test_needs_human_does_not_repair_plan_or_regenerate_resource():
    c = fixture()
    w, _ = restore_material(c["material"])
    w.input_snapshot = deepcopy(c["input_snapshot"])
    before = canonical(w.plan)
    answer = valid_review("resource")
    answer.update(verdict="needs_human", unresolved=["计划17与实际19冲突，需核对。"])
    g = Capture(answer)
    history = asyncio.run(review_resource(g, CallWindow(), w, "explanation"))
    assert len(g.requests) == 1 and len(history) == 1
    assert canonical(w.plan) == before and len(w.candidates()) == 3
    assert history[0]["local_routing"]["verdict"] == "needs_human"


def test_plan_conflict_feedback_enters_resource_corrector_not_a_plan_repairer():
    c = fixture()
    w, _ = restore_material(c["material"])
    w.input_snapshot = deepcopy(c["input_snapshot"])
    before = canonical(w.plan)
    a = valid_review("resource")
    a.update(
        verdict="revise",
        findings=[
            dict(
                category="fact",
                severity="minor",
                anchors=["a1"],
                condition_or_counterexample="计划目标17与正文19不一致。",
                impact="需核对冲突来自计划还是内容。",
            )
        ],
    )
    unresolved = valid_review("resource")
    unresolved.update(verdict="needs_human", unresolved=["计划仍为17，尚未解决。"])

    class Sequence:
        def __init__(self):
            self.values = [a, deepcopy(w.candidates()[0].envelope), unresolved]
            self.requests = []

        async def generate_structured(self, request, *, retry_safe=False):
            assert not retry_safe
            self.requests.append(request)
            return StructuredResult(
                self.values.pop(0),
                "synthetic",
                transport_audit=TransportAudit("1" * 64, "2" * 64, "3" * 64),
            )

    g = Sequence()
    history = asyncio.run(review_resource(g, CallWindow(), w, "explanation"))
    assert len(g.requests) == 3 and len(history) == 2 and not g.values
    assert "Preserve plan conventions" in g.requests[1].prompt.messages[0].content
    correction = json.loads(g.requests[1].prompt.messages[1].content)
    assert correction["plan"]["objectives"] == c["material"]["plan"]["objectives"]
    assert correction["adjustment"]["findings"] == a["findings"]
    assert canonical(w.plan) == before
    assert [c.role for c in w.candidates()] == [
        "explanation"
    ]  # Downstream invalidated.


def test_unit_revise_is_protocol_failure_not_a_global_correction_loop():
    c = fixture()
    w, m = restore_material(c["material"])
    a = valid_review("unit")
    a.update(
        verdict="revise",
        findings=[
            dict(
                category="fact",
                severity="minor",
                anchors=["a1"],
                condition_or_counterexample="需核对计划中的矛盾。",
                impact="无法保证目标一致。",
            )
        ],
    )
    g = Capture(a)
    with pytest.raises(LearningContractError, match="REVIEW_PROTOCOL_INVALID"):
        asyncio.run(
            review_once(
                g,
                CallWindow(),
                binding=w.binding,
                target_digest=m["unit_digest"],
                payload={"unit": m, "reference_context": w.reference_context},
                candidates=w.candidates(),
                scope="unit",
                input_snapshot=c["input_snapshot"],
            )
        )
    assert len(g.requests) == 1


def test_human_service_has_no_revise_decision_and_does_not_touch_db_for_it():
    with pytest.raises(LearningContractError, match="INVALID_REVIEW_DECISION"):
        asyncio.run(
            decide_case(
                None,
                owner_id=uuid4(),
                case_id=uuid4(),
                expected_digest="0" * 64,
                reviewer_id="synthetic",
                identity_source="test",
                verdict="revise",
                reason="Request a content edit, not approval",
                idempotency_key="test-only",
            )
        )


def test_actual_a01_blocked_publication_is_not_a_plan_repair_success():
    path = ROOT / "docs/acceptance/phase-1-generation-mini-r01/results"
    r = json.loads((path / "A01-service-result.json").read_text())
    e = json.loads((path / "A01-evaluation.json").read_text())
    assert r["course_state"] == "awaiting_human" and r["isolated_publication"] is None
    assert "17" in r["plans"][0]["plan"]["objectives"][2]["text"]
    assert r["actual_call_count"] == 8 and not e["corrections"]["observed"]
    assert e["grades"]["full_quality"] == "fail"
