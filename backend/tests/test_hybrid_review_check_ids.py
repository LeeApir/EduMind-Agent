"""Regression of exact real r02 prose checklist; no cloud calls or score rewriting."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from test_deepseek_responses import adapter, response
from test_hybrid_resource_review import answer, candidate_workspace

from app.agents.hybrid_resource_review import (
    RESOURCE_CHECKS,
    UNIT_CHECKS,
    review_output_schema,
    route_review,
)
from app.services.provider_gateway import (
    OutputFailureReason,
    ProviderError,
    StructuredRequest,
    TextRequest,
)
from app.services.teaching_actions import anchor_catalog

ROOT = Path(__file__).resolve().parents[2]


def original_r02():
    p = ROOT / "docs/acceptance/phase-1-om-admission-r02/results/correct-unit-01.json"
    return json.loads(p.read_text())["review_result"]


def test_actual_r02_prose_is_rejected_upstream_without_rewriting_old_routing():
    value = original_r02()
    before = deepcopy(value)
    schema = review_output_schema("unit")
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(value)
    old_cases = json.loads(
        (ROOT / "docs/acceptance/phase-1-om-admission-r02/cases.json").read_text()
    )
    route = route_review(value, scope="unit", catalog=old_cases["correct-unit"]["anchors"])
    assert route["verdict"] == "needs_human"
    assert route["reason_codes"] == ["COVERAGE_INCOMPLETE"]
    assert value == before


@pytest.mark.parametrize("scope", ["resource", "unit"])
@pytest.mark.parametrize("bad", ["prose", "translated", "duplicate", "opposite_scope"])
def test_checked_accepts_only_own_exact_unique_ids(scope, bad):
    value = answer("pass", scope)
    required = sorted(RESOURCE_CHECKS if scope == "resource" else UNIT_CHECKS)
    value["coverage"]["checked"] = required
    Draft202012Validator(review_output_schema(scope)).validate(value)
    if bad == "duplicate":
        value["coverage"]["checked"] = required + [required[0]]
    else:
        value["coverage"]["checked"][0] = {
            "prose": "I checked all required items.",
            "translated": "术语",
            "opposite_scope": "terminology" if scope == "resource" else "facts",
        }[bad]
    with pytest.raises(ValidationError):
        Draft202012Validator(review_output_schema(scope)).validate(value)


@pytest.mark.parametrize("scope", ["resource", "unit"])
def test_real_uncertainty_need_not_claim_all_checks_completed(scope):
    required = sorted(RESOURCE_CHECKS if scope == "resource" else UNIT_CHECKS)
    value = answer("needs_human", scope)
    value["coverage"] = {
        "checked": required[:1],
        "unchecked": ["Missing independent premise for the other checks."],
    }
    Draft202012Validator(review_output_schema(scope)).validate(value)
    catalog = anchor_catalog(candidate_workspace().candidates())
    assert route_review(value, scope=scope, catalog=catalog)["verdict"] == "needs_human"


def test_model_cannot_invent_anchor_ids_in_the_outgoing_schema():
    catalog = anchor_catalog(candidate_workspace().candidates())
    ids = [a["anchor_id"] for a in catalog]
    schema = review_output_schema("resource", anchor_ids=ids)
    value = answer("reject")
    value["findings"][0]["anchors"] = [ids[0]]
    Draft202012Validator(schema).validate(value)
    value["findings"][0]["anchors"] = ["invented-anchor"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(value)


def test_actual_adapter_validates_checked_enum_even_if_vendor_ignores_it():
    value = original_r02()
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=response(json.dumps(value)))
    )
    with pytest.raises(ProviderError) as exc:
        asyncio.run(
            adapter(transport).generate_structured(
                StructuredRequest(
                    TextRequest(messages=(), max_output_tokens=2048), review_output_schema("unit")
                )
            )
        )
    assert exc.value.output_failure_reason == OutputFailureReason.STRUCTURED_SCHEMA_MISMATCH
    assert exc.value.schema_keyword == "enum"
