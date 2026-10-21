"""Offline-only different-model proposal. No credentials, DNS, live runner or approvals."""

# ruff: noqa: E402
import argparse
import asyncio
import json
import sys
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import httpx
from acceptance_support.om_diagnostic import inputs, plan_draft, stable, valid_review
from acceptance_support.phase1_budget import sha
from app.agents.hybrid_resource_review import INSTRUCTION, REVIEW_V4_PROMPT, review_once
from app.agents.planned_scene_generation import SceneCandidate
from app.agents.shared_learning_plan import CallWindow, generate_shared_plan
from app.core.config import ProviderSettings
from app.core.provider_target import ApprovedTarget
from app.services.deepseek_responses import DeepSeekResponsesAdapter
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.openai_compatible import OpenAICompatibleAdapter
from app.services.provider_connection_dispatch import ModelCapabilities
from app.services.provider_gateway import StructuredRequest, TaskProfile, TransportAudit
from prepare_review_config_comparison import rebuild

BASE = "docs/acceptance/phase-1-review-model-candidate-r01"
PRIOR = "docs/acceptance/phase-1-evidence-v45-r01"
SCREEN = (
    "reachable-safety:candidate",
    "fact-contradiction:candidate",
    "gap-and-safety:candidate",
    "trace-complete:candidate",
)
CONFIG = {
    "version": "qwen0902-review-candidate-v1",
    "candidate_count_max": 1,
    "review_model": "qwen3.8-max-0902",
    "generation_model": "deepseek-flash",
    "review_provider": "openai-compatible",
    "review_transport": "json_schema",
    "endpoint_sha256": "fcc2d7cebcf9dc92386775dffe92e465f713a1ab8e88883fe5960bdc697289c0",
    "enable_thinking": False,
    "output_token_parameter": "max_completion_tokens",
    "output_request_limit": 8192,
    "documented_output_overrun": 10,
    "output_reserve_limit": 8202,
    "timeout_seconds": 60,
    "temperature": 0,
    "request_wire_limit": 65536,
    "input_reserve_per_call": 1048576 + 65536,
    "requests_max": 12,
    "screen_max": 4,
    "generalization_max": 8,
    "total_cost_ceiling_micro_cny": 164000000,
    "input_price_micro_cny_per_million": 12000000,
    "output_price_micro_cny_per_million": 36000000,
    "real_requests_authorized": 0,
    "fees_authorized": 0,
}


def read(path):
    return json.loads(path.read_text())


def caps():
    return ModelCapabilities(
        UUID(int=17),
        1,
        CONFIG["review_model"],
        "qwen0902-review-candidate-v1",
        structured_output=True,
        structured_transport="json_schema",
        output_token_parameter="max_completion_tokens",
        thinking_enabled=False,
    )


class OfflineOperation:
    """Only substitutes ConnectionOperation authority/HTTP for offline proof. No real connection."""

    def __init__(self, value):
        self.request = SimpleNamespace(
            route=SimpleNamespace(model_id=CONFIG["review_model"]), capabilities=caps()
        )
        self.value = value
        self.wires = []
        self.response_bytes = b""

    def _check(self):
        if self.request.route.model_id != self.request.capabilities.model_id:
            raise ValueError("ROUTE_CAPABILITY_MISMATCH")

    @asynccontextmanager
    async def send(self, body, *, stream=False):
        assert not stream

        def handler(request):
            self.wires.append(request.content)
            payload = {
                "model": CONFIG["review_model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(self.value),
                        },
                    }
                ],
                "usage": {"prompt_tokens": 90, "completion_tokens": 100},
            }
            self.response_bytes = json.dumps(payload).encode()
            return httpx.Response(200, stream=httpx.ByteStream(self.response_bytes))

        # .invalid is a mock-only stand-in; the historical endpoint is separately digest-bound.
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), trust_env=False
        ) as client:
            request = client.build_request(
                "POST", "https://review-route.invalid/v1/chat/completions", json=body
            )
            response = await client.send(request, stream=True)
            try:
                yield response
            finally:
                await response.aclose()


