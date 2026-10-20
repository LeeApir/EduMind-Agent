"""Build sixteen fixed test inputs and twelve full review fixtures, entirely offline."""

# ruff: noqa: E402
import argparse
import asyncio
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import patch
from uuid import NAMESPACE_URL, UUID, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.luna_high_candidate import CONFIG, offline_router
from acceptance_support.om_diagnostic import Capture, inputs, plan_draft, valid_review
from acceptance_support.qwen_review_budget import canonical, sha
from app.agents.hybrid_resource_review import review_once, review_output_schema
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow, generate_shared_plan
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.teaching_actions import assemble_actions
from app.services.teaching_binding import select_teaching_context
from app.services.unit_material import unit_material
from prepare_luna_admission import candidates

BASE = ROOT / "docs/acceptance/phase-1-five-hour-test-plan-r01"
TRACE_GOAL = (
    "用C实现并明确追踪数组{4,6,9}求和的关键状态与循环退出条件，并用题目考查过程掌握。"
)
SUM_CODE = "int sum_sample(void) {\n    int a[3] = {4, 6, 9};\n    int s = 0;\n    for (int i = 0; i < 3; ++i) s += a[i];\n    return s;\n}"
TRACE = "初始s=0；i=0轮后s=4，i=1轮后s=10，i=2轮后s=19；随后i=3，3<3为假，退出，不访问a[3]，返回19，无打印。"


def uid(name):
    return str(uuid5(NAMESPACE_URL, "edumind:five-hour-materials-r01:" + name))


def quiz(n, question, answer, explanation):
    return dict(
        id=f"q{n}",
        question="[判断题] " + question + " 仅填 T 或 F（T=正确，F=错误）。",
        answer=answer,
        explanation=explanation,
    )


