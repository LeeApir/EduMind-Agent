"""Prepare/check offline development probes only. No run/init/live command or credentials."""

# ruff: noqa: E402
import argparse
import asyncio
from copy import deepcopy
from pathlib import Path
import json
import sys
from unittest.mock import patch
from uuid import UUID, NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.plan_admission import (
    CONFIG,
    LaneGateway,
    offline_router,
)
from acceptance_support.om_diagnostic import valid_review
from acceptance_support.qwen_review_budget import sha
from app.agents.hybrid_resource_review import review_once
from app.agents.plan_check import CHECKS, inspect_plan
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.models.learning_plan import LearningPlanVersion
from app.services.learning_contract import digest
from app.services.learning_policy import POLICY, POLICY_VERSION, active_policy_digest
from app.services.unit_material import restore_material
from prepare_five_hour_materials import contents, draft_for

BASE = ROOT / "docs/acceptance/phase-1-plan-admission-preparation-r01"
REVIEW = ROOT / "docs/acceptance/phase-1-defect-regression-r01"
GEN = ROOT / "docs/acceptance/phase-1-separated-diagnostics-r01/inputs"
PLAN_NAMES = [
    "plan-consistency--correct",
    "plan-consistency--error",
    "plan-consistency--insufficient",
    "requirement-origin--error",
]


def read(path):
    return json.loads(path.read_text())


def plan_row(case):
    b = case["material"]["binding"]
    value = case["material"]["plan"]
    s = case["input_snapshot"]
    refs = s["references"]
    return LearningPlanVersion(
        id=UUID(b["plan_id"]),
        user_id=UUID(b["owner_id"]),
        learning_unit_id=UUID(b["unit_id"]),
        origin_operation_id=UUID(b["operation_id"]),
        version=b["plan_version"],
        schema_version="learning-plan-v1",
        plan_json=value,
        input_snapshot=s,
        references_snapshot=refs,
        policy_snapshot=deepcopy(POLICY),
        plan_digest=digest("plan", "learning-plan-v1", plan=value),
        input_digest=digest("input", "learning-input-v1", snapshot=s),
        references_digest=digest(
            "references", "learning-references-v1", references=refs
        ),
        policy_version=POLICY_VERSION,
        policy_digest=active_policy_digest(),
    )


async def capture(lane, case):
    if lane == "fixed_review":
        workspace, material = restore_material(case["material"])
        gateway, wires = offline_router([valid_review("unit")])
        guard = LaneGateway(gateway, lane)
        await review_once(
            guard,
            CallWindow(),
            binding=material["binding"],
            target_digest=material["unit_digest"],
            payload=dict(
                unit=material, reference_context=material["reference_context"]
            ),
            candidates=workspace.candidates(),
            scope="unit",
            input_snapshot=case["input_snapshot"],
        )
    elif lane == "plan_review":
        result = dict(
            schema_version="plan-review-result-v1",
            verdict="pass",
            coverage=dict(checked=CHECKS, unchecked=[]),
            findings=[],
            unresolved=[],
        )
        gateway, wires = offline_router([result])
        guard = LaneGateway(gateway, lane)
        row = plan_row(case)
        await inspect_plan(guard, CallWindow(), row, row.origin_operation_id)
    elif lane == "generation_draft":
        s = case["input_snapshot"]
        inputs = PlanInputs(
            s["metadata"],
            s["references"],
            frozenset(s["node_ids"]),
            s["learner_evidence"],
            case["reference_context"],
            teaching_context=s.get("teaching_context"),
        )
        values = [
            draft_for(inputs, "complete"),
            *[
                dict(
                    resource_type=role,
                    prompt_version="learning-resources-v1",
                    content=content,
                )
                for role, content in contents("complete").items()
            ],
        ]
        gateway, wires = offline_router(values)
        guard = LaneGateway(gateway, lane)
        window = CallWindow()
        plan = await generate_shared_plan(guard, inputs, window)

        def identity(key):
            return str(
                uuid5(NAMESPACE_URL, "edumind:plan-admission:mock:" + case["id"] + key)
            )

        b = {
            key: identity(key)
            for key in ("owner_id", "unit_id", "operation_id", "plan_id")
        }
        b.update(
            plan_version=1,
            plan_digest=digest("plan", "learning-plan-v1", plan=plan),
            input_digest=digest("input", "learning-input-v1", snapshot=s),
            references_digest=digest(
                "references", "learning-references-v1", references=inputs.references
            ),
            policy_version=POLICY_VERSION,
            policy_digest=active_policy_digest(),
        )
        workspace = PlannedScenes(
            plan, b, reference_context=inputs.reference_context, input_snapshot=s
        )
        with patch(
            "app.agents.planned_scene_generation.uuid4",
            side_effect=[UUID(identity("candidate" + str(i))) for i in range(3)],
        ):
            for role in ("explanation", "code", "exercise"):
                c = await workspace.generate(guard, window, role)
                # Draft-only bridge; no review record, DB, decision or publication.
                workspace.disposition(role, c.id, "needs_human")
    else:
        raise ValueError("UNKNOWN_LANE")
    if any(
        (
            "expected_verdict" in json.dumps(w["body"])
            or "forbidden_claims" in json.dumps(w["body"])
        )
        for w in wires
    ):
        raise ValueError("LABEL_LEAKED")
    return dict(
        lane=lane,
        calls=guard.calls,
        provider_calls=0,
        semantic_evaluated=False,
        formal_success=None,
        wires=wires,
    )