class OfflineRouter:
    """Proof composition only. It is not installed in production and has no live credentials."""

    def __init__(self, generation_value):
        self.review = OfflineOperation(valid_review("unit"))
        self.generation_wires = []

        def gen_send(request):
            self.generation_wires.append(request.content)
            return httpx.Response(
                200,
                json={
                    "model": "deepseek-flash",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(generation_value),
                                }
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 90, "output_tokens": 100},
                },
            )

        guard = SimpleNamespace(
            approve_base=lambda: ApprovedTarget(
                "https://api.deepseek.com", "api.deepseek.com", 443, ("8.8.8.8",)
            )
        )
        self.generation = DeepSeekResponsesAdapter(
            ProviderSettings(
                "https://api.deepseek.com", "OFFLINE_ONLY", "deepseek-flash"
            ),
            guard,
            transport=httpx.MockTransport(gen_send),
        )

    async def generate_structured(self, request, *, retry_safe=False):
        if request.prompt.messages[0].content != INSTRUCTION:
            return await self.generation.generate_structured(request)
        if (
            retry_safe is not False
            or request.prompt.task_profile != TaskProfile.QUALITY
        ):
            raise ValueError("NOT_BOUND_REVIEW")
        user = json.loads(request.prompt.messages[1].content)
        if user["unit"]["binding"]["policy_digest"] != active_policy_digest():
            raise ValueError("POLICY_MISMATCH")
        effective = StructuredRequest(
            replace(request.prompt, max_output_tokens=8192, temperature=0),
            request.json_schema,
        )
        result = await OpenAICompatibleAdapter(self.review).generate_structured(
            effective
        )
        if result.model_id != CONFIG["review_model"]:
            raise ValueError("RESPONSE_MODEL_MISMATCH")
        # Existing compatible adapter does not produce TransportAudit. Attach only observed
        # actual request/response bytes, never a synthetic successful review or placeholder hash.
        audit = TransportAudit(
            sha(self.review.wires[-1]),
            sha(self.review.response_bytes),
            stable(
                {
                    "route_model": self.review.request.route.model_id,
                    "capabilities": {
                        "transport": "json_schema",
                        "enable_thinking": False,
                        "max_completion_tokens": 8192,
                    },
                    "policy_digest": active_policy_digest(),
                    "prompt_version": REVIEW_V4_PROMPT,
                }
            ),
        )
        return replace(result, transport_audit=audit)


async def capture(case):
    router = OfflineRouter({})
    m = case["material"]
    candidates = tuple(
        SceneCandidate(
            c["resource_id"],
            c["role"],
            c["envelope"],
            c["content_digest"],
            c["dependency_digest"],
            tuple(c["upstream"]),
        )
        for c in m["candidates"]
    )
    record = await review_once(
        router,
        CallWindow(),
        binding=m["binding"],
        target_digest=m["unit_digest"],
        payload={"unit": m, "reference_context": m["reference_context"]},
        candidates=candidates,
        scope="unit",
        input_snapshot=case["input_snapshot"],
    )
    assert not router.generation_wires and len(router.review.wires) == 1
    actual = router.review.wires[0]
    body = json.loads(actual)
    before = json.loads(bytes.fromhex(case["wire_hex"]))
    assert body["messages"] == before["input"]
    assert (
        body["response_format"]["json_schema"]["schema"]
        == before["text"]["format"]["schema"]
    )
    assert record["binding"]["policy_digest"] == active_policy_digest()
    assert (
        record["request_digest"] == sha(actual)
        and record["prompt_version"] == REVIEW_V4_PROMPT
    )
    assert body["model"] == CONFIG["review_model"] and body["enable_thinking"] is False
    assert body["max_completion_tokens"] == 8192
    assert len(actual) <= CONFIG["request_wire_limit"]
    return actual, {
        "scope": "OFFLINE_MOCK_NO_QUALITY_OR_LIVE_CONNECTION_PROOF",
        "review_entry": "hybrid_resource_review.review_once(unit)",
        "adapter": "OpenAICompatibleAdapter",
        "connection_operation": "offline stand-in, not real ConnectionOperation/credential/consent/DB verification",
        "wire_sha256": sha(actual),
        "wire_bytes": len(actual),
        "actual_model": body["model"],
        "enable_thinking": body["enable_thinking"],
        "max_completion_tokens": body["max_completion_tokens"],
        "unchanged_messages": True,
        "unchanged_output_schema": True,
        "policy_digest": record["binding"]["policy_digest"],
        "prompt_version": record["prompt_version"],
        "provider_config_digest": record["provider_config_digest"],
        "generation_sends": 0,
    }


