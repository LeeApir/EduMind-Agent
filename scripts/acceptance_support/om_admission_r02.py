"""Authored calibration pairs for the scope-contract repair; never formal holdout data."""

import asyncio
from copy import deepcopy
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from acceptance_support import om_diagnostic as prior

from app.agents.hybrid_resource_review import review_once
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.teaching_actions import assemble_actions
from app.services.unit_material import unit_material

BASE = "docs/acceptance/phase-1-om-admission-r02"
PRIVATE = "local-materials/phase-1-om-admission-r02"
SLOTS = ("correct-unit", "missing-unit-objective", "reachable-safety", "fact-contradiction")


def identity(name):
    return str(uuid5(NAMESPACE_URL, "edumind:om-admission-r02:" + name))


async def build_cases(root=prior.ROOT):
    # Same failed-control family, explicitly calibration, not new statistically independent data.
    seeds = await prior.build_cases(root)
    result = {}
    for name in SLOTS:
        seed = seeds["correct-unit" if name == "missing-unit-objective" else name]["material"]
        plan, binding = deepcopy(seed["plan"]), deepcopy(seed["binding"])
        plan["objectives"][0]["text"] = "逐步追踪total=2、7、16及i=3时不再访问数组的边界"
        for key in ("owner_id", "unit_id", "operation_id", "plan_id"):
            binding[key] = identity(name + ":" + key)
        binding["plan_digest"] = digest("plan", "learning-plan-v1", plan=plan)
        binding["policy_digest"] = active_policy_digest()
        w = PlannedScenes(plan, binding, reference_context=seed["reference_context"])
        trace = (
            "a={2,5,9}，容量3，下标0、1、2。total初始为0。"
            "i=0读取a[0]=2后total=2；i=1读取a[1]=5后total=7；"
            "i=2读取a[2]=9后total=16。i增至3，i<3为假，停止循环，"
            "不访问a[3]，循环体恰执行3次。sum()返回16，不直接打印。"
        )
        if name == "fact-contradiction":
            trace = trace.replace("sum()返回16", "sum()返回18")
        if name == "missing-unit-objective":
            trace = "a={2,5,9}，容量3，下标0、1、2。sum()返回16，不直接打印。"
        for old in seed["candidates"]:
            envelope = deepcopy(old["envelope"])
            role = old["role"]
            if role == "explanation":
                envelope["content"]["markdown"] = trace
            elif role == "code":
                envelope["content"]["key_steps"] = (
                    ["total从0开始依次变为2、7、16。", "i=3时i<3为假，停止且不访问a[3]。"]
                    if name != "missing-unit-objective"
                    else ["遍历并求和后返回结果。"]
                )
            elif role == "exercise" and name != "missing-unit-objective":
                envelope["content"]["items"] = [
                    {
                        "id": "q1",
                        "question": (
                            "[判断题] i=1这次循环结束后total=7。"
                            "仅填 T 或 F（T=正确，F=错误）"
                        ),
                        "answer": "T",
                        "explanation": "先加入a[0]=2，再加入a[1]=5，得到7。",
                    },
                    {
                        "id": "q2",
                        "question": (
                            "[判断题] i=3时停止，循环体共执行3次。"
                            "仅填 T 或 F（T=正确，F=错误）"
                        ),
                        "answer": "T",
                        "explanation": "i只在0、1、2进入循环体；i=3不满足i<3。",
                    },
                    {
                        "id": "q3",
                        "question": (
                            "[判断题] sum返回16表示它直接打印16。"
                            "仅填 T 或 F（T=正确，F=错误）"
                        ),
                        "answer": "F",
                        "explanation": "返回值交给调用方，本函数没有打印语句。",
                    },
                ]
            with patch(
                "app.agents.planned_scene_generation.uuid4",
                return_value=identity(name + ":" + role),
            ):
                c = w.stage(role, envelope)
            # Authored staging only; these statuses are never model-review evidence.
            w.disposition(role, c.id, "pass")
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
        scope = "resource" if name == "reachable-safety" else "unit"
        candidates = (w.candidates()[1],) if scope == "resource" else w.candidates()
        payload = (
            {
                "plan": plan,
                "candidate": candidates[0].payload(),
                "reference_context": w.reference_context,
            }
            if scope == "resource"
            else {"unit": material, "reference_context": w.reference_context}
        )
        gateway = prior.Capture(prior.valid_review(scope))
        record = await review_once(
            gateway,
            CallWindow(),
            binding=binding,
            target_digest=candidates[0].content_digest
            if scope == "resource"
            else material["unit_digest"],
            payload=payload,
            candidates=candidates,
            scope=scope,
        )
        result[name] = {
            "wire_hex": prior.wire(gateway.requests[0]).hex(),
            "kind": "review",
            "scope": scope,
            "anchors": record["anchor_catalog"],
            "material": material,
            "fixture_status": "AUTHORED_CALIBRATION_NOT_MODEL_OR_HUMAN_APPROVED",
        }
    return result


def cases(root=prior.ROOT):
    return asyncio.run(build_cases(root))
