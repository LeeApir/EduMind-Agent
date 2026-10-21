"""Actual failed/correct material through generation requests; no semantic model oracle."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_hybrid_resource_review import ReviewGateway, answer

from app.agents.hybrid_resource_review import review_resource
from app.agents.learning_resource_prompt import EXERCISE_PROCESS_INSTRUCTION
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import LearningContractError
from app.services.learning_policy import active_policy_digest

ROOT = Path(__file__).resolve().parents[2]


def actual_workspace(name):
    """New offline workspace, original bodies/plan; never mutate stored evidence or scores."""
    if name in {"A01", "A02"}:
        data = json.loads(
            (
                ROOT / "docs/acceptance/phase-1-five-hour-remaining-six-r01/actual-results.json"
            ).read_text()
        )
        case = next(c for c in data["cases"] if c["case_id"] == name)
        actual = case["generated_delivery"]
        plan, snapshot = actual["plans"][0]["plan"], actual["plans"][0]["input_snapshot"]
        binding = deepcopy(case["reviews"][0]["binding"])
        envelopes = [
            dict(
                resource_type=(
                    "explanation"
                    if "markdown" in r["content"]
                    else "exercise"
                    if "items" in r["content"]
                    else "code"
                ),
                prompt_version="learning-resources-v1",
                content=r["content"],
            )
            for r in actual["resources"]
        ]
    else:
        case = json.loads(
            (
                ROOT / f"docs/acceptance/phase-1-five-hour-test-plan-r01/cases/{name}.json"
            ).read_text()
        )
        plan, snapshot = case["material"]["plan"], case["input_snapshot"]
        binding = deepcopy(case["material"]["binding"])
        envelopes = [c["envelope"] for c in case["material"]["candidates"]]
    binding["policy_digest"] = active_policy_digest()
    w = PlannedScenes(
        plan, binding, input_snapshot=snapshot, reference_context=snapshot.get("reference_context")
    )
    for envelope in sorted(
        envelopes, key=lambda e: ["explanation", "code", "exercise"].index(e["resource_type"])
    ):
        c = w.stage(envelope["resource_type"], envelope)
        w.disposition(c.role, c.id, "pass")  # Offline fixture assembly, not model pass.
    return w


@pytest.mark.parametrize("name", ["A01", "U06", "U07"])
def test_actual_generation_keeps_original_goal_and_all_upstream_content(name):
    w = actual_workspace(name)
    old = w.candidates()
    g = ReviewGateway([old[2].envelope])
    asyncio.run(w.generate(g, CallWindow(), "exercise"))
    request = g.requests[0]
    context = json.loads(request.prompt.messages[1].content)
    requirements = context["exercise_requirements"]
    expected = w.teaching_context["original_request"]
    assert requirements["original_request"] == expected
    assert requirements["input_digest"] == w.binding["input_digest"]
    assert context["upstream"] == [c.payload() for c in old[:2]]
    assert EXERCISE_PROCESS_INSTRUCTION in request.prompt.messages[0].content
    assert set(context["upstream"][1]["envelope"]["content"]) >= {"source", "key_steps"}
    # The old A01 error is preserved, not relabeled as a semantic success by a mock.
    assert old[2].envelope == w.candidates()[2].envelope


def test_tampered_original_request_stops_before_model_send():
    w = actual_workspace("A01")
    w.input_snapshot["teaching_context"]["original_request"] = "Only arithmetic is needed"
    g = ReviewGateway([])
    with pytest.raises(LearningContractError, match="GENERATION_INPUT_BINDING_MISMATCH"):
        asyncio.run(w.generate(g, CallWindow(), "exercise"))
    assert not g.requests


def test_exercise_correction_retains_process_requirement_and_exact_goal():
    w = actual_workspace("A01")
    envelope = w.candidates()[2].envelope
    # Script an ordinary fact correction to exercise the existing correction path,
    # not an invented automatic correction for a coverage-only gap.
    g = ReviewGateway([answer("revise"), envelope, answer("pass")])
    asyncio.run(review_resource(g, CallWindow(), w, "exercise"))
    request = g.requests[1]
    assert EXERCISE_PROCESS_INSTRUCTION in request.prompt.messages[0].content
    context = json.loads(request.prompt.messages[1].content)
    assert (
        context["exercise_requirements"]["original_request"]
        == w.teaching_context["original_request"]
    )
    assert context["adjustment"]["candidate"]["envelope"] == envelope