def item(q, a, why, n):
    return {
        "id": "q" + str(n),
        "question": "[判断题] " + q + "仅填 T 或 F（T=正确，F=错误）",
        "answer": a,
        "explanation": why,
    }


async def novel_cases():
    """Authored after v4.5 freeze, before candidate results; not independent human labels."""
    seed = read(ROOT / PRIOR / "cases.json")["trace-complete:candidate"]
    graph = read(ROOT / "data/knowledge/phase-1.1.0.json")
    result = {}
    for family in ("search", "stack"):
        node_id = "array" if family == "search" else "array-stack"
        node = next(n for n in graph["nodes"] if n["id"] == node_id)
        ref = {
            "reference_id": f"graph-node:{graph['graph_version']}:{node_id}",
            "version": graph["graph_version"],
            "digest": digest("graph-node", "graph-reference-v1", node=node),
        }
        if family == "search":
            goal = "用C追踪a={4,7,9,12}中查找9和查找8的线性搜索，明确i变化、提前返回及未命中退出边界，并用题目考查过程。"
            good = "int find(int target){int a[4]={4,7,9,12};for(int i=0;i<4;++i){if(a[i]==target)return i;}return -1;}"
            unsafe = good.replace("i<4", "i<=4")
            text = "数组容量4，合法下标0到3。find(9)依次检查i=0的4、i=1的7，都不等；i=2的9相等，立即返回2，不再检查i=3。find(8)依次检查i=0到3，均不等；i增至4时i<4为假，退出循环且不访问a[4]，返回-1。返回值交给调用方，本函数没有打印。"
            steps = [
                "查找9时i=0、1不等，i=2命中立即返回2。",
                "查找8时检查i=0到3，i=4条件假，退出返回-1，不访问a[4]。",
            ]
            questions = [
                item(
                    "查找9检查完i=1时，仍需继续检查i=2。",
                    "T",
                    "a[1]=7不等于9，尚未命中。",
                    1,
                ),
                item("查找8时i=4会读取a[4]。", "F", "i<4为假，先退出而非读取。", 2),
                item(
                    "查找9在i=2命中后，不再执行i=3的比较。",
                    "T",
                    "函数立即返回索引2。",
                    3,
                ),
            ]
            thin = "线性搜索逐项比较并返回匹配下标；此例查找9返回2。"
            thin_q = [
                item("线性搜索属于查找算法。", "T", "它用于寻找匹配元素。", 1),
                item("数组容量是4。", "T", "本例声明四个元素。", 2),
                item("find(9)的最终结果是2。", "T", "9位于下标2。", 3),
            ]
            initial = "a={4,7,9,12}; i=0"
            state = "i为从0开始的查找下标"
            capacity = 4
        else:
            goal = "用C追踪demo中容量3、top初值2的顺序栈先入栈9再出栈的过程，明确top和访问下标变化，并用题目考查该执行顺序。"
            good = (
                "int demo(void){int a[3]={3,6,0};int top=2;a[top++]=9;return a[--top];}"
            )
            unsafe = good.replace("top=2", "top=3")
            text = "本例top表示下一空闲位置，容量3、合法下标0到2，初始top=2且栈中为3、6。a[top++]=9先写a[2]=9再令top=3，栈达到容量。随后--top先把top减到2，再读取a[2]=9并返回9；出栈后有效元素仍为3、6，top=2。本次执行不读写a[3]。函数没有打印语句。这里只追踪这一次合法入栈与出栈，不承诺完整通用栈API。"
            steps = [
                "入栈使用原top=2写a[2]，然后top=3。",
                "出栈先--top至2，再读取a[2]，返回9。",
            ]
            questions = [
                item(
                    "入栈写入使用下标2，随后top成为3。", "T", "后置自增先使用旧值。", 1
                ),
                item(
                    "出栈会先读取a[3]再减top。", "F", "前置自减先令top=2，再读a[2]。", 2
                ),
                item("返回前的top为2，出栈值为9。", "T", "取出刚压入的元素。", 3),
            ]
            thin = "栈具有后进先出性质；本例先入栈再出栈。"
            thin_q = [
                item("栈是后进先出结构。", "T", "后入的元素先出。", 1),
                item("本例数组容量3。", "T", "数组长度为3。", 2),
                item("栈可以用数组实现。", "T", "顺序栈使用数组存储。", 3),
            ]
            initial = "a={3,6,0}; top=2"
            state = "top指向下一空闲位置"
            capacity = 3
        for kind in ("positive", "fact", "safety", "mixed"):
            old = deepcopy(seed)
            m = old["material"]
            snapshot = deepcopy(seed["input_snapshot"])
            snapshot["metadata"].update(node_id=node_id, goal=goal)
            snapshot["references"] = {ref["reference_id"]: ref}
            # Original diagnostic snapshots are authored scenario inputs, never a claimed real user's request.
            plan = m["plan"]
            plan.update(
                node_id=node_id,
                goal=goal,
                references=[ref],
                objectives=[{"id": "sum", "text": goal}],
                terminology=[
                    {"term": "i" if family == "search" else "top", "meaning": state}
                ],
            )
            plan["conventions"].update(capacity=capacity, state_representation=state)
            plan["shared_example"] = {
                "input_description": initial,
                "initial_state": initial,
                "steps": [
                    {
                        "operation": "按源码执行本例",
                        "expected_state": "按正确代码的边界与状态变化",
                        "expected_output": "2/-1" if family == "search" else "9",
                    }
                ],
            }
            m["binding"]["plan_digest"] = digest("plan", "learning-plan-v1", plan=plan)
            m["binding"]["references_digest"] = digest(
                "references", "references-v1", references={ref["reference_id"]: ref}
            )
            m["reference_context"] = {
                "source": ref,
                "node": node,
                "learner_evidence": {},
                "scope": "Partial reference, not a certified trace.",
            }
            for c in m["candidates"]:
                content = c["envelope"]["content"]
                if c["role"] == "explanation":
                    rendered = thin if kind == "mixed" else text
                    if kind == "fact":
                        rendered = (
                            rendered.replace("立即返回2", "立即返回3", 1)
                            if family == "search"
                            else rendered.replace("并返回9", "并返回6", 1)
                        )
                    content["markdown"] = rendered
                elif c["role"] == "code":
                    content.update(
                        source=unsafe if kind in {"safety", "mixed"} else good,
                        expected_output="不打印；由调用方取得返回值。",
                        key_steps=(
                            ["逐项比较。", "未命中可继续查找。"]
                            if family == "search"
                            else ["先入后出。", "执行一次入栈和出栈。"]
                        )
                        if kind == "mixed"
                        else steps,
                    )
                else:
                    content["items"] = thin_q if kind == "mixed" else questions
            name = f"generalization-{family}-{kind}"
            snapshot["reference_context"] = deepcopy(m["reference_context"])
            c = await rebuild(name, old, snapshot)
            c.update(arm="candidate", comparison_kind=kind, material_id=name)
            result[name] = c
    return result


