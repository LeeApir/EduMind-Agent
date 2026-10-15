"""New fixed-input admission probes; no formal samples, credentials or network."""

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import httpx

from app.agents.hybrid_resource_review import RESOURCE_CHECKS, UNIT_CHECKS, review_once
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow, PlanInputs, generate_shared_plan
from app.services.deepseek_responses import _request_body
from app.services.learning_contract import canonical, digest
from app.services.learning_policy import active_policy_digest
from app.services.provider_gateway import StructuredResult, TransportAudit
from app.services.teaching_actions import assemble_actions
from app.services.unit_material import unit_material

ROOT = Path(__file__).resolve().parents[2]
BASE = "docs/acceptance/phase-1-om-admission-r01"
PRIVATE = "local-materials/phase-1-om-admission-r01"
MODEL = "deepseek-flash"
SLOTS = ("plan", "correct-unit", "reachable-safety", "fact-contradiction")


def identity(name):
    return str(uuid5(NAMESPACE_URL, "edumind:om-admission-r01:" + name))


def inputs(root=ROOT):
    graph = json.loads((root / "data/knowledge/phase-1.1.0.json").read_text())
    node = next(n for n in graph["nodes"] if n["id"] == "array")
    rid = f"graph-node:{graph['graph_version']}:array"
    ref = {
        "reference_id": rid,
        "version": graph["graph_version"],
        "digest": digest("graph-node", "graph-reference-v1", node=node),
    }
    return PlanInputs(
        metadata={
            "node_id": "array",
            "graph_version": graph["graph_version"],
            "graph_digest": digest("graph", "graph-snapshot-v1", nodes=graph["nodes"]),
            "profile_version": None,
            "profile_evidence_digest": digest(
                "profile-evidence", "profile-evidence-v1", evidence={}
            ),
            "goal": "用C追踪数组{2,5,9}的求和循环，解释下标0至2和返回值16。",
            "code_language": "C",
        },
        references={rid: ref},
        node_ids=frozenset(n["id"] for n in graph["nodes"]),
        learner_evidence={},
        reference_context={
            "source": ref,
            "node": node,
            "learner_evidence": {},
            "scope": "Partial graph; proposed trace is not independently verified evidence.",
        },
    )


def plan_draft(i):
    return {
        "objectives": [{"id": "sum", "text": "追踪数组求和的边界和结果"}],
        "terminology": [{"term": "i", "meaning": "从0开始的数组下标"}],
        "conventions": {
            "index_base": 0,
            "capacity": 3,
            "state_representation": "a={2,5,9}; total表示已处理元素之和",
            "not_applicable_reasons": [],
        },
        "shared_example": {
            "input_description": "a={2,5,9}",
            "initial_state": "total=0",
            "steps": [
                {
                    "operation": "遍历i=0,1,2并累加a[i]",
                    "expected_state": "total依次为2,7,16",
                    "expected_output": "16",
                }
            ],
        },
        "prerequisite_node_ids": [],
        "reference_ids": list(i.references),
        "scenes": [
            {"role": r, "scene_key": r, "objective_ids": ["sum"], "depends_on": deps}
            for r, deps in [
                ("explanation", []),
                ("code", ["explanation"]),
                ("exercise", ["explanation", "code"]),
            ]
        ],
    }


def valid_review(scope):
    return {
        "schema_version": "resource-review-v4",
        "scope": scope,
        "verdict": "pass",
        "findings": [],
        "coverage": {
            "checked": sorted(UNIT_CHECKS if scope == "unit" else RESOURCE_CHECKS),
            "unchecked": [],
        },
        "unresolved": [],
    }


class Capture:
    def __init__(self, value):
        self.value, self.requests = value, []

    async def generate_structured(self, request, *, retry_safe=False):
        assert retry_safe is False
        self.requests.append(request)
        return StructuredResult(
            deepcopy(self.value),
            "offline-capture-only",
            transport_audit=TransportAudit("1" * 64, "2" * 64, "3" * 64),
        )


def wire(request):
    body = _request_body(request.prompt, reasoning_effort="none")
    if request.prompt.temperature is None:
        body["temperature"] = 0.0
    body["text"] = {
        "format": {
            "type": "json_schema",
            "name": "edumind_result",
            "schema": dict(request.json_schema),
        }
    }
    body["model"] = MODEL
    # Match httpx's actual JSON encoder, including key order and Unicode behavior.
    return httpx.Request("POST", "https://api.deepseek.com/responses", json=body).content


