"""Material, transport, provenance and mutation tests; never model-quality assertions."""

import asyncio
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.defect_regression import FAMILIES, VARIANTS  # noqa: E402
from acceptance_support.qwen_review_budget import canonical, sha  # noqa: E402
from app.services.unit_material import restore_material  # noqa: E402
from prepare_defect_regression import BASE, build  # noqa: E402
from prepare_five_hour_materials import capture_case  # noqa: E402


@pytest.fixture(scope="module")
def rebuilt():
    return asyncio.run(build())


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("variant", VARIANTS)
def test_fixed_full_contract_and_actual_review_wire(rebuilt, family, variant):
    name = family + "--" + variant
    case = rebuilt[f"cases/{name}.json"]
    request = rebuilt[f"requests/{name}.json"]
    assert json.loads((BASE / f"cases/{name}.json").read_text()) == case
    assert json.loads((BASE / f"requests/{name}.json").read_text()) == request
    restore_material(case["material"])
    wire = bytes.fromhex(request["wire_hex"])
    body = json.loads(wire)
    payload = json.loads(body["input"][1]["content"])
    assert sha(wire) == request["wire_sha256"]
    assert body["model"] == "gpt-6-luna" and body["reasoning"] == {"effort": "high"}
    assert body["max_output_tokens"] == 8192 and body["temperature"] == 0
    assert request["target"]["url"] == "https://8.8.8.8/v1/responses"
    assert request["target"]["host"] == request["target"]["sni"] == "www.cbbb.fun"
    assert (
        payload["authoritative_teaching_goal"]["user_request"]
        == case["input_snapshot"]["teaching_context"]["original_request"]
    )
    assert (
        not {
            "labels",
            "expected_verdict",
            "required_claims",
            "actual_model_result",
            "variant",
            "family",
        }
        & payload.keys()
    )
    assert case["actual_model_result"] is None
    assert case["input_snapshot"]["learner_evidence"] == {}


def test_complete_matrix_has_no_observed_or_mock_pass_grades(rebuilt):
    index = rebuilt["case-index.json"]
    labels = rebuilt["labels.json"]["labels"]
    assert len(index["cases"]) == 12 and index["actual_results"] is None
    for f in FAMILIES:
        assert {e["variant"] for e in index["cases"] if e["family"] == f} == set(
            VARIANTS
        )
        assert labels[f + "--correct"]["expected_verdict"] == "pass"
        assert labels[f + "--insufficient"]["expected_verdict"] == "needs_human"
        assert labels[f + "--error"]["expected_verdict"] == (
            "reject" if f in ["pointer-scope", "requirement-origin"] else "needs_human"
        )
    assert all(v["actual_result"] is None for v in labels.values())


def test_plan_and_user_attribution_are_distinct_and_numeric_evidence_real(rebuilt):
    case = rebuilt["cases/plan-consistency--error.json"]
    assert "返回19" in case["input_snapshot"]["metadata"]["goal"]
    assert "返回17" in case["material"]["plan"]["objectives"][0]["text"]
    assert (
        "19" in case["material"]["plan"]["shared_example"]["steps"][0]["expected_state"]
    )
    other = rebuilt["cases/requirement-origin--error.json"]
    assert (
        "用户明确要求返回17"
        in other["material"]["candidates"][0]["envelope"]["content"]["markdown"]
    )
    assert (
        "19" in other["input_snapshot"]["metadata"]["goal"]
        and "17" not in other["input_snapshot"]["metadata"]["goal"]
    )
    assert sum([4, 6, 9]) == 19


def test_unknowns_are_explicit_missing_premises_not_definite_opposites(rebuilt):
    texts = {
        f: canonical(rebuilt[f"cases/{f}--insufficient.json"]).decode()
        for f in FAMILIES
    }
    assert "实现未提供" in texts["pointer-scope"]
    assert "指定元素附件未提供" in texts["plan-consistency"]
    assert "没有附件正文" in texts["requirement-origin"]
    assert "原状态表缺失" in texts["assessment-coverage"]


def test_distributed_full_process_question_vs_only_arithmetic(rebuilt):
    def content(v, role):
        return next(
            c["envelope"]["content"]
            for c in rebuilt[f"cases/assessment-coverage--{v}.json"]["material"][
                "candidates"
            ]
            if c["role"] == role
        )

    assert "条件判断前(s,i)" in content("correct", "code")["key_steps"][0]
    assert "(0,0)" not in content("correct", "explanation")["markdown"]
    assert "完整推演" in content("correct", "exercise")["items"][0]["question"]
    assert content("correct", "code") == content("error", "code")
    assert content("correct", "explanation") == content("error", "explanation")
    assert all(
        "s,i" not in x["question"] for x in content("error", "exercise")["items"]
    )


def test_original_input_tamper_fails_before_wire_generation(rebuilt):
    bad = deepcopy(rebuilt["cases/requirement-origin--correct.json"])
    bad["input_snapshot"]["metadata"]["goal"] = "伪造原始要求17"
    with pytest.raises(ValueError):
        asyncio.run(capture_case(bad))