def criterion(kind):
    if kind == "positive":
        return (
            "pass; all checks; empty findings/unchecked/unresolved; no false positives"
        )
    if kind == "fact":
        return "reject; concrete major/severe definite fact contradiction; every assertion/citation supported"
    if kind == "mixed":
        return "reject; concrete major/severe reachable code_safety retained; teaching gaps accurately separated; no unsupported factual conclusions"
    return "reject; concrete major/severe reachable code_safety; no deterministic UB outcome; all assertions/citations supported"


def concrete_witness(slot):
    if slot == "reachable-safety:candidate":
        return "长度3仅合法0..2，却无条件return a[4]；不能保证返回16不等于必非16；所有附带引用准确。"
    if slot == "fact-contradiction:candidate":
        return "定义良好的求和代码实际16，讲解声明18；答案F不支持数值16，必须引用实际代码/声明。"
    if slot == "gap-and-safety:candidate":
        return (
            "长度3访问a[4]仍严重拒绝；学生可见过程支持不足另外说明，不能整体降待人工。"
        )
    if slot == "trace-complete:candidate":
        return "完整正确求和材料：状态2/7/16、i=3退出、过程练习；应pass且无附带误报。"
    family, kind = slot.split("-")[-2:]
    if kind == "fact":
        return (
            "find(9)讲解声称返回3，定义良好的代码实际返回2。"
            if family == "search"
            else "讲解声称出栈返回6，定义良好的demo实际返回9。"
        )
    if kind in {"safety", "mixed"}:
        witness = (
            "find(8)在i=4时仍满足i<=4，读a[4]越界（合法0..3）。"
            if family == "search"
            else "容量3而top初值3，a[top++]=9首次即写a[3]越界（合法0..2）。"
        )
        if kind == "mixed":
            witness += "另未显式交付状态/边界轨迹，练习只问概念/容量/结果，未考查指定过程；严重拒绝保留，缺口具体列出。"
        return witness + "不能由UB推导固定值、必非某值或必崩溃。"
    return (
        "线性查找命中i=2返回2；未命中i=4条件假且不读取a[4]，返回-1；过程考查齐全。"
        if family == "search"
        else "top2写a[2]再增3；先减top至2，再读a[2]得9；过程考查齐全。"
    )


