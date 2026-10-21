"""Independent lane requests and evidence accounting, never actual semantic scores."""
# ruff: noqa: E402

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.separated_diagnostics import (
    IsolatedGateway,
    generator_assessment,
    review_summary,
)  # noqa:E402
from acceptance_support.om_diagnostic import valid_review  # noqa:E402
from acceptance_support.qwen_review_budget import canonical, sha  # noqa:E402
from app.agents.hybrid_resource_review import INSTRUCTION  # noqa:E402
from prepare_separated_diagnostics import (
    capture_review,
    capture_generation,
    fixed_materials,
)  # noqa:E402


@pytest.mark.parametrize("name", list(fixed_materials()))
def test_reviewer_only_exact_fixed_wire(name):
    p = asyncio.run(capture_review(name))
    assert (
        p["mock_requests"] == 1
        and p["generation_calls"] == 0
        and p["provider_calls"] == 0
    )


@pytest.mark.parametrize("name", ["G01", "G02", "G03", "G04"])
def test_independent_generation_never_reviews_or_publishes(name):
    p = asyncio.run(capture_generation(name))
    assert p["mock_requests"] == 4 and p["review_calls"] == 0
    assert p["limits"] == [2048, 4096, 4096, 4096]
    assert p["models"] == ["deepseek-flash"] * 4
    assert p["review_status"] == "not_reviewed" and p["published"] is False
    assert all(t["host"] == t["sni"] == "api.deepseek.com" for t in p["targets"])
    assert all(
        "Independently review"
        not in json.loads(bytes.fromhex(w))["input"][0]["content"]
        for w in p["wire_hex"]
    )


def row(repeat=1):
    fixed = fixed_materials()
    name = "plan-consistency--correct"
    case, request, _ = fixed[name]
    return dict(
        case_id=name,
        repeat=repeat,
        material_sha256=sha(canonical(case)),
        wire_sha256=request["wire_sha256"],
        model_result=valid_review("unit"),
        technical_status="complete",
        technical_error=None,
        semantic_checks=dict(
            required_claims="pass", all_assertions="pass", all_citations="pass"
        ),
        evidence_kind="synthetic",
        audit=dict(
            evaluator="scripted test fixture, NOT actual GPT evaluation",
            assertions=[],
            citations=[],
        ),
    )


def test_same_wire_variance_and_all_unrun_in_denominator():
    rows = [row(1), row(2), row(3)]
    rows[1]["model_result"].update(
        verdict="needs_human", unresolved=["无据声称原文要求17"]
    )
    rows[1]["audit"]["assertions"] = [
        dict(
            json_pointer="/unresolved/0",
            quoted_text="无据声称原文要求17",
            result="contradicted",
            reason="原文要求19，模型错归因。",
        )
    ]
    rows[1]["semantic_checks"]["all_assertions"] = "fail"
    result = review_summary(rows, fixed_materials())
    case = next(c for c in result["cases"] if c["case_id"] == rows[0]["case_id"])
    assert (
        result["planned"] == 36 and result["observed"] == 3 and result["not_run"] == 33
    )
    assert (
        case["verdict_varies"]
        and case["verdict_counts"]["pass"] == 2
        and case["verdict_counts"]["needs_human"] == 1
    )
    assert case["full_audited_matches"] == 2 and case["semantic_failures"] == 1
    assert result["evidence_kind"] == "synthetic"


@pytest.mark.parametrize(
    "change", ["duplicate", "wire", "missing-audit", "false-pass", "mix"]
)
def test_no_combining_changed_inputs_or_hiding_claims(change):
    a = row()
    rows = [a]
    if change == "duplicate":
        rows.append(deepcopy(a))
    elif change == "wire":
        a["wire_sha256"] = "0" * 64
    elif change == "missing-audit":
        a["model_result"].update(verdict="needs_human", unresolved=["new claim"])
    elif change == "false-pass":
        a["model_result"].update(verdict="needs_human", unresolved=["new claim"])
        a["audit"]["assertions"] = [
            dict(
                json_pointer="/unresolved/0",
                quoted_text="new claim",
                result="contradicted",
                reason="unsupported",
            )
        ]
    else:
        b = row(2)
        b["evidence_kind"] = "externally_audited_provider"
        rows.append(b)
    with pytest.raises(ValueError):
        review_summary(rows, fixed_materials())