def contents(kind):
    value = dict(
        explanation=dict(
            markdown="本节只实现并追踪这个求和示例，不承诺整个数组节点。" + TRACE
        ),
        code=dict(
            language="C",
            source=SUM_CODE,
            expected_output="函数返回19，没有标准输出。",
            key_steps=[TRACE],
            display_only=True,
        ),
        exercise=dict(
            items=[
                quiz(
                    1, "请从s=0逐轮推演：i=1轮结束后s=10", "T", "先加4得4，再加6得10。"
                ),
                quiz(
                    2,
                    "请推演首次条件失败：i=3时退出，不执行访问a[3]的循环体",
                    "T",
                    "i=2轮后s=19，i递增为3，3<3为假，因此退出。",
                ),
                quiz(
                    3, "函数会自行把19打印到屏幕", "F", "函数只有return，没有打印语句。"
                ),
            ]
        ),
    )
    if kind == "fact":
        value["explanation"]["markdown"] = "sum_sample返回17，无打印。" + TRACE
    if kind in ("teaching-gap", "mixed"):
        value["explanation"]["markdown"] = (
            "本节处理数组{4,6,9}的求和过程，函数没有打印语句。"
        )
        value["code"]["key_steps"] = ["按给定实现运行。"]
    if kind == "teaching-gap":
        for item in value["exercise"]["items"][:2]:
            # False question propositions do not themselves supply a worked trace.
            item["question"] = (
                item["question"]
                .replace("s=10", "s=12")
                .replace("i=3时退出", "i=4时退出")
            )
            item["answer"] = "F"
            item["explanation"] = "本题答案F，此处不提供展开的状态表或退出边界推演。"
    if kind in ("assessment-gap", "mixed"):
        value["exercise"]["items"] = [
            quiz(1, "4+6+9=19", "T", "4+6=10，10+9=19。"),
            quiz(2, "6+9+4=19", "T", "6+9=15，15+4=19。"),
            quiz(3, "9+4+6=20", "F", "9+4+6=19。"),
        ]
    if kind == "mixed":
        value["code"]["source"] = (
            "int sum_sample(void) {\n    int a[3] = {4, 6, 9};\n    return a[3];\n}"
        )
        value["code"]["expected_output"] = "无标准输出；函数尝试把值返回给调用方。"
    if kind == "distributed":
        value["explanation"]["markdown"] = (
            "sum_sample求和数组{4,6,9}，返回19，不打印；关键状态见代码步骤，退出边界见q2解析。"
        )
        value["code"]["key_steps"] = [
            "s从0开始，处理i=0、1、2后依次为4、10、19。",
            "退出边界见q2解析。",
        ]
    if kind == "safety":
        value["explanation"]["markdown"] = (
            "read_example是一个可直接调用的固定数组读取函数。本例声称其访问安全，函数无打印。"
        )
        value["code"].update(
            source="int read_example(void) {\n    int a[2] = {5, 7};\n    return a[2];\n}",
            expected_output="没有标准输出；函数尝试返回一个数组元素。",
            key_steps=["声明a含两个元素，随后执行return表达式。"],
        )
        value["exercise"]["items"] = [
            quiz(1, "声明int a[2]后合法元素下标为0和1", "T", "长度2的元素下标是0、1。"),
            quiz(
                2,
                "int a[2]中的a[2]是可合法读取的第三个元素",
                "F",
                "第三个位置不属于这两个数组元素。",
            ),
            quiz(3, "read_example包含打印语句", "F", "函数只有数组声明和return。"),
        ]
    if kind in ("prerequisite", "unknown-profile"):
        value["explanation"]["markdown"] = (
            "p保存value的地址；value初始化为21，*p在value仍存活时读到21，返回21，不打印。"
            + (
                "本节只补指针先修，尚未交付链表头插法，原目标留待后续。"
                if kind == "prerequisite"
                else ""
            )
        )
        value["code"].update(
            source="int pointer_sample(void) {\n    int value = 21;\n    int *p = &value;\n    return *p;\n}",
            expected_output="函数返回21，没有标准输出。",
            key_steps=[
                "先取value地址，再在value存活期间解引用；返回的是int值，不是局部变量地址。"
            ],
        )
        value["exercise"]["items"] = [
            quiz(1, "p保存value的地址", "T", "&value取地址。"),
            quiz(2, "这次*p读取21", "T", "读取发生在value存活期间，value初始化为21。"),
            quiz(3, "返回int值等于返回局部变量地址", "F", "这里返回的是*p的整数值。"),
        ]
    if kind == "scene-scope":
        value["explanation"]["markdown"] = (
            "C数组a[3]包含3个同类型元素，合法下标为0、1、2。后续代码场景给出求和实现，练习场景提供题目；本讲解只说明长度和下标。"
        )
    if kind == "code-contradiction":
        value["explanation"]["markdown"] = (
            "first_sample读取固定数组首元素4，函数不打印。"
        )
        value["code"].update(
            source="int first_sample(void) {\n    int a[3] = {4, 6, 9};\n    /* 返回最后一个元素9。 */\n    return a[0];\n}",
            expected_output="返回首元素4，没有标准输出。",
            key_steps=["读取合法下标0的元素，其值为4。"],
        )
    if kind == "answer-contradiction":
        value["exercise"]["items"] = [
            quiz(1, "4+6+9=19", "F", "4+6+9=19，因此题干命题成立，应答T。"),
            quiz(2, "数组声明int a[3]的合法下标包含3", "F", "合法下标只有0、1、2。"),
            quiz(
                3,
                "执行int f(void){return 19;}会打印19",
                "F",
                "return把值交给调用方，不是打印。",
            ),
        ]
    return value


def input_for(name, node, goal, *, prerequisite=False):
    graph = default_knowledge_graph_repository()
    owner = uid(name + ":owner")
    path = SimpleNamespace(
        id=uid(name + ":path"),
        user_id=UUID(owner),
        target_node_id=node,
        current_node_id="c-pointer" if prerequisite else node,
        nodes=[{"node_id": node}]
        + ([{"node_id": "c-pointer"}] if prerequisite else []),
        version=1,
        graph_version=graph.graph_version,
    )
    tc = select_teaching_context(
        owner_id=path.user_id,
        target_node_id=node,
        original_request=goal,
        mode="recommended" if prerequisite else "target",
        graph=graph,
        path=path,
    )
    node_value = next(
        n
        for n in json.loads((ROOT / "data/knowledge/phase-1.1.0.json").read_text())[
            "nodes"
        ]
        if n["id"] == tc["teaching_node_id"]
    )
    rid = f"graph-node:{graph.graph_version}:{node_value['id']}"
    ref = dict(
        reference_id=rid,
        version=graph.graph_version,
        digest=digest("graph-node", "graph-reference-v1", node=node_value),
    )
    seed = inputs()
    return replace(
        seed,
        metadata={
            **seed.metadata,
            "node_id": tc["teaching_node_id"],
            "goal": tc["segment_goal"],
            "graph_version": tc["graph_version"],
            "graph_digest": tc["graph_digest"],
        },
        references={rid: ref},
        reference_context={
            "source": ref,
            "node": node_value,
            "learner_evidence": {},
            "scope": "Background only, not certification of this example.",
        },
        teaching_context=tc,
    )


