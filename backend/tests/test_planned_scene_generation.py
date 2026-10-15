"""Shared context and invalidation, using synthetic resources only."""

import asyncio
from copy import deepcopy

import pytest
from test_learning_unit_generator import valid_results
from test_shared_learning_plan import EXAMPLES, PLAN, Gateway

from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import LearningContractError, digest
from app.services.provider_gateway import ProviderError, ProviderErrorCode


def workspace():
    binding = deepcopy(EXAMPLES["plan_record"]["binding"])
    binding["plan_digest"] = digest("plan", "learning-plan-v1", plan=PLAN)
    return PlannedScenes(PLAN, binding)


def fill(w):
    for role, result in valid_results().items():
        c = w.stage(role.value, dict(result.value))
        w.disposition(role.value, c.id, "pass")
    return w.candidates()


def test_dependencies_use_complete_reviewed_upstream_and_invalidate():
    w = workspace()
    original = fill(w)
    context = w.context("exercise")
    assert [c["resource_id"] for c in context["upstream"]] == [c.id for c in original[:2]]
    assert context["upstream"][1]["envelope"]["content"]["source"]
    replacement = deepcopy(original[0].envelope)
    replacement["content"]["markdown"] = "new example"
    new = w.stage("explanation", replacement)
    assert len(w.candidates()) == 1 and new.id != original[0].id
    with pytest.raises(LearningContractError):
        w.context("code")
    with pytest.raises(LearningContractError):
        w.disposition("explanation", original[0].id, "pass")
    w.disposition("explanation", new.id, "needs_human")
    assert w.context("code")["upstream"][0]["content_digest"] == new.content_digest


def test_candidate_data_is_copied_and_language_checked():
    w = workspace()
    old = fill(w)
    old[0].envelope["content"]["markdown"] = "attacker"
    assert w.candidates()[0].envelope["content"]["markdown"] != "attacker"
    wrong = deepcopy(old[1].envelope)
    wrong["content"]["language"] = "Python"
    with pytest.raises(LearningContractError):
        w.stage("code", wrong)


def test_generation_uses_shared_window_and_preserves_failure():
    w = workspace()
    g = Gateway(value=dict(next(iter(valid_results().values())).value))
    window = CallWindow()
    c = asyncio.run(w.generate(g, window, "explanation"))
    assert window.used == 1 and c.role == "explanation"
    assert g.requests[0].prompt.max_output_tokens == 4096
    w.disposition(c.role, c.id, "pass")
    failing = Gateway(error=ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE))
    with pytest.raises(ProviderError):
        asyncio.run(w.generate(failing, window, "code"))
    assert window.used == 2 and len(w.candidates()) == 1
