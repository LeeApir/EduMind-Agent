"""Reproduce complete v4.9 fixtures offline; no live authority or model labels."""

# ruff: noqa: E402
import json
import sys
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
from acceptance_support.om_diagnostic import inputs, plan_draft, Capture, valid_review
from app.agents.shared_learning_plan import generate_shared_plan, CallWindow
from app.agents.planned_scene_generation import PlannedScenes
from app.agents.hybrid_resource_review import review_once
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.unit_material import unit_material
from app.services.teaching_actions import assemble_actions
from app.services.teaching_binding import select_teaching_context
from app.services.knowledge_graph import default_knowledge_graph_repository
import asyncio

BASE = ROOT / "docs/acceptance/phase-1-luna-v49-admission-r02"


def uid(s):
    return str(uuid5(NAMESPACE_URL, "luna-v49-admission-r01:" + s))


def quiz(q, a, e, n):
    return dict(
        id=f"q{n}",
        question="[判断题] " + q + " 仅填 T 或 F（T=正确，F=错误）。",
        answer=a,
        explanation=e,
    )


def content(kind):
    code = "int total(void) {\n    int a[3] = {3, 8, 4};\n    int s = 0;\n    for (int i = 0; i < 3; ++i) s += a[i];\n    return s;\n}\n"
    trace = "开始s=0；i=0后s=3，i=1后s=11，i=2后s=15；随后i=3，i<3为假，退出，返回15。"
    md = (
        "本节仅追踪一个数组求和过程，不承诺覆盖整个数组节点。函数total返回15；没有打印。"
        + trace
    )
    steps = ["处理下标0、1、2，分别累加。", "在i=3时退出，返回累计和。"]
    items = [
        quiz("i=1这一轮结束后s=11", "T", "初始0，先加3，再加8，得到11。", 1),
        quiz("退出时i=3且条件i<3为假", "T", "第三轮后下标递增到3，退出。", 2),
        quiz("此函数会将返回值打印到屏幕", "F", "没有打印语句，返回值交给调用方。", 3),
    ]
    if kind == "distributed":
        md = "total求和数组{3,8,4}，返回15，不打印。过程见代码关键步骤与练习解析。"
        steps = [trace]
    if kind in ("teaching-gap", "mixed"):
        md = "total处理数组{3,8,4}，无打印语句。"
        steps = ["按实现运行。"]
        items = [
            quiz("3+8+4=15", "T", "算术总和是15。", 1),
            quiz("数组长度是3", "T", "声明长度3。", 2),
            quiz("函数中存在打印语句", "F", "没有打印语句。", 3),
        ]
    if kind == "assessment-gap":
        items = [
            quiz("3+8+4=15", "T", "算术总和15。", 1),
            quiz("数组长度是3", "T", "长度3。", 2),
            quiz("函数打印15", "F", "函数不打印。", 3),
        ]
    if kind == "fact":
        md = md.replace("函数total返回15", "函数total返回17")
    if kind == "full-node":
        md = md.replace("本节仅追踪一个数组求和过程，不承诺覆盖整个数组节点。", "")
        md += "本节承诺完整覆盖数组基本操作，包括插入和删除。"
    if kind in ("safety", "mixed"):
        code = "int total(void) {\n    int a[3] = {3, 8, 4};\n    return a[5];\n}\n"
        md = "本节用total处理数组{3,8,4}，无打印语句。" + (
            trace if kind == "safety" else ""
        )
    if kind == "safety":
        code = "int total(void) {\n    int a[3]={3,8,4}; int s=0;\n    for(int i=0;i<3;++i) s+=a[i];\n    return s;\n}\nint extra(void) { int a[3]={3,8,4}; return a[5]; }\n"
        md = "total返回15，不打印。" + trace + "配套extra是另一个可直接调用的取值函数。"
    if kind.startswith("stack"):
        code = "int top_value(void) {\n    int a[2] = {6, 9};\n    int top = 0;\n    a[top++] = 6;\n    a[top++] = 9;\n    return a[--top];\n}\n"
        md = "定长栈只做这两次入栈、一次出栈，不是可任意调用的通用接口。top从0到1到2，出栈先减到1，取a[1]=9，返回9，无打印；这组有限操作始终在容量2内。"
        steps = ["top表示元素数，也是下一写入位置；先减后取符合后进先出。"]
        items = [
            quiz("第二次入栈后top=2", "T", "两次递增得到2。", 1),
            quiz("出栈先令top=1再取a[1]", "T", "前置递减先执行。", 2),
            quiz("此次出栈返回最早放入的6", "F", "返回后放入的9。", 3),
        ]
        if kind == "stack-fact":
            md = md.replace("返回9，无打印", "返回6，无打印")
        if kind == "stack-safety":
            code = code.replace("a[--top]", "a[top]")
            md = "仅执行给定两次入栈和一次读取。top由0到1到2；读取a[top]。"
            steps = ["top表示已存元素数；代码本次直接读取a[top]。"]
            items = [
                quiz("两次入栈后top=2", "T", "两个后置递增使top由0到2。", 1),
                quiz("长度2的数组允许读取a[2]", "F", "合法下标只有0和1。", 2),
                quiz("代码包含打印语句", "F", "没有打印语句。", 3),
            ]
    if kind == "prerequisite":
        code = "int pointer_value(void) {\n    int value = 12;\n    int *p = &value;\n    return *p;\n}\n"
        md = "本节只补C指针先修：p存value地址，*p读取12，返回12，不打印。本节尚未实现链表头插法，原目标留待后续。"
        steps = ["取地址后解引用；p始终指向仍存活的局部value，读取发生在返回之前。"]
        items = [
            quiz("p保存value的地址", "T", "&value取地址。", 1),
            quiz("*p在本次读取为12", "T", "value已初始化为12。", 2),
            quiz(
                "这一小节已经交付完整链表头插程序",
                "F",
                "当前仅是授权的指针先修小节。",
                3,
            ),
        ]
    return {
        "explanation": {"markdown": md},
        "code": dict(
            language="C",
            source=code,
            expected_output="无标准输出；由调用方获取返回值。",
            key_steps=steps,
            display_only=True,
        ),
        "exercise": {"items": items},
    }