def draft_for(i, kind):
    d = plan_draft(i)
    d["objectives"] = [dict(id="local", text=i.metadata["goal"])]
    for scene in d["scenes"]:
        scene["objective_ids"] = ["local"]
    d["terminology"] = [dict(term="返回值", meaning="函数交给调用方的值，不等于打印")]
    d["shared_example"] = dict(
        input_description="a={4,6,9}",
        initial_state="s=0,i=0",
        steps=[
            dict(
                operation="求和循环",
                expected_state="s=4,10,19；i=3条件失败退出",
                expected_output="无打印，返回19",
            )
        ],
    )
    d["conventions"].update(
        index_base=0,
        capacity=3,
        state_representation="s为已处理元素和，i为下一个处理下标",
    )
    if kind == "safety":
        d["shared_example"] = dict(
            input_description="a={5,7},长度2",
            initial_state="数组初始化",
            steps=[
                dict(
                    operation="固定数组读取",
                    expected_state="只允许下标0或1",
                    expected_output="返回值交给调用方，无打印",
                )
            ],
        )
        d["conventions"].update(
            capacity=2, state_representation="a为长度2数组，下标必须在0或1"
        )
    if kind in ("prerequisite", "unknown-profile"):
        d["shared_example"] = dict(
            input_description="value=21",
            initial_state="value初始化21",
            steps=[
                dict(
                    operation="取地址再解引用",
                    expected_state="p=&value，*p=21",
                    expected_output="无打印，返回21",
                )
            ],
        )
        d["conventions"].update(
            index_base=None,
            capacity=None,
            state_representation="p保存value地址",
            not_applicable_reasons=["标量指针例不涉及容器容量或下标。"],
        )
    if kind == "scene-scope":
        d["objectives"] = [
            dict(id="concept", text="说明长度3数组的合法下标0、1、2"),
            dict(id="implementation", text="代码场景提供安全求和实现"),
            dict(id="assessment", text="练习场景检查下标与求和知识"),
        ]
        for scene, ids in zip(
            d["scenes"], [["concept"], ["implementation"], ["assessment"]], strict=True
        ):
            scene["objective_ids"] = ids
    if kind == "code-contradiction":
        d["shared_example"] = dict(
            input_description="a={4,6,9}",
            initial_state="数组初始化",
            steps=[
                dict(
                    operation="读取下标0",
                    expected_state="读取首元素4",
                    expected_output="返回4，不打印",
                )
            ],
        )
    return d


async def make_case(name, kind, goal, node="array", *, role=None):
    i = input_for(name, node, goal, prerequisite=kind == "prerequisite")
    plan = await generate_shared_plan(Capture(draft_for(i, kind)), i, CallWindow())
    binding = {
        k: uid(name + ":" + k)
        for k in ("owner_id", "unit_id", "operation_id", "plan_id")
    }
    binding.update(
        plan_version=1,
        plan_digest=digest("plan", "learning-plan-v1", plan=plan),
        input_digest=digest("input", "learning-input-v1", snapshot=i.snapshot()),
        references_digest=digest(
            "references", "references-v1", references=i.references
        ),
        policy_version="hybrid-review-v1",
        policy_digest=active_policy_digest(),
    )
    w = PlannedScenes(
        plan,
        binding,
        reference_context=i.reference_context,
        input_snapshot=i.snapshot(),
    )
    for r, c in contents(kind).items():
        with patch(
            "app.agents.planned_scene_generation.uuid4",
            return_value=uid(name + ":" + r),
        ):
            candidate = w.stage(
                r,
                dict(
                    resource_type=r, prompt_version="learning-resources-v1", content=c
                ),
            )
        w.disposition(
            r, candidate.id, "pass"
        )  # Fixture assembly only; NOT model review.
    scenes = [
        dict(
            role=c.role,
            scene_key=c.role,
            scene_id=uid(name + ":scene:" + c.role),
            scene_version=1,
            resource_id=c.id,
            resource_digest=c.content_digest,
            dependency_digest=c.dependency_digest,
        )
        for c in w.candidates()
    ]
    return dict(
        id=name,
        scope="resource" if role else "unit",
        selected_role=role,
        material=unit_material(w, scenes, assemble_actions(w.candidates())),
        input_snapshot=i.snapshot(),
        provenance=dict(
            author="Codex GPT-authored fixture, not independent human truth",
            relationship_to_history="new content, reuses known diagnostic patterns; NOT blind/independent population sample",
            historical_failed_stack_sample_reused=False,
        ),
        actual_model_result=None,
    )


