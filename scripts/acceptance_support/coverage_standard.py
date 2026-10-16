"""Closed calibration-material checks, not a generic C executor or semantic judge."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from acceptance_support.om_diagnostic import Capture, stable, valid_review, wire

from app.agents.hybrid_resource_review import review_once
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.teaching_actions import assemble_actions
from app.services.unit_material import unit_material

ROOT = Path(__file__).resolve().parents[2]
SLOTS = ("trace-complete", "trace-distributed", "plan-only-gap", "assessment-gap")
GOOD_SOURCE = (
    "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};int total=0;"
    "for(int i=0;i<3;i++)total+=a[i];return total;}"
)
BAD_SOURCE = "#include <stddef.h>\nint sum(void){int a[3]={2,5,9};return a[4];}"


def read_materials(root=ROOT):
    base = root / "docs/acceptance/phase-1-om-admission-r03"
    proposal = json.loads((base / "proposal.json").read_text())
    value = json.loads((base / "cases.json").read_text())
    if stable(value) != proposal["cases_sha256"]:
        raise ValueError("HISTORICAL_MATERIAL_CHANGED")
    return value


def reference_check(source):
    """Only two exact authored snippets. Never parse/execute arbitrary supplied C."""
    if source == GOOD_SOURCE:
        values, total, trace = [2, 5, 9], 0, []
        for i, value in enumerate(values):
            total += value
            trace.append({"i": i, "total": total})
        return {
            "source_matched_closed_fixture": True,
            "trace": trace,
            "exit": {"i": 3, "condition": "i<3 is false"},
            "return": total,
            "method": "trusted Python model of this exact fixed loop, not C execution",
        }
    if source == BAD_SOURCE:
        return {
            "source_matched_closed_fixture": True,
            "reachable_unsafe_access": "a[4]",
            "array_length": 3,
            "valid_indices": [0, 1, 2],
            "return": None,
            "method": "exact fixture inspection; no undefined C behavior executed",
        }
    raise ValueError("UNSUPPORTED_REFERENCE_PROGRAM")


def reassess(root=ROOT):
    values = read_materials(root)
    rows = []
    for name in (
        "correct-unit",
        "missing-unit-objective",
        "reachable-safety",
        "fact-contradiction",
    ):
        m = values[name]["material"]
        by_role = {c["role"]: c for c in m["candidates"]}
        source = by_role["code"]["envelope"]["content"]["source"]
        reference = reference_check(source)
        gap = name == "missing-unit-objective"
        rows.append(
            {
                "id": name,
                "material_sha256": stable(m),
                "unit_digest": m["unit_digest"],
                "source_evidence": [
                    {
                        "resource_id": c["resource_id"],
                        "resource_digest": c["content_digest"],
                        "role": c["role"],
                        "actual_content": c["envelope"]["content"],
                    }
                    for c in m["candidates"]
                ],
                "reference_check": reference,
                "accompanying_inconsistencies": [
                    "Code directly returns a[4] and has no i/total/loop, while explanation, "
                    "key_steps and process questions describe a summation loop."
                ]
                if name == "reachable-safety"
                else [],
                "implementation": "unsafe reachable access"
                if name == "reachable-safety"
                else "correct fixed loop",
                "process_support": (
                    "partial: no explicit state sequence or loop exit in student-facing fields"
                )
                if gap
                else (
                    "explicit state sequence and loop exit in explanation; "
                    "inspect any actual defects separately"
                ),
                "process_assessment": (
                    "not established by final arithmetic/index-bound/non-printing questions"
                )
                if gap
                else "q1 asks intermediate total, q2 loop exit/iteration count",
                "expected_primary_semantics": {
                    "correct-unit": "pass",
                    "missing-unit-objective": "needs_human",
                    "reachable-safety": "code_safety reachable defect",
                    "fact-contradiction": "fact: stated18 vs actual16",
                }[name],
                "teaching_gap_is_severe_fact_error": False,
                "adjudication_authority": "CURRENT_USER_EXPLICIT_PARTIAL_COVERAGE_DECISION"
                if gap
                else "ASSISTANT_RUBRIC_RECHECK_AND_CLOSED_REFERENCE_CHECK_NOT_NEW_HUMAN_SIGNOFF",
                "internal_plan_counted_as_teaching": False,
            }
        )
    return {
        "version": "coverage-standard-reassessment-v1",
        "standard": "ADR-0016",
        "review_method": (
            "read frozen student-facing bodies without using model "
            "verdicts as evidence; fixed code arithmetic checked independently"
        ),
        "independent_human_review_of_all_rows": False,
        "provider_requests": 0,
        "rows": rows,
        "formal_50_labels": (
            "not requalified; still need independent scope/coverage review before formal acceptance"
        ),
        "old_results_labels_halts": "unchanged; reassessment is a new separate artifact",
    }


def identity(name):
    return str(uuid5(NAMESPACE_URL, "edumind:coverage-r04:" + name))


async def build_cases(root=ROOT):
    seeds = read_materials(root)
    result = {}
    for name in (*SLOTS, "implementation-only-offline"):
        seed = seeds["missing-unit-objective" if name == "plan-only-gap" else "correct-unit"][
            "material"
        ]
        plan, binding = deepcopy(seed["plan"]), deepcopy(seed["binding"])
        if name == "assessment-gap":
            plan["goal"] += "并用题目检验学生是否掌握循环过程。"
            plan["objectives"][0]["text"] += "，用题目检验中间状态和退出条件知识。"
        if name == "implementation-only-offline":
            plan["goal"] = "提供数组求和的C实现及必要输入、返回值说明。"
            plan["objectives"][0]["text"] = (
                "提供正确求和实现，说明固定输入与返回值，不承诺过程教学或测量。"
            )
        # Perfect internal trace deliberately remains in the gap case; it does NOT rescue delivery.
        plan["shared_example"]["steps"] = [
            {
                "operation": "i=0,1,2累加a[i]",
                "expected_state": "total依次2,7,16",
                "expected_output": None,
            },
            {
                "operation": "i=3检查i<3",
                "expected_state": "条件为假，退出且不访问a[3]",
                "expected_output": "16",
            },
        ]
        for k in ("owner_id", "unit_id", "operation_id", "plan_id"):
            binding[k] = identity(name + ":" + k)
        input_snapshot = {
            "goal": plan["goal"],
            "node_id": plan["node_id"],
            "code_language": plan["code_language"],
            "reference_context": seed["reference_context"],
        }
        binding["input_digest"] = digest("input", "learning-input-v1", snapshot=input_snapshot)
        binding["plan_digest"] = digest("plan", "learning-plan-v1", plan=plan)
        binding["policy_digest"] = active_policy_digest()
        w = PlannedScenes(plan, binding, reference_context=seed["reference_context"])
        for old in seed["candidates"]:
            role, envelope = old["role"], deepcopy(old["envelope"])
            if (
                name in ("trace-distributed", "implementation-only-offline")
                and role == "explanation"
            ):
                envelope["content"]["markdown"] = (
                    "固定输入a={2,5,9}；sum无外部参数，返回16，不直接打印。"
                )
            if name == "implementation-only-offline" and role == "code":
                envelope["content"]["key_steps"] = ["对固定数组求和后返回结果。"]
            if role == "exercise" and name in ("assessment-gap", "implementation-only-offline"):
                envelope["content"] = deepcopy(
                    seeds["missing-unit-objective"]["material"]["candidates"][2]["envelope"][
                        "content"
                    ]
                )
            with patch(
                "app.agents.planned_scene_generation.uuid4",
                return_value=identity(name + ":" + role),
            ):
                c = w.stage(role, envelope)
            w.disposition(role, c.id, "pass")  # Authored staging, never model-review evidence.
        scenes = [
            {
                "role": c.role,
                "scene_key": c.role,
                "scene_id": identity(name + ":scene:" + c.role),
                "scene_version": 1,
                "resource_id": c.id,
                "resource_digest": c.content_digest,
                "dependency_digest": c.dependency_digest,
            }
            for c in w.candidates()
        ]
        material = unit_material(w, scenes, assemble_actions(w.candidates()))
        capture = Capture(valid_review("unit"))
        record = await review_once(
            capture,
            CallWindow(),
            binding=binding,
            target_digest=material["unit_digest"],
            payload={"unit": material, "reference_context": w.reference_context},
            candidates=w.candidates(),
            scope="unit",
        )
        result[name] = {
            "wire_hex": wire(capture.requests[0]).hex(),
            "scope": "unit",
            "kind": "review",
            "material": material,
            "input_snapshot": input_snapshot,
            "anchors": record["anchor_catalog"],
            "fixture_status": "AUTHORED_CALIBRATION_PENDING_INDEPENDENT_HUMAN_REVIEW",
            "real_slot": name in SLOTS,
        }
    return result


def cases(root=ROOT):
    return asyncio.run(build_cases(root))
