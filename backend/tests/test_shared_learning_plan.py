"""Synthetic gateway exercises local plan generation, not semantic quality."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.services.learning_contract import LearningContractError
from app.services.provider_gateway import ProviderError, ProviderErrorCode, StructuredResult

EXAMPLES = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "docs/acceptance/phase-1-om-redesign/contract-examples.json"
    ).read_text()
)
PLAN = EXAMPLES["plan_record"]["plan"]
DRAFT = EXAMPLES["plan_generation"]


def inputs():
    keys = (
        "node_id",
        "graph_version",
        "graph_digest",
        "profile_version",
        "profile_evidence_digest",
        "goal",
        "code_language",
    )
    return PlanInputs(
        {k: PLAN[k] for k in keys},
        {r["reference_id"]: r for r in PLAN["references"]},
        frozenset({"stack"}),
        {},
    )


class Gateway:
    def __init__(self, value=None, error=None):
        self.value = deepcopy(DRAFT if value is None else value)
        self.error = error
        self.requests = []

    async def generate_structured(self, request, *, retry_safe=False):
        assert retry_safe is False
        self.requests.append(request)
        if self.error:
            raise self.error
        return StructuredResult(self.value, "synthetic")


def test_shared_plan_merges_only_server_metadata():
    g = Gateway()
    w = CallWindow()
    p = asyncio.run(generate_shared_plan(g, inputs(), w))
    assert p == PLAN and w.used == 1
    assert p["profile_version"] is None
    assert g.requests[0].prompt.max_output_tokens == 2048
    assert "graph_digest" not in g.requests[0].json_schema["properties"]


@pytest.mark.parametrize("bad", ["reference", "metadata", "conventions", "scene"])
def test_invalid_plan_has_no_retries_or_fallback(bad):
    value = deepcopy(DRAFT)
    if bad == "reference":
        value["reference_ids"] = ["unknown"]
    if bad == "metadata":
        value["graph_digest"] = "1" * 64
    if bad == "conventions":
        value["conventions"]["capacity"] = None
    if bad == "scene":
        value["scenes"][0]["scene_key"] = "intro"
    g = Gateway(value)
    w = CallWindow()
    with pytest.raises(LearningContractError):
        asyncio.run(generate_shared_plan(g, inputs(), w))
    assert len(g.requests) == w.used == 1


def test_provider_failure_cancellation_and_exhausted_window():
    for error in [
        ProviderError(ProviderErrorCode.TEMPORARILY_UNAVAILABLE),
        asyncio.CancelledError(),
    ]:
        g = Gateway(error=error)
        w = CallWindow()
        with pytest.raises(type(error)):
            asyncio.run(generate_shared_plan(g, inputs(), w))
        assert w.used == len(g.requests) == 1
    for w in [CallWindow(used=20), CallWindow(deadline=0)]:
        g = Gateway()
        with pytest.raises(LearningContractError):
            asyncio.run(generate_shared_plan(g, inputs(), w))
        assert not g.requests