async def build():
    cases = {}
    labels = []
    specs = [
        ("screen-complete", "complete", "pass"),
        ("screen-distributed", "distributed", "pass"),
        ("screen-teaching-gap", "teaching-gap", "needs_human"),
        ("screen-assessment-gap", "assessment-gap", "needs_human"),
        ("screen-fact", "fact", "reject"),
        ("screen-safety", "safety", "reject"),
        ("screen-mixed", "mixed", "reject"),
        ("screen-full-node-promise", "full-node", "needs_human"),
        ("holdout-stack-complete", "stack", "pass"),
        ("holdout-stack-fact", "stack-fact", "reject"),
        ("holdout-stack-safety", "stack-safety", "reject"),
        ("holdout-prerequisite", "prerequisite", "pass"),
    ]
    for name, kind, expected in specs:
        i = inputs()
        graph = default_knowledge_graph_repository()
        owner = uid(name + ":owner")
        node = "stack" if kind.startswith("stack") else "array"
        goal = "用C实现并明确追踪数组{3,8,4}求和循环的关键状态和退出条件，并用题目检查是否掌握这个过程。"
        if kind.startswith("stack"):
            goal = "用C展示容量2的栈依次入栈6、9和一次出栈，明确追踪top和返回值，并用题目检查操作过程。"
        if kind == "prerequisite":
            node = "linked-list-insertion"
            goal = "用C学习单链表头插法。"
        path = SimpleNamespace(
            id=uid(name + ":path"),
            user_id=__import__("uuid").UUID(owner),
            target_node_id=node,
            current_node_id="c-pointer" if kind == "prerequisite" else node,
            nodes=[{"node_id": node}]
            + ([{"node_id": "c-pointer"}] if kind == "prerequisite" else []),
            version=1,
            graph_version=graph.graph_version,
        )
        tc = select_teaching_context(
            owner_id=path.user_id,
            target_node_id=node,
            original_request=goal,
            mode="recommended" if kind == "prerequisite" else "target",
            graph=graph,
            path=path,
        )
        actual = next(
            n
            for n in json.loads((ROOT / "data/knowledge/phase-1.1.0.json").read_text())[
                "nodes"
            ]
            if n["id"] == tc["teaching_node_id"]
        )
        rid = f"graph-node:{graph.graph_version}:{actual['id']}"
        ref = dict(
            reference_id=rid,
            version=graph.graph_version,
            digest=digest("graph-node", "graph-reference-v1", node=actual),
        )
        i = replace(
            i,
            metadata={
                **i.metadata,
                "node_id": tc["teaching_node_id"],
                "goal": tc["segment_goal"],
                "graph_version": tc["graph_version"],
                "graph_digest": tc["graph_digest"],
            },
            references={rid: ref},
            reference_context={
                "source": ref,
                "node": actual,
                "learner_evidence": {},
                "scope": "Background only; not proof of this example.",
            },
            teaching_context=tc,
        )
        draft = plan_draft(i)
        draft["objectives"] = [dict(id="local", text=i.metadata["goal"])]
        draft["reference_ids"] = [rid]
        for s in draft["scenes"]:
            s["objective_ids"] = ["local"]
        draft["shared_example"] = dict(
            input_description="精确示例见学生代码",
            initial_state="见代码初始化",
            steps=[
                dict(
                    operation="独立跟踪代码",
                    expected_state="内部计划不是已交付教学",
                    expected_output="不打印",
                )
            ],
        )
        draft["terminology"] = [
            dict(term="返回值", meaning="函数交给调用方的值，不等于打印")
        ]
        draft["conventions"]["capacity"] = 2 if kind.startswith("stack") else 3
        if kind == "prerequisite":
            draft["conventions"].update(
                index_base=None,
                capacity=None,
                not_applicable_reasons=["标量指针取值示例不涉及容器容量或下标。"],
            )
        draft["conventions"]["state_representation"] = (
            "s为已处理元素总和，i为下一处理下标"
            if node == "array"
            else "top为已存元素数"
            if node == "stack"
            else "p存value地址"
        )
        draft["shared_example"] = dict(
            input_description="a={3,8,4}"
            if node == "array"
            else "入栈6、9"
            if node == "stack"
            else "value=12",
            initial_state="s=0,i=0"
            if node == "array"
            else "top=0"
            if node == "stack"
            else "value初始化12",
            steps=[
                dict(
                    operation="执行固定示例",
                    expected_state="s为3、11、15，i=3退出"
                    if node == "array"
                    else "top为1、2、1"
                    if node == "stack"
                    else "p=&value，*p=12",
                    expected_output="无打印，返回15"
                    if node == "array"
                    else "无打印，返回9"
                    if node == "stack"
                    else "无打印，返回12",
                )
            ],
        )
        plan = await generate_shared_plan(Capture(draft), i, CallWindow())
        b = {
            k: uid(name + ":" + k)
            for k in ("owner_id", "unit_id", "operation_id", "plan_id")
        }
        b.update(
            owner_id=owner,
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
            plan, b, reference_context=i.reference_context, input_snapshot=i.snapshot()
        )
        for role, c in content(kind).items():
            with patch(
                "app.agents.planned_scene_generation.uuid4",
                return_value=uid(name + ":" + role),
            ):
                staged = w.stage(
                    role,
                    dict(
                        resource_type=role,
                        prompt_version="learning-resources-v1",
                        content=c,
                    ),
                )
            w.disposition(
                role, staged.id, "pass"
            )  # fixture construction only, not model results
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
        m = unit_material(w, scenes, assemble_actions(w.candidates()))
        cap = Capture(valid_review("unit"))
        await review_once(
            cap,
            CallWindow(),
            binding=b,
            target_digest=m["unit_digest"],
            payload={"unit": m, "reference_context": w.reference_context},
            candidates=w.candidates(),
            scope="unit",
            input_snapshot=i.snapshot(),
        )
        # Capture's scripted pass exercises local protocol, never becomes a diagnostic result.
        cases[name] = dict(
            material=m,
            input_snapshot=i.snapshot(),
            fixture_kind=kind,
            provenance="new authored fixture; never used to tune current v4.9",
            scope="unit",
        )
        want = []
        if kind in ("fact", "stack-fact"):
            want = ["指出返回值声明与实际程序矛盾，引用声明和程序；不得编造其他缺陷。"]
        if kind in ("safety", "mixed", "stack-safety"):
            want = [
                "指出实际可达越界及精确长度/索引；不得从未定义行为推出必然不等于某个数值。"
            ]
        if kind == "mixed":
            want += [
                "程序未实现原始目标承诺的求和循环；这是实际交付缺口，须具体说明，不能误记为附带误报。"
            ]
        if kind == "stack-safety":
            want += [
                "本例未递减top，也未完成所承诺的出栈/返回值教学；该真实目标缺口须保留具体说明，不计附带误报。"
            ]
        if kind in ("teaching-gap", "mixed"):
            want += [
                "具体说明学生可见关键状态/退出教学不足，以及题目未考查过程；内部计划不算交付。"
            ]
        if kind == "full-node":
            want = [
                "指出显式完整基本操作承诺中的插入/删除没有交付，不能只按局部求和目标放行；不将缺教学编造为fact。"
            ]
        if kind == "assessment-gap":
            want = [
                "已教状态与退出边界，准确指出仅测最终值/长度而未测过程；不得声称未教。"
            ]
        if expected == "pass":
            want = ["所有必检ID齐全，findings/unchecked/unresolved均为空；无附带误报。"]
        labels.append(
            dict(
                id=name,
                phase="holdout" if name.startswith("holdout") else "screen",
                material_sha256=__import__("hashlib")
                .sha256(
                    json.dumps(
                        cases[name],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                )
                .hexdigest(),
                expected_local_verdict=expected,
                required_claims=want,
                all_claims_and_all_anchors_must_be_supported=True,
                independent_human_status="pending",
                model_result=None,
            )
        )
    return cases, {
        "labels": labels,
        "authorship": "Codex draft; not independent signoff",
        "holdout_definition": "newly authored after v4.9 freeze, disjoint from earlier fixes; visible to preparer, not statistically blind to preparer",
        "real_calls": 0,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    cases, labels = asyncio.run(build())
    for name, value in (("cases.json", cases), ("proposed-labels.json", labels)):
        raw = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        if args.write:
            if (BASE / "manifest.json").exists() and (BASE / name).read_text() != raw:
                raise ValueError("FROZEN_PACKAGE_IMMUTABLE")
            (BASE / name).write_text(raw)
        elif (BASE / name).read_text() != raw:
            raise SystemExit("MATERIAL_FREEZE_CHANGED: " + name)
    print("12 complete materials reproduced; independent labels pending; real calls 0")