def budget():
    return dict(
        real_requests_authorized=0,
        base_request_cap=60,
        executable_request_max=59,
        closed_unused_slots=1,
        fees="unlimited by user policy; not authorization",
        input_tokens_max=None,
        output_tokens_max=370688,
        deadline_seconds_proposed=18000,
        operation_deadline_seconds=180,
        per_request_seconds=60,
        automatic_retries=0,
        fallbacks=0,
        lanes=[
            dict(
                lane="fixed_review",
                materials=12,
                repeats=8,
                calls=20,
                output_max=163840,
            ),
            dict(lane="generation_draft", materials=4, calls=16, output_max=57344),
            dict(lane="plan_review", materials=4, calls=4, output_max=32768),
            dict(
                lane="full_pipeline",
                materials=1,
                mapping=0,
                rebuild=0,
                normal_calls=9,
                calls=19,
                output_max=116736,
            ),
        ],
    )


def prepare():
    if (BASE / "manifest.json").exists():
        raise ValueError("FROZEN_PACKAGE_CANNOT_REWRITE")
    BASE.mkdir(parents=True, exist_ok=True)
    labels = read(REVIEW / "labels.json")["labels"]
    index = []
    for name, label in labels.items():
        case = read(REVIEW / f"cases/{name}.json")
        path = BASE / f"materials/review/{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n")
        value = asyncio.run(capture("fixed_review", case))
        p = BASE / f"captures/review/{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        index.append(
            dict(
                id=name,
                lane="fixed_review",
                material=str(path.relative_to(ROOT)),
                sha256=sha(path.read_bytes()),
                prelabel=label,
                independent_signoff="pending_Lee_for_this_package",
                use="development_calibration_not_generalization",
            )
        )
    expected = [
        (["pass"], "accept_plan", "原始19、轨迹19与目标一致，不增背景目标/动画。"),
        (
            ["issue", "needs_human", "reject"],
            "needs_human_or_reject",
            "计划目标17与原文/轨迹19冲突，必须指出具体字段，不冒称原文17。",
        ),
        (["needs_human"], "needs_human", "指定元素缺失，不能核验19或宣称确定非19。"),
        (
            ["issue", "needs_human", "reject"],
            "needs_human_or_reject",
            "仅计划追加17；不能归给要求19的用户，区分原文与计划。",
        ),
    ]
    for i, name in enumerate(PLAN_NAMES, 1):
        case = read(REVIEW / f"cases/{name}.json")
        row = dict(
            id=f"P{i:02}",
            source_development_case=name,
            input_snapshot=case["input_snapshot"],
            plan=case["material"]["plan"],
            binding=case["material"]["binding"],
        )
        path = BASE / f"materials/plan/P{i:02}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n")
        value = asyncio.run(capture("plan_review", case))
        p = BASE / f"captures/plan/P{i:02}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        index.append(
            dict(
                id=f"P{i:02}",
                lane="plan_review",
                material=str(path.relative_to(ROOT)),
                sha256=sha(path.read_bytes()),
                prelabel=dict(
                    model_verdicts=expected[i - 1][0],
                    server_route=expected[i - 1][1],
                    evidence_requirement=expected[i - 1][2],
                    all_assertions_and_citations_required=True,
                ),
                independent_signoff="pending_Lee_for_this_package",
                author="Codex development prelabel, not independent truth",
            )
        )
    for name in ["G01", "G02", "G03", "G04"]:
        case = read(GEN / f"{name}.json")
        path = BASE / f"materials/generation/{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n")
        value = asyncio.run(capture("generation_draft", case))
        p = BASE / f"captures/generation/{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
        index.append(
            dict(
                id=name,
                lane="generation_draft",
                material=str(path.relative_to(ROOT)),
                sha256=sha(path.read_bytes()),
                labels="actual plan/content require independent human assessment; no expected model answer",
                use="development_input_previously_exposed_not_holdout",
            )
        )
    for name, value in [
        (
            "index.json",
            dict(
                real_requests_authorized=0,
                materials=index,
                full_pipeline_input="G03",
                repeat_review_ids=[
                    n for n in labels if not n.endswith("--insufficient")
                ],
                order=[
                    "plan_review",
                    "fixed_review",
                    "generation_draft",
                    "full_pipeline",
                ],
            ),
        ),
        ("budget.json", budget()),
        (
            "config.json",
            dict(
                candidate=CONFIG,
                output_caps=dict(mapping=512, plan=2048, resource=4096, review=8192),
                server_stage_routing="learning-stage-v1",
                policy_digest=active_policy_digest(),
                production_semantic_verifiers=[],
                plan_projection="plan-check-string-types-reachable-defs-v1",
                resource_projection="luna-review-explicit-string-types-reachable-defs-v1",
                single_candidate_only=True,
                real_provider_compatibility="not proven for new plan schema; first P01 is compatibility and positive control",
            ),
        ),
    ]:
        (BASE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def check():
    from jsonschema import Draft202012Validator

    schema = read(BASE / "evaluation.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(read(BASE / "evaluation-template.json"))
    config = read(BASE / "config.json")
    assert (
        config["candidate"] == CONFIG
        and config["policy_digest"] == active_policy_digest()
    )
    data = read(BASE / "budget.json")
    assert data == budget()
    assert sum(x["calls"] for x in data["lanes"]) == 59
    assert sum(x["output_max"] for x in data["lanes"]) == 370688
    index = read(BASE / "index.json")
    assert len(index["materials"]) == 20 and len(index["repeat_review_ids"]) == 8
    for item in index["materials"]:
        path = ROOT / item["material"]
        assert sha(path.read_bytes()) == item["sha256"]
        assert "/holdout" not in str(path) and not path.name.startswith("H0")
    m = BASE / "manifest.json"
    if m.exists():
        manifest = read(m)
        for p, d in manifest["files"].items():
            assert sha((ROOT / p).read_bytes()) == d, p
        for p, d in manifest["historical_ledgers"].items():
            assert sha((ROOT / p).read_bytes()) == d, p
        for p, d in manifest["holdout_sealed_files"].items():
            # Byte-only seal maintenance. These files never enter a request or evaluator.
            assert sha((ROOT / p).read_bytes()) == d, p
        assert manifest["real_requests_authorized"] == 0
    return dict(
        status="offline prepared; signoffs/budget/live executor NOT authorized",
        materials=20,
        requests_max=59,
        base_cap=60,
        provider_calls=0,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare", "check"])
    args = p.parse_args()
    if args.action == "prepare":
        prepare()
    print(json.dumps(check()))