REVIEW_SPECS = (
    (
        "U01",
        "fact",
        TRACE_GOAL,
        "array",
        None,
        ["reject"],
        "fact",
        "major",
        [
            "讲解声明返回17，实际源码按有定义累加返回19，且讲解轨迹本身也得19；须具体指出矛盾，不虚构内存缺陷。"
        ],
    ),
    (
        "U02",
        "safety",
        "提供一个可直接调用且数组访问安全的固定读取函数，说明下标与返回约定。",
        "array",
        None,
        ["reject"],
        "code_safety",
        "severe",
        [
            "长度2数组读取a[2]，合法0/1；调用时越界可达。UB不保证数值或正常返回，不得推导必然不是7。",
            "安全调用宣称与实际访问冲突是同一安全问题，不要求多报一个fact。",
        ],
    ),
    (
        "U03",
        "mixed",
        TRACE_GOAL,
        "array",
        None,
        ["reject"],
        "code_safety",
        "severe",
        [
            "长度3却读取a[3]，调用时越界可达；无求和循环实现。",
            "学生可见内容缺状态/退出教学，三题仅算术，缺过程考查；严重拒绝不能降为仅needs_human。",
        ],
    ),
    (
        "U04",
        "teaching-gap",
        TRACE_GOAL,
        "array",
        None,
        ["needs_human"],
        None,
        None,
        [
            "代码正确且过程题存在，但所有可见载体都未给出完整关键状态/退出教学；F答案与未展开解析不能补齐。",
            "没有事实或安全错误，不把判断题里的假命题当作教学断言。",
        ],
    ),
    (
        "U05",
        "assessment-gap",
        TRACE_GOAL,
        "array",
        None,
        ["needs_human"],
        None,
        None,
        [
            "过程已经教过；题目仅测最终算术而不要求过程知识，准确说明已教未考，不虚构事实错误。"
        ],
    ),
    (
        "U06",
        "complete",
        TRACE_GOAL,
        "array",
        None,
        ["pass"],
        None,
        None,
        ["状态0→4→10→19、i3退出及过程题完整；无附带误报或未决。"],
    ),
    (
        "U07",
        "distributed",
        TRACE_GOAL,
        "array",
        None,
        ["pass"],
        None,
        None,
        [
            "状态在代码步骤，退出在q2解析，过程问题完整；没有先教再考承诺，不强求重复或时序。"
        ],
    ),
    (
        "U08",
        "prerequisite",
        "用C学习单链表头插法。",
        "linked-list-insertion",
        None,
        ["pass"],
        None,
        None,
        [
            "显式recommended授权c-pointer先修，本节不承诺完成头插；未知画像不单独拦截，无动画承诺。",
            "value存活时读取*p=21，返回int值不是局部地址，不虚构悬垂指针。",
        ],
    ),
    (
        "R01",
        "scene-scope",
        "讲解场景仅解释数组长度与下标；代码场景给出求和实现，练习场景提供题目。",
        "array",
        "explanation",
        ["pass"],
        None,
        None,
        ["只审核讲解本身概念和承诺，不要求提供分配给兄弟场景的完整代码或练习。"],
    ),
    (
        "R02",
        "unknown-profile",
        "用通用易读语言讲解C指针的取地址、解引用和返回值，不对未提供的个人掌握度作判断。",
        "c-pointer",
        "explanation",
        ["pass"],
        None,
        None,
        [
            "通用讲解事实正确且无个性化断言，不因缺少细分画像而转人工，不推断已掌握或不会。"
        ],
    ),
    (
        "R03",
        "code-contradiction",
        "用固定数组的首元素读取函数展示下标0和返回值，接口与注释必须一致。",
        "array",
        "code",
        ["revise", "reject"],
        "fact",
        "major",
        [
            "源码返回a[0]=4，注释却声称最后元素9；仅非安全事实矛盾，读取合法，无虚构内存问题。",
            "现资源契约未规定此类真实major事实错误必须revise或必须reject，预冻结两者均可；禁止pass/needs_human。此组不自动修正。",
        ],
    ),
    (
        "R04",
        "answer-contradiction",
        "用三个判断题检查数组求和、合法下标以及返回与打印的区别。",
        "array",
        "exercise",
        ["revise", "reject"],
        "fact",
        "major",
        [
            "q1命题4+6+9=19成立，解释也写应答T，但答案字段F；具体检出，不把它仅说成过程考查不足。",
            "预冻结资源revise/reject均可，pass/needs_human不可；不启动修正，不编造兄弟资源缺口。",
        ],
    ),
)