async def build_cases(root=ROOT):
    i = inputs(root)
    capture = Capture(plan_draft(i))
    plan = await generate_shared_plan(capture, i, CallWindow())
    cases = {
        "plan": {
            "wire_hex": wire(capture.requests[0]).hex(),
            "kind": "plan",
            "scope": None,
            "anchors": [],
            "input_snapshot": i.snapshot(),
        }
    }
    for name in SLOTS[1:]:
        binding = {
            k: identity(name + ":" + k) for k in ("owner_id", "unit_id", "operation_id", "plan_id")
        }
        binding.update(
            plan_version=1,
            plan_digest=digest("plan", "learning-plan-v1", plan=plan),
            input_digest=digest("input", "learning-input-v1", snapshot=i.snapshot()),
            references_digest=digest("references", "references-v1", references=i.references),
            policy_version="hybrid-review-v1",
            policy_digest=active_policy_digest(),
        )
        w = PlannedScenes(plan, binding, reference_context=i.reference_context)
        claim = "数组a={2,5,9}，合法下标0至2。sum()返回16；函数不打印。"
        if name == "fact-contradiction":
            claim = "数组a={2,5,9}，合法下标0至2。sum()返回18；函数不打印。"
        source = (
            "int sum(void){int a[3]={2,5,9};int total=0;"
            "for(int i=0;i<3;i++)total+=a[i];return total;}"
        )
        if name == "reachable-safety":
            source = "int sum(void){int a[3]={2,5,9};return a[4];}"
        contents = {
            "explanation": {"markdown": claim},
            "code": {
                "language": "C",
                "source": "#include <stddef.h>\n" + source,
                "expected_output": "不打印；由调用方取得返回值。",
                "key_steps": ["按代码跟踪实际访问的下标。"],
                "display_only": True,
            },
            "exercise": {
                "items": [
                    {
                        "id": "q1",
                        "question": (
                            "[判断题] 长度为3的数组合法下标为0、1、2。仅填 T 或 F（T=正确，F=错误）"
                        ),
                        "answer": "T",
                        "explanation": "从0开始，最后下标为长度减1。",
                    },
                    {
                        "id": "q2",
                        "question": "[判断题] 2+5+9=16。仅填 T 或 F（T=正确，F=错误）",
                        "answer": "T",
                        "explanation": "2+5=7，7+9=16。",
                    },
                    {
                        "id": "q3",
                        "question": (
                            "[判断题] 返回值必然直接打印到屏幕。仅填 T 或 F（T=正确，F=错误）"
                        ),
                        "answer": "F",
                        "explanation": "返回值传给调用方；本例没有打印语句。",
                    },
                ]
            },
        }
        for role, content in contents.items():
            # Fixture staging needs declared predecessor status; these are NOT model passes.
            with patch(
                "app.agents.planned_scene_generation.uuid4",
                return_value=identity(name + ":" + role),
            ):
                c = w.stage(
                    role,
                    {
                        "resource_type": role,
                        "prompt_version": "learning-resources-v1",
                        "content": content,
                    },
                )
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
        g = Capture(valid_review(scope))
        record = await review_once(
            g,
            CallWindow(),
            binding=binding,
            target_digest=(
                candidates[0].content_digest if scope == "resource" else material["unit_digest"]
            ),
            payload=payload,
            candidates=candidates,
            scope=scope,
        )
        cases[name] = {
            "wire_hex": wire(g.requests[0]).hex(),
            "kind": "review",
            "scope": scope,
            "anchors": record["anchor_catalog"],
            "material": material,
            "fixture_status": "AUTHORED_NOT_MODEL_GENERATED_OR_REVIEWED",
        }
    return cases


def cases(root=ROOT):
    return asyncio.run(build_cases(root))


def price(wire_size, output=2048):
    # Existing kernel adds wire bytes as SLACK, not as a tokenizer estimate.
    return 2 * (1048576 + wire_size) + 8 * output


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def hash_bytes(value):
    import hashlib

    return hashlib.sha256(value).hexdigest()


def stable(value):
    return hash_bytes(canonical(value))