def test_lane_guard_before_delegate_and_exact_call_ceiling():
    class Gateway:
        count = 0

        async def generate_structured(self, request, **kw):
            self.count += 1

    g = Gateway()
    guard = IsolatedGateway(g, "generation")

    def req(text):
        return SimpleNamespace(
            prompt=SimpleNamespace(messages=[SimpleNamespace(content=text)])
        )

    with pytest.raises(ValueError, match="LANE_OR_RETRY"):
        asyncio.run(guard.generate_structured(req(INSTRUCTION)))
    assert g.count == 0
    for _ in range(4):
        asyncio.run(guard.generate_structured(req("generation only")))
    with pytest.raises(ValueError, match="LANE_CALL_LIMIT"):
        asyncio.run(guard.generate_structured(req("generation only")))
    assert g.count == 4


def test_generator_semantics_not_inferred_from_review_and_needs_evidence():
    draft = dict(
        lane="generation",
        case_id="G01",
        review_calls=0,
        review_status="not_reviewed",
        published=False,
        production_publish_performed=False,
        plan={"objectives": [{"text": "scripted plan"}]},
    )
    keys = [
        "plan_internal_consistency",
        "original_request_fidelity",
        "student_content_facts_and_safety",
        "teaching_delivery",
        "exercise_measurement",
    ]
    checks = {k: dict(status="unassessed", reason="", source_pointers=[]) for k in keys}
    result = generator_assessment(draft, checks)
    assert (
        not result["quality_pass"]
        and result["formal_success"] is None
        and result["reviewer_quality_score"] is None
    )
    checks[keys[0]]["status"] = "pass"
    with pytest.raises(ValueError, match="GENERATION_EVIDENCE_REQUIRED"):
        generator_assessment(draft, checks)
    checks[keys[0]].update(
        reason="offline fixture location only",
        source_pointers=["/plan/objectives/0/text"],
    )
    assert not generator_assessment(draft, checks)["quality_pass"]
    draft["review_calls"] = 1
    with pytest.raises(ValueError, match="NOT_FORMAL_REVIEW"):
        generator_assessment(draft, checks)


def test_failed_transport_or_schema_attempt_is_observed_not_dropped():
    a = row()
    a.update(
        technical_status="failed",
        technical_error="INVALID_SCHEMA",
        model_result={"extra": "invalid result preserved"},
    )
    a["semantic_checks"] = {k: "unassessed" for k in a["semantic_checks"]}
    r = review_summary([a], fixed_materials())
    c = next(c for c in r["cases"] if c["case_id"] == a["case_id"])
    assert r["observed"] == 1 and r["not_run"] == 35
    assert c["technical_failures"] == 1 and c["full_audited_matches"] == 0


@pytest.mark.parametrize("bad", ["missing", "quote", "unsupported"])
def test_every_finding_reference_checked_against_actual_field(bad):
    a = row()
    case, req, _ = fixed_materials()[a["case_id"]]
    anchor = req["anchor_catalog"][0]
    a["model_result"].update(
        verdict="reject",
        findings=[
            dict(
                category="fact",
                severity="major",
                anchors=[anchor["anchor_id"]],
                condition_or_counterexample="scripted test claim",
                impact="scripted impact",
            )
        ],
    )
    a["audit"]["assertions"] = [
        dict(
            json_pointer="/findings/0/" + key,
            quoted_text=text,
            result="supported",
            reason="synthetic annotation",
        )
        for key, text in [
            ("condition_or_counterexample", "scripted test claim"),
            ("impact", "scripted impact"),
        ]
    ]
    field = next(
        c["envelope"]["content"]
        for c in case["material"]["candidates"]
        if c["resource_id"] == anchor["resource_id"]
    )
    for key in anchor["json_pointer"].strip("/").split("/"):
        field = field[int(key)] if isinstance(field, list) else field[key]
    raw = field.encode() if isinstance(field, str) else canonical(field)
    quote = raw[anchor["start_utf8"] : anchor["end_utf8"]].decode()
    citation = dict(
        finding_index=0,
        anchor_id=anchor["anchor_id"],
        quoted_text=quote,
        result="supported",
        reason="synthetic annotation of exact field",
    )
    a["audit"]["citations"] = [citation]
    review_summary([a], fixed_materials())
    if bad == "missing":
        a["audit"]["citations"] = []
    elif bad == "quote":
        citation["quoted_text"] = "neighbor field invented"
    else:
        citation["result"] = "contradicted"
    with pytest.raises(ValueError):
        review_summary([a], fixed_materials())
