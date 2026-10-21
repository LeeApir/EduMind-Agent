"""Offline actual-adapter routing and frozen dev probes; no semantic quality claims."""

# ruff: noqa: E402
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator, ValidationError

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import acceptance_support.plan_admission as support
from acceptance_support.plan_admission import (
    CandidateGateway,
    LaneGateway,
    projected_schema,
)
from app.services.learning_contract import LearningContractError
from app.services.plan_check import SCHEMA
from app.services.provider_gateway import (
    ChatMessage,
    StructuredRequest,
    TextRequest,
    StructuredResult,
    TokenUsage,
    TransportAudit,
)
from prepare_plan_admission import (
    BASE,
    REVIEW,
    GEN,
    PLAN_NAMES,
    budget,
    capture,
    check,
    read,
)

LABELS = read(REVIEW / "labels.json")["labels"]


@pytest.mark.parametrize("name", list(LABELS))
def test_fixed_review_is_one_review_with_unchanged_student_material(name, monkeypatch):
    import socket

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("No DNS allowed")),
    )
    case = read(REVIEW / f"cases/{name}.json")
    before = deepcopy(case)
    output = asyncio.run(capture("fixed_review", case))
    assert case == before and output["calls"] == 1 and not output["semantic_evaluated"]
    wire = output["wires"][0]
    assert wire["role"] == "review" and wire["host"] == wire["sni"] == "www.cbbb.fun"
    assert wire["body"]["model"] == "gpt-6-luna" and wire["body"]["reasoning"] == {
        "effort": "high"
    }
    assert wire["body"]["max_output_tokens"] == 8192
    assert output["formal_success"] is None
    assert "expected_verdict" not in json.dumps(wire["body"])


@pytest.mark.parametrize("name", PLAN_NAMES)
def test_plan_projection_preserves_original_source_and_review_route(name):
    value = asyncio.run(capture("plan_review", read(REVIEW / f"cases/{name}.json")))
    assert value["calls"] == 1 and value["provider_calls"] == 0
    wire = value["wires"][0]
    schema = wire["body"]["text"]["format"]["schema"]
    assert wire["role"] == "review" and schema["properties"]["schema_version"] == {
        "const": "plan-review-result-v1",
        "type": "string",
    }
    assert set(schema["$defs"]) == {"finding"}
    assert "proof" not in schema["$defs"]
    assert schema["additionalProperties"] is False and not value["semantic_evaluated"]


@pytest.mark.parametrize("name", ["G01", "G02", "G03", "G04"])
def test_generation_is_four_generation_only_unpublished_drafts(name):
    output = asyncio.run(capture("generation_draft", read(GEN / f"{name}.json")))
    assert output["calls"] == 4 and output["formal_success"] is None
    assert [w["role"] for w in output["wires"]] == ["generation"] * 4
    assert all(
        w["body"]["reasoning"] == {"effort": "none"} and w["host"] == "api.deepseek.com"
        for w in output["wires"]
    )
    assert [w["body"]["max_output_tokens"] for w in output["wires"]] == [
        2048,
        4096,
        4096,
        4096,
    ]


def test_projection_keeps_original_constraints_and_source_intact():
    original = {"$ref": "#/$defs/model_result", "$defs": deepcopy(SCHEMA["$defs"])}
    before = deepcopy(original)
    wire, meta = projected_schema(original, "plan_check")
    assert original == before and meta["removed_reachable_constraints"] == []
    assert wire["properties"]["coverage"] == {
        **SCHEMA["$defs"]["model_result"]["properties"]["coverage"],
        "properties": {
            **SCHEMA["$defs"]["model_result"]["properties"]["coverage"]["properties"],
            "checked": {
                **SCHEMA["$defs"]["model_result"]["properties"]["coverage"][
                    "properties"
                ]["checked"],
                "items": {
                    **SCHEMA["$defs"]["model_result"]["properties"]["coverage"][
                        "properties"
                    ]["checked"]["items"],
                    "type": "string",
                },
            },
        },
    }
    value = dict(
        schema_version="plan-review-result-v1",
        verdict="pass",
        coverage=dict(checked=[], unchecked=[]),
        findings=[],
        unresolved="wrong type",
    )
    for schema in [original, wire]:
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(value)
    with pytest.raises(ValueError):
        projected_schema(original, "resource_generation")
    with pytest.raises(ValueError, match="PLAN_WRAPPER_CONSTRAINT_CHANGED"):
        projected_schema({**original, "maxProperties": 1}, "plan_check")


@pytest.mark.parametrize(
    "lane,stage,maximum",
    [
        ("fixed_review", "unit_review", 1),
        ("plan_review", "plan_check", 1),
        ("generation_draft", "plan_generation", 4),
    ],
)
def test_lane_limit_counts_failures_and_rejects_cross_lane(lane, stage, maximum):
    class Gateway:
        calls = 0

        async def generate_structured(self, request, *, retry_safe=False):
            self.calls += 1
            raise TimeoutError()

    async def run():
        gateway = Gateway()
        guard = LaneGateway(gateway, lane)
        request = StructuredRequest(TextRequest(messages=()), {}, stage=stage)
        with pytest.raises(LearningContractError):
            await guard.generate_structured(
                replace(request, stage="resource_correction")
            )
        with pytest.raises(LearningContractError):
            await guard.generate_structured(request, retry_safe=True)
        for _ in range(maximum):
            with pytest.raises(TimeoutError):
                await guard.generate_structured(request)
        with pytest.raises(LearningContractError):
            await guard.generate_structured(request)
        assert guard.calls == gateway.calls == maximum

    asyncio.run(run())