GOALS = (
    (
        "A01",
        "array",
        "用C实现数组{7,2,5}的求和，明确逐轮s和i、首次条件失败与不访问a[3]；给出讲解、完整可编译程序（含main调用）、恰好三道要求推演过程的题及答案解析，不要动画。",
        [
            "s:0→7→9→14；首次失败i=3；返回14与打印区分",
            "三题实际要求过程知识，不能仅问7+2+5",
        ],
    ),
    (
        "A02",
        "linked-list-insertion",
        "主题是无头结点单链表头插法，C语言，空链表依次头插3和8。用int push_front(Node **head,int value)返回1成功/0失败；malloc失败不改变旧链表。提供讲解、含main和完整释放的可编译程序、恰好三道过程题及解析。指针和分配仅是配套要求，不另选教学主题；不需要动画。",
        [
            "链表[]→[3]→[8,3]，首/次分配失败分别保持[]/[3]，不丢旧头",
            "malloc检查、next/头指针顺序、调用返回约定与完整释放正确；不得只凭局部NULL检查断言调用方安全",
        ],
    ),
    (
        "A03",
        "stack",
        "用C实现容量3、top表示元素数的数组栈，演示依次入栈4、11再出栈一次。提供讲解、含main的完整程序、恰好三道过程题及解析。明确空栈不读数组、满栈不写出容量，top与返回值的变化；不需要动画。",
        [
            "top:0→1→2→1，pop返回11，合法下标0..2",
            "空/满检查和失败不改状态，先减后读或先读top-1再减均可，不虚构唯一合法形式",
        ],
    ),
    (
        "A04",
        "circular-queue",
        "用C实现容量4的循环队列，front指下一读取位置、rear指下一写入位置、size表示元素数，初始均0。入队5、9、11、13，出队一次，再入队17。提供讲解、含main完整程序、恰好三道过程题及解析；追踪回绕并以size区分空满，失败不改状态；无需动画。",
        [
            "首次四次入队后front0/rear0/size4；出队5后front1/size3；再入17后front1/rear1/size4",
            "最终逻辑顺序9,11,13,17；空size0/满size4，front==rear不单独判空；所有下标取模4",
        ],
    ),
)


async def capture_case(case):
    scope = case["scope"]
    cs = candidates(case)
    chosen = (
        cs
        if scope == "unit"
        else tuple(c for c in cs if c.role == case["selected_role"])
    )
    m = case["material"]
    payload = (
        {"unit": m, "reference_context": m["reference_context"]}
        if scope == "unit"
        else {
            "plan": m["plan"],
            "candidate": chosen[0].payload(),
            "reference_context": m["reference_context"],
        }
    )
    router, gen, wires, targets = offline_router(valid_review(scope))
    record = await review_once(
        router,
        CallWindow(),
        binding=m["binding"],
        target_digest=m["unit_digest"] if scope == "unit" else chosen[0].content_digest,
        payload=payload,
        candidates=chosen,
        scope=scope,
        input_snapshot=case["input_snapshot"],
    )
    assert not gen and len(wires) == 1
    body = json.loads(wires[0])
    assert body["model"] == CONFIG.review_model and body["reasoning"] == {
        "effort": "high"
    }
    assert body["max_output_tokens"] == 8192 and body["temperature"] == 0
    assert targets[0]["host"] == targets[0]["sni"] == "www.cbbb.fun"
    return dict(
        wire_hex=wires[0].hex(),
        wire_sha256=sha(wires[0]),
        wire_bytes=len(wires[0]),
        scope=scope,
        anchor_catalog=record["anchor_catalog"],
        business_schema=review_output_schema(
            scope, anchor_ids=[a["anchor_id"] for a in record["anchor_catalog"]]
        ),
        target=targets[0],
        evidence_type="offline real adapter MockTransport capture, NOT live result or semantic pass",
    )


