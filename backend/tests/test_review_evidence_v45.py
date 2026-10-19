"""Prompt/policy version and unchanged output/input contract, not semantic accuracy."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from test_hybrid_resource_review import ReviewGateway, answer
from test_review_input import fixture

from app.agents.hybrid_resource_review import (
    INSTRUCTION,
    REVIEW_V4_PROMPT,
    UNIT_CHECKS,
    review_once,
    review_output_schema,
)
from app.agents.review_evidence import EVIDENCE_INSTRUCTION, REVIEW_PROMPT_VERSION
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import digest
from app.services.learning_policy import POLICY, POLICY_VERSION, active_policy_digest

ROOT = Path(__file__).resolve().parents[2]


def test_general_rule_shared_version_and_original_prompt_prefix():
    old = json.loads(
        (ROOT / "docs/acceptance/phase-1-review-remaining-r01/cases.json").read_text()
    )["reachable-safety:candidate"]
    body = json.loads(bytes.fromhex(old["wire_hex"]))
    assert INSTRUCTION.startswith(body["input"][0]["content"] + "\n" + EVIDENCE_INSTRUCTION)
    assert INSTRUCTION == (ROOT / f"docs/agents/prompts/{REVIEW_PROMPT_VERSION}.txt").read_text()
    assert (
        REVIEW_V4_PROMPT
        == REVIEW_PROMPT_VERSION
        == POLICY["resource_review_prompt"]
        == "evidence-resource-review-v4.8"
    )
    assert (
        EVIDENCE_INSTRUCTION
        == (ROOT / "docs/agents/prompts/evidence-resource-review-v4.5.txt").read_text()
    )
    assert "answer field containing F" not in INSTRUCTION and "a15" not in EVIDENCE_INSTRUCTION
    assert "borrow content from adjacent fields" in EVIDENCE_INSTRUCTION
    prior = deepcopy(POLICY)
    prior["resource_review_prompt"] = "evidence-resource-review-v4.4"
    assert digest("policy", POLICY_VERSION, policy=prior) != active_policy_digest()


@pytest.mark.parametrize("scope", ["resource", "unit"])
def test_outbound_request_uses_new_rules_without_new_fields(scope):
    async def run():
        w, m = fixture("trace-complete")
        result = answer("needs_human", scope)
        if scope == "unit":
            result["coverage"]["checked"] = sorted(UNIT_CHECKS)
        g = ReviewGateway([result])
        record = await review_once(
            g,
            CallWindow(),
            binding=w.binding,
            input_snapshot=w.input_snapshot,
            target_digest=m["unit_digest"] if scope == "unit" else w.candidates()[0].content_digest,
            payload={"unit": m, "reference_context": w.reference_context}
            if scope == "unit"
            else {
                "plan": w.plan,
                "candidate": w.candidates()[0].payload(),
                "reference_context": w.reference_context,
            },
            candidates=w.candidates() if scope == "unit" else (w.candidates()[0],),
            scope=scope,
        )
        request = g.requests[0]
        assert request.prompt.messages[0].content == INSTRUCTION
        assert record["prompt_version"] == "evidence-resource-review-v4.8"
        assert request.json_schema == review_output_schema(
            scope, anchor_ids=[a["anchor_id"] for a in record["anchor_catalog"]]
        )
        assert set(result) == {
            "schema_version",
            "scope",
            "verdict",
            "findings",
            "coverage",
            "unresolved",
        }
        validator = Draft202012Validator(request.json_schema)
        validator.validate(result)
        bad = {**result, "unresolved": [{"reason": "not permitted"}]}
        with pytest.raises(ValidationError):
            validator.validate(bad)
        with pytest.raises(ValidationError):
            validator.validate({**result, "evidence_map": {}})
        assert record["result"] == result

    asyncio.run(run())
