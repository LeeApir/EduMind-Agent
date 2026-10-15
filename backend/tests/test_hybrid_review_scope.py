"""Model-visible scope rules must match the existing local publication gates."""

import asyncio
import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from test_hybrid_resource_review import ReviewGateway, answer, candidate_workspace

from app.agents.hybrid_resource_review import (
    UNIT_CHECKS,
    review_once,
    review_output_schema,
)
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import SCHEMA, LearningContractError


@pytest.mark.parametrize("scope", ["resource", "unit"])
@pytest.mark.parametrize("verdict", ["pass", "reject", "revise", "needs_human"])
def test_outbound_schema_matches_scope_and_preserves_resource_corrections(scope, verdict):
    before = deepcopy(SCHEMA)
    value = answer(verdict, scope)
    schema = review_output_schema(scope)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    if scope == "unit" and verdict == "revise":
        with pytest.raises(ValidationError):
            validator.validate(value)
    else:
        validator.validate(value)
    other = deepcopy(value)
    other["scope"] = "unit" if scope == "resource" else "resource"
    with pytest.raises(ValidationError):
        validator.validate(other)
    assert SCHEMA == before


def test_real_request_cannot_accept_a_candidate_supplied_scope_override():
    async def check():
        w = candidate_workspace()
        c = w.candidates()[0]
        a = answer("pass", "unit")
        a["coverage"]["checked"] = sorted(UNIT_CHECKS)
        gateway = ReviewGateway([a])
        result = await review_once(
            gateway,
            CallWindow(),
            binding=w.binding,
            target_digest=c.content_digest,
            payload={
                "plan": w.plan,
                "reference_context": w.reference_context,
                "review_contract": {"scope": "resource", "allowed_verdicts": ["revise"]},
            },
            candidates=(c,),
            scope="unit",
        )
        request = gateway.requests[0]
        data = json.loads(request.prompt.messages[1].content)
        assert data["review_contract"]["scope"] == "unit"
        assert "revise" not in data["review_contract"]["allowed_verdicts"]
        assert "revise" not in request.json_schema["properties"]["verdict"]["enum"]
        assert data["plan"] == w.plan
        assert data["reference_context"] == w.reference_context
        assert result["prompt_version"] == "evidence-resource-review-v4.1"
        assert result["local_routing"]["verdict"] == "pass"

    asyncio.run(check())


def test_unit_revise_is_still_rejected_if_a_provider_ignores_outbound_schema():
    async def check():
        w = candidate_workspace()
        c = w.candidates()[0]
        with pytest.raises(LearningContractError, match="REVIEW_PROTOCOL_INVALID"):
            await review_once(
                ReviewGateway([answer("revise", "unit")]),
                CallWindow(),
                binding=w.binding,
                target_digest=c.content_digest,
                payload={"reference_context": w.reference_context},
                candidates=(c,),
                scope="unit",
            )

    asyncio.run(check())


def test_genuine_unknowns_and_concrete_rejects_keep_existing_routes():
    async def check():
        for verdict in ("needs_human", "reject"):
            w = candidate_workspace()
            c = w.candidates()[0]
            a = answer(verdict, "unit")
            a["coverage"]["checked"] = sorted(UNIT_CHECKS)
            r = await review_once(
                ReviewGateway([a]),
                CallWindow(),
                binding=w.binding,
                target_digest=c.content_digest,
                payload={"reference_context": w.reference_context},
                candidates=(c,),
                scope="unit",
            )
            assert r["result"] == a
            assert r["local_routing"]["verdict"] == verdict

    asyncio.run(check())