@pytest.mark.parametrize(
    "change", ["model", "usage_missing", "negative", "over", "float", "audit", "limit"]
)
def test_exact_candidate_response_and_limit_guard(change):
    result = StructuredResult(
        {},
        "gpt-6-luna",
        usage=TokenUsage(1, 1),
        transport_audit=TransportAudit("1" * 64, "2" * 64, "3" * 64),
    )
    if change == "model":
        result = replace(result, model_id="other-model")
    elif change == "usage_missing":
        result = replace(result, usage=None)
    elif change == "negative":
        result = replace(result, usage=TokenUsage(-1, 1))
    elif change == "over":
        result = replace(result, usage=TokenUsage(1, 8193))
    elif change == "float":
        result = replace(result, usage=TokenUsage(1, 1.2))
    elif change == "audit":
        result = replace(result, transport_audit=None)

    class Gateway:
        async def generate_structured(self, request, *, retry_safe=False):
            return result

    request = StructuredRequest(
        TextRequest(
            messages=(ChatMessage("system", "data"),),
            max_output_tokens=2048 if change == "limit" else 8192,
        ),
        {},
        stage="plan_check",
    )
    with pytest.raises(LearningContractError):
        asyncio.run(CandidateGateway(Gateway()).generate_structured(request))


def test_frozen_budget_labels_and_cli_have_no_live_authority():
    assert check()["materials"] == 20
    data = budget()
    assert data["executable_request_max"] == 59 and data["base_request_cap"] == 60
    assert sum(x["output_max"] for x in data["lanes"]) == 370688
    index = read(BASE / "index.json")
    assert index["order"] == [
        "plan_review",
        "fixed_review",
        "generation_draft",
        "full_pipeline",
    ]
    assert all(
        m.get("independent_signoff") == "pending_Lee_for_this_package"
        for m in index["materials"]
        if m["lane"] != "generation_draft"
    )
    assert read(BASE / "config.json")["production_semantic_verifiers"] == []
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_plan_admission.py"), "run"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "invalid choice" in result.stderr


def test_original_local_schema_still_rejects_if_transport_projection_is_weakened(
    monkeypatch,
):
    from app.services.deepseek_responses import DeepSeekResponsesAdapter
    from app.services.provider_gateway import ProviderError

    original = {"$ref": "#/$defs/model_result", "$defs": deepcopy(SCHEMA["$defs"])}

    async def fake(self, request):
        return StructuredResult(
            dict(
                schema_version="plan-review-result-v1",
                verdict="pass",
                coverage=dict(checked=[], unchecked=[]),
                findings=[],
                unresolved="PRIVATE_SENTINEL",
            ),
            "gpt-6-luna",
        )

    monkeypatch.setattr(
        support, "projected_schema", lambda *args: ({"type": "object"}, {})
    )
    monkeypatch.setattr(DeepSeekResponsesAdapter, "generate_structured", fake)
    adapter = object.__new__(support.CandidateReviewAdapter)
    with pytest.raises(ProviderError) as error:
        asyncio.run(
            adapter.generate_structured(
                StructuredRequest(
                    TextRequest(messages=()), original, stage="plan_check"
                )
            )
        )
    assert "PRIVATE_SENTINEL" not in str(error.value)


def test_frozen_package_cannot_be_prepared_over_itself(tmp_path, monkeypatch):
    import prepare_plan_admission as preparation

    (tmp_path / "manifest.json").write_text("{}")
    monkeypatch.setattr(preparation, "BASE", tmp_path)
    with pytest.raises(ValueError, match="FROZEN_PACKAGE_CANNOT_REWRITE"):
        preparation.prepare()
    assert list(tmp_path.iterdir()) == [tmp_path / "manifest.json"]


def test_evaluation_template_cannot_turn_gpt_or_mock_output_into_human_quality():
    schema = read(BASE / "evaluation.schema.json")
    template = read(BASE / "evaluation-template.json")
    Draft202012Validator(schema).validate(template)
    assert (
        template["scores"]["quality_success"] is None
        and template["automatic_publication_completed"] is None
    )
    for mutation in ["gpt", "mock", "missing_claim_inventory", "formal_denominator"]:
        row = deepcopy(template)
        row.update(
            status="evaluated",
            mode="real",
            run_id="synthetic-run-only",
            package_manifest_sha256="1" * 64,
        )
        row["evaluator"] = dict(
            name="synthetic-test-only", role="independent_human", signed=True
        )
        row["artifacts"] = {key: "1" * 64 for key in row["artifacts"]}
        row["inventories_complete"] = dict(all_assertions=True, all_citations=True)
        Draft202012Validator(schema).validate(row)
        if mutation == "gpt":
            row["evaluator"]["role"] = "gpt_draft"
        elif mutation == "mock":
            row["mode"] = "mock"
        elif mutation == "missing_claim_inventory":
            row["inventories_complete"]["all_assertions"] = False
        else:
            row["eligible_for_T040_denominator"] = True
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(row)


def test_correct_core_rejection_with_false_side_claim_is_not_quality_success():
    schema = read(BASE / "evaluation.schema.json")
    row = read(BASE / "evaluation-template.json")
    row.update(
        status="evaluated",
        mode="real",
        run_id="synthetic-run-only",
        package_manifest_sha256="1" * 64,
    )
    row["evaluator"] = dict(
        name="synthetic-test-only", role="independent_human", signed=True
    )
    row["artifacts"] = {key: "1" * 64 for key in row["artifacts"]}
    row["inventories_complete"] = dict(all_assertions=True, all_citations=True)
    row["scores"].update(
        quality_success=True,
        technical_integrity="pass",
        matches_frozen_label=True,
        incidental_falsehoods="present",
        citation_quality="pass",
        severe_detection="pass",
    )
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(row)
    row["scores"]["quality_success"] = False
    Draft202012Validator(schema).validate(row)