async def build():
    files, index, labels = {}, [], {}
    for name, node, goal, checks in GOALS:
        i = input_for(name, node, goal)
        router, wires, reviews, targets = offline_router(draft_for(i, "complete"))
        # The scripted plan is NOT a generated course or a gold output. Only the request is kept.
        await generate_shared_plan(router, i, CallWindow())
        assert len(wires) == 1 and not reviews
        body = json.loads(wires[0])
        assert (
            body["model"] == "deepseek-flash"
            and body["reasoning"] == {"effort": "none"}
            and body["max_output_tokens"] == 2048
        )
        value = dict(
            id=name,
            kind="generation_input",
            original_request=goal,
            input_snapshot=i.snapshot(),
            reference_context=i.reference_context,
            expected_checklist=checks,
            generated_material=None,
            actual_model_result=None,
            provenance="GPT authored input and acceptance checklist; not an existing generated course or independently human-scored sample",
        )
        files[f"cases/{name}.json"] = value
        files[f"requests/{name}-plan.json"] = dict(
            wire_hex=wires[0].hex(),
            wire_sha256=sha(wires[0]),
            target=targets[0],
            future_child_wires="depend on real parent outputs, not yet known/frozen",
            evidence_type="offline MockTransport first-plan request only; scripted output discarded",
        )
        index.append(
            dict(
                id=name,
                kind=value["kind"],
                case_path=f"cases/{name}.json",
                case_sha256=sha(canonical(value)),
                request_path=f"requests/{name}-plan.json",
            )
        )
        labels[name] = dict(
            expected_verdicts=None,
            full_generation_required=True,
            checklist=checks,
            actual_result=None,
            label_author="Codex GPT plus static facts, not independent human truth",
        )
    for (
        name,
        kind,
        goal,
        node,
        role,
        expected,
        category,
        severity,
        required,
    ) in REVIEW_SPECS:
        case = await make_case(name, kind, goal, node, role=role)
        req = await capture_case(case)
        files[f"cases/{name}.json"] = case
        files[f"requests/{name}.json"] = req
        index.append(
            dict(
                id=name,
                kind=case["scope"] + "_review",
                case_path=f"cases/{name}.json",
                case_sha256=sha(canonical(case)),
                request_path=f"requests/{name}.json",
                wire_sha256=req["wire_sha256"],
            )
        )
        labels[name] = dict(
            scope=case["scope"],
            selected_role=role,
            expected_verdicts=expected,
            required_category=category,
            expected_severity=severity,
            required_findings=required,
            all_claims_and_citations_required=True,
            allowed_unresolved="specific frozen teaching gaps"
            if name in ("U03", "U04", "U05")
            else "none unless evidence-based independently documented; never enough to pass",
            actual_result=None,
            label_author="Codex GPT plus static mathematical/program facts; no independent human signature",
        )
    files["case-index.json"] = dict(
        frozen_case_count=16,
        real_requests_authorized=0,
        entries=index,
        generation_outputs_frozen=False,
        explanation="Four complete input tasks plus twelve full fixed review fixtures; actual course outputs only after authorized live run",
    )
    files["labels.json"] = dict(
        version="five-hour-gpt-prelabels-v1",
        label_method="GPT-authored plus static reasoning; no runtime execution or independent human truth",
        labels=labels,
    )
    return files


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    files = asyncio.run(build())
    for relative, value in files.items():
        path = BASE / relative
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.write:
            if path.exists() and path.read_text() != raw:
                raise ValueError("REFUSE_OVERWRITE_FROZEN_MATERIAL")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(raw)
        elif path.read_text() != raw:
            raise ValueError("MATERIAL_CHANGED")
    print(
        json.dumps(
            dict(
                mode="offline material preparation/check only",
                cases=16,
                captured_review_requests=12,
                captured_plan_inputs=4,
                provider_calls=0,
            )
        )
    )


if __name__ == "__main__":
    main()