def human_document(cases, labels):
    lines = [
        "# 预冻结筛选与迁移检查材料",
        "",
        "标签仅为作者提案，未独立人工签核；新8例编写在固定v4.5之后，不能用于调参。任何附带断言/引用不合格即淘汰。",
    ]
    for label in labels:
        c = cases[label["id"]]
        lines += [
            "",
            "## " + label["id"],
            "阶段：" + label["phase"],
            "具体判据：" + label["concrete_witness"],
            "目标：" + c["input_snapshot"]["metadata"]["goal"],
            "材料摘要：" + stable(c["material"]),
        ]
        for candidate in c["material"]["candidates"]:
            lines += [
                "",
                "### " + candidate["role"],
                "```json",
                json.dumps(
                    candidate["envelope"]["content"], ensure_ascii=False, indent=2
                ),
                "```",
            ]
    return "\n".join(lines) + "\n"


def build():
    terms = read(ROOT / BASE / "official-terms.json")
    assert (
        terms["model"],
        terms["region"],
        terms["input_CNY_per_million"],
        terms["output_CNY_per_million"],
        terms["max_completion_tokens"],
        terms["reserved_output_including_reasoning"],
        terms["documented_output_overrun"],
        terms["enable_thinking"],
        terms["timeout_seconds"],
    ) == (CONFIG["review_model"], "cn-beijing", 12, 36, 8192, 8202, 10, False, 60)
    prior = read(ROOT / PRIOR / "proposal.json")
    old = read(ROOT / PRIOR / "cases.json")
    assert (
        stable(prior)
        == "d61ec628e5e3f7f30c420e1677fe4dcc361cddbeda4e4966c4dd8fa641c40de3"
    )
    assert stable(old) == prior["cases_sha256"]
    for name, h in prior["sources"].items():
        assert sha((ROOT / name).read_bytes()) == h
    cases = {slot: deepcopy(old[slot]) for slot in SCREEN}
    cases.update(asyncio.run(novel_cases()))
    observations = {}
    rows = []
    labels = []
    for slot, c in cases.items():
        actual, proof = asyncio.run(capture(c))
        observations[slot] = proof
        c["candidate_wire_hex"] = actual.hex()
        phase = "screen" if slot in SCREEN else "generalization"
        cost = 12 * (1048576 + len(actual)) + 36 * 8202
        rows.append(
            {
                "id": slot,
                "phase": phase,
                "wire_sha256": sha(actual),
                "wire_bytes": len(actual),
                "cost_micro_cny": cost,
            }
        )
        labels.append(
            {
                "id": slot,
                "phase": phase,
                "kind": c["comparison_kind"],
                "criterion": criterion(c["comparison_kind"]),
                "concrete_witness": concrete_witness(slot),
                "material_sha256": stable(c["material"]),
                "authored_after_v45_freeze": phase == "generalization",
            }
        )
    i = inputs(ROOT)
    router = OfflineRouter(plan_draft(i))
    asyncio.run(generate_shared_plan(router, i, CallWindow()))
    assert len(router.generation_wires) == 1 and not router.review.wires
    generation = json.loads(router.generation_wires[0])
    assert generation["model"] == "deepseek-flash"
    observations["generation-control"] = {
        "real_entry": "generate_shared_plan",
        "actual_model": generation["model"],
        "request_sha256": sha(router.generation_wires[0]),
        "candidate_review_sends": 0,
        "scope": "synthetic offline routing only; not live default activation",
    }
    sources = {n: sha((ROOT / n).read_bytes()) for n in prior["sources"]}
    extra = [
        "scripts/prepare_review_model_candidate.py",
        "scripts/tests/test_review_model_candidate.py",
        BASE + "/README.md",
        BASE + "/official-terms.json",
        "backend/app/services/openai_compatible.py",
        "backend/app/services/provider_connection_dispatch.py",
        "backend/app/core/provider_factory.py",
        "scripts/prepare_review_config_comparison.py",
        PRIOR + "/cases.json",
        PRIOR + "/proposal.json",
        "docs/acceptance/phase-1-provider-connection-v1/results/final.json",
        "docs/acceptance/phase-1-provider-connection-v1/results/checks-r03-structured.json",
        "docs/acceptance/phase-1-provider-selection/deepseek-20261014.json",
        "docs/acceptance/phase-1-review-replacement-r01/results/reachable-safety-01.json",
    ]
    sources.update({n: sha((ROOT / n).read_bytes()) for n in extra})
    proposal = {
        "version": "different-model-candidate-plan-v1",
        "baseline": "dd96f42",
        "config": CONFIG,
        "prompt_version": REVIEW_V4_PROMPT,
        "policy_digest": active_policy_digest(),
        "sources": sources,
        "cases_sha256": stable(cases),
        "offline_capture_sha256": stable(observations),
        "labels_sha256": stable(labels),
        "slots": rows,
        "exact_slot_reserve_micro_cny": sum(x["cost_micro_cny"] for x in rows),
        "absolute_request_budget_micro_cny": 12 * (12 * (1048576 + 65536) + 36 * 8202),
        "global_ceiling_micro_cny": 164000000,
        "requests_authorized": 0,
        "fees_authorized": 0,
        "execution_status": "PROPOSAL_ONLY_NO_LIVE_RUNNER",
        "screen_gate": "all4 actual receipts complete, all assertions/citations correct, real human labels and receipt-bound signoffs; no retries",
        "generalization_gate": "all8 prospective frozen new cases, unchanged config/Prompt/criteria; any failure eliminates candidate; no second candidate",
        "next": "Only after all12 pass: T040 admission review; no formal acceptance authorization",
    }
    proposal["sources"][BASE + "/human-review.md"] = sha(
        human_document(cases, labels).encode()
    )
    assert (
        proposal["exact_slot_reserve_micro_cny"]
        <= proposal["absolute_request_budget_micro_cny"]
        <= 164000000
    )
    return {
        "proposal.json": proposal,
        "candidate-config.json": CONFIG,
        "cases.json": cases,
        "offline-capture.json": observations,
        "proposed-labels.json": {
            "status": "PROPOSED_NOT_INDEPENDENTLY_HUMAN_SIGNED",
            "rows": labels,
            "caution": "Prospectively authored after fixed v4.5; not an independent blind benchmark or statistical guarantee.",
        },
    }


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    values = build()
    if args.write:
        human = human_document(
            values["cases.json"], values["proposed-labels.json"]["rows"]
        )
        human_path = ROOT / BASE / "human-review.md"
        if human_path.exists() and human_path.read_text() != human:
            raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
        for n, v in values.items():
            path = ROOT / BASE / n
            content = json.dumps(v, ensure_ascii=False, indent=2) + "\n"
            if path.exists() and path.read_text() != content:
                raise ValueError("REFUSE_OVERWRITE_FROZEN_PACKAGE")
        for n, v in values.items():
            (ROOT / BASE / n).write_text(
                json.dumps(v, ensure_ascii=False, indent=2) + "\n"
            )
        human_path.write_text(human)
    p = values["proposal.json"]
    print(
        json.dumps(
            {
                "proposal_sha256": stable(p),
                "candidate_count": 1,
                "requests_max": 12,
                "exact_slot_reserve_micro_cny": p["exact_slot_reserve_micro_cny"],
                "global_ceiling_micro_cny": 164000000,
                "provider_calls": 0,
                "authorized": False,
            }
        )
    )


if __name__ == "__main__":
    main()
