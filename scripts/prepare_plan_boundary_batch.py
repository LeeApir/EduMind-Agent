"""Prepare the sole bounded development batch; no credentials or real transport."""

# ruff: noqa: E402
import argparse
import asyncio
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
from acceptance_support.plan_admission import offline_router
from acceptance_support.five_hour_runtime import write_once
from acceptance_support.qwen_review_budget import sha
from app.agents.plan_check import CHECKS, inspect_plan
from app.agents.shared_learning_plan import CallWindow
from app.models.learning_plan import LearningPlanVersion
from app.services.knowledge_graph import default_knowledge_graph_repository
from app.services.learning_contract import digest
from app.services.learning_policy import POLICY, POLICY_VERSION, active_policy_digest
from app.services.plan_check import verify_review_input

BASE = ROOT / "docs/acceptance/phase-1-plan-boundary-development-r01"
SOURCE = ROOT / "docs/acceptance/phase-1-plan-admission-preparation-r01/materials/plan"
ORDER = [f"D{i:02}" for i in range(1, 9)]


def read(path):
    return json.loads(path.read_bytes())


def row_for(case):
    from uuid import UUID

    b = case["server_binding"]
    s = case["input_snapshot"]
    p = case["plan"]
    return LearningPlanVersion(
        id=UUID(b["plan_id"]),
        user_id=UUID(b["owner_id"]),
        learning_unit_id=UUID(b["unit_id"]),
        origin_operation_id=UUID(b["origin_operation_id"]),
        version=b["plan_version"],
        schema_version="learning-plan-v1",
        plan_json=deepcopy(p),
        input_snapshot=deepcopy(s),
        references_snapshot=deepcopy(s["references"]),
        policy_snapshot=deepcopy(POLICY),
        policy_version=POLICY_VERSION,
        plan_digest=digest("plan", "learning-plan-v1", plan=p),
        input_digest=digest("input", "learning-input-v1", snapshot=s),
        references_digest=digest(
            "references", "learning-references-v1", references=s["references"]
        ),
        policy_digest=active_policy_digest(),
    )


def expected_binding(case):
    from uuid import UUID

    return {
        k: UUID(v)
        if k
        in ("owner_id", "unit_id", "operation_id", "origin_operation_id", "plan_id")
        else v
        for k, v in case["server_binding"].items()
    }


def attach_binding(case):
    identities = {
        k: str(
            uuid5(
                NAMESPACE_URL,
                "edumind:plan-boundary-development-r01:" + case["id"] + ":" + k,
            )
        )
        for k in ("owner_id", "unit_id", "operation_id", "plan_id")
    }
    identities["origin_operation_id"] = identities["operation_id"]
    identities["plan_version"] = 1
    case["server_binding"] = identities
    row = row_for(case)
    identities.update(
        plan_digest=row.plan_digest,
        input_digest=row.input_digest,
        reference_digest=row.references_digest,
        policy_digest=row.policy_digest,
    )
    return case


def new_case(id, node_id, goal, state, input_description, steps, conventions):
    base = read(SOURCE / "P01.json")
    g = default_knowledge_graph_repository()
    node = asdict(g.get_node(node_id))
    rid = f"graph-node:{g.graph_version}:{node_id}"
    ref = dict(
        reference_id=rid,
        version=g.graph_version,
        digest=digest("graph-node", "graph-reference-v1", node=node),
    )
    metadata = dict(
        node_id=node_id,
        graph_version=g.graph_version,
        graph_digest=digest(
            "graph", "graph-snapshot-v1", nodes=[asdict(n) for n in g.all_nodes()]
        ),
        profile_version=None,
        profile_evidence_digest=digest(
            "profile-evidence", "profile-evidence-v1", evidence={}
        ),
        goal=goal,
        code_language="C",
    )
    plan = deepcopy(base["plan"])
    plan.update(metadata)
    plan.update(
        objectives=[dict(id="core", text=goal)],
        prerequisite_node_ids=[],
        references=[ref],
        conventions=conventions,
        shared_example=dict(
            initial_state=state, input_description=input_description, steps=steps
        ),
        terminology=[
            dict(
                term="本例",
                meaning="仅按明确的本节原文和示例承诺审核，不将背景自动视为完整节点要求。",
            )
        ],
    )
    plan["scenes"] = [
        dict(
            scene_key=role,
            role=role,
            objective_ids=["core"],
            depends_on=[]
            if i == 0
            else ["explanation"]
            if i == 1
            else ["explanation", "code"],
        )
        for i, role in enumerate(("explanation", "code", "exercise"))
    ]
    snap = dict(
        metadata=metadata,
        references={rid: deepcopy(ref)},
        node_ids=[n.id for n in g.all_nodes()],
        learner_evidence={},
        reference_context=dict(
            source=deepcopy(ref),
            node=node,
            scope="Partial background, not extra mandatory goals.",
        ),
    )
    return dict(
        id=id,
        kind="development_plan_review",
        source="new authored development control, not H or independent truth",
        input_snapshot=snap,
        plan=plan,
    )


def materials():
    old = read(SOURCE / "P01.json")
    d1 = dict(
        id="D01",
        kind="development_plan_review",
        source="existing exposed P01 correct control, content unchanged",
        input_snapshot=deepcopy(old["input_snapshot"]),
        plan=deepcopy(old["plan"]),
    )
    d2 = new_case(
        "D02",
        "stack",
        "用C实现容量3、top表示元素数的数组栈。演示依次push(4)、push(11)、pop一次，返回11且top变1；讲解、完整程序及三道过程题，说明空栈不读、满栈不写。不要求动画。",
        "top=0；a有3个有效槽位",
        "容量3；依次push(4)、push(11)、pop一次",
        [
            dict(
                operation="push(4)：检查top<3后a[top]=4，再top++",
                expected_state="top=1，a[0]=4",
                expected_output="无打印",
            ),
            dict(
                operation="push(11)：检查top<3后a[top]=11，再top++",
                expected_state="top=2，a[1]=11",
                expected_output="无打印",
            ),
            dict(
                operation="pop：先检查top>0；--top后返回a[top]",
                expected_state="top=1",
                expected_output="返回a[1]=11",
            ),
        ],
        dict(
            index_base=0,
            capacity=3,
            state_representation="top为元素数。空top==0，满top==3；失败的操作不访问数组。",
            not_applicable_reasons=[],
        ),
    )
    d3 = new_case(
        "D03",
        "linked-list-insertion",
        "用C展示单链表头插。所有节点均在同一个main函数内存续：n0值4、n1值11，初始head=&n0且n0.next=NULL，p=&n1。先p->next=head再head=p，得到11到4。给出讲解、完整程序与三道过程题，只讲此具体状态，不要求动态分配或动画。",
        "n0.value=4,n0.next=NULL；n1.value=11,n1.next=NULL；head=&n0,p=&n1；全部在main使用结束前存续。",
        "在main内对这两个有效节点执行一次头插",
        [
            dict(
                operation="p->next=head",
                expected_state="n1.next=&n0；head仍为&n0",
                expected_output="无打印",
            ),
            dict(
                operation="head=p",
                expected_state="head=&n1；链为n1→n0→NULL",
                expected_output="遍历次序11、4",
            ),
        ],
        dict(
            index_base=None,
            capacity=None,
            state_representation="head/p保存节点地址，next连接有效对象；不返回局部节点地址。",
            not_applicable_reasons=[
                "本例非下标容器，未定义数组下标。",
                "节点对象数为2但不是数组容量参数。",
            ],
        ),
    )
    d4 = new_case(
        "D04",
        "circular-queue",
        "用C解释容量3的循环队列，以size区分空满，head指下一读取位置、tail指下一写入位置。演示入队4、入队11、出队一次返回4。说明空队列不读、满队列不写；讲解、完整程序及三道过程题，不要求动画。",
        "head=0,tail=0,size=0；a有3个槽位",
        "依次enqueue(4)、enqueue(11)、dequeue一次",
        [
            dict(
                operation="enqueue(4)：size<3时写a[tail]，tail=(tail+1)%3，size++",
                expected_state="head=0,tail=1,size=1；a[0]=4",
                expected_output="无打印",
            ),
            dict(
                operation="enqueue(11)：size<3时写a[tail]，tail=(tail+1)%3，size++",
                expected_state="head=0,tail=2,size=2；a[1]=11",
                expected_output="无打印",
            ),
            dict(
                operation="dequeue：size>0时取a[head]，head=(head+1)%3，size--",
                expected_state="head=1,tail=2,size=1",
                expected_output="返回4",
            ),
        ],
        dict(
            index_base=0,
            capacity=3,
            state_representation="head是下一读、tail是下一写，size范围0..3；size==0空、size==3满。",
            not_applicable_reasons=[],
        ),
    )
    d5 = deepcopy(d1)
    d5.update(
        id="D05", source="derived development contradiction; original request unchanged"
    )
    d5["plan"]["objectives"][0]["text"] = d5["plan"]["objectives"][0]["text"].replace(
        "返回19", "返回17"
    )
    d6 = deepcopy(d2)
    d6.update(
        id="D06",
        source="derived development LIFO contradiction; original request unchanged",
    )
    d6["plan"]["shared_example"]["steps"][-1]["expected_output"] = "返回a[0]=4"
    d7 = deepcopy(d1)
    d7.update(
        id="D07",
        source="derived reachable unsafe plan; not a safe-counterexample lesson",
    )
    d7["plan"]["shared_example"]["steps"].insert(
        0,
        dict(
            operation="求和程序第一步无条件执行x=a[4]，然后才进入求和循环；a仅有3元素",
            expected_state="发生可达越界，后续行为不受保证",
            expected_output="不保证数值或正常返回",
        ),
    )
    missing = read(SOURCE / "P03.json")
    d8 = dict(
        id="D08",
        kind="development_plan_review",
        source="existing exposed missing-input control P03, content unchanged",
        input_snapshot=deepcopy(missing["input_snapshot"]),
        plan=deepcopy(missing["plan"]),
    )
    return [attach_binding(x) for x in [d1, d2, d3, d4, d5, d6, d7, d8]]


def labels():
    return {
        **{
            f"D{i:02}": dict(
                model_verdicts=["pass"],
                routes=["accept_plan"],
                required="干净pass；全部原文/计划关系正确，无虚构额外要求或附带误报。",
            )
            for i in range(1, 5)
        },
        "D05": dict(
            model_verdicts=["issue", "needs_human"],
            routes=["needs_human"],
            required="具体指出原要求/轨迹19与计划目标17矛盾；不得把17归给用户，不得虚构安全理由。",
        ),
        "D06": dict(
            model_verdicts=["issue", "needs_human"],
            routes=["needs_human"],
            required="具体指出后进先出应返回a[1]=11，计划却称a[0]=4；不得遗漏冲突或夸大为可达UB。",
        ),
        "D07": dict(
            severe_control=True,
            model_verdicts=["reject"],
            routes=["reject"],
            required="具体检出长度3却无条件访问a[4]的可达越界，unsafe_plan/severe；不得推导UB确定数值。",
        ),
        "D08": dict(
            model_verdicts=["needs_human"],
            routes=["needs_human", "clarify_user"],
            required="指出附件/指定输入缺失，转人工或明确向用户索取材料；不能核验19，也不能断言确定非19或臆造输入。",
        ),
    }


async def capture(case):
    row = row_for(case)
    expected = expected_binding(case)
    verify_review_input(row, row.origin_operation_id, expected)
    value = dict(
        schema_version="plan-review-result-v1",
        verdict="pass",
        coverage=dict(checked=CHECKS, unchecked=[]),
        findings=[],
        unresolved=[],
    )
    gateway, wires = offline_router([value])
    record = await inspect_plan(
        gateway, CallWindow(), row, row.origin_operation_id, expected_binding=expected
    )
    assert len(wires) == 1 and wires[0]["role"] == "review"
    return dict(
        case_id=case["id"],
        provider_calls=0,
        semantic_evaluated=False,
        scope="synthetic clean reply captures actual outbound route/schema only, not a grade",
        wire=wires[0],
        exact_wire_sha256=sha(
            json.dumps(
                wires[0]["body"],
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ),
        server_anchors=record["anchor_catalog"],
    )


def prepare():
    if (BASE / "manifest.json").exists():
        raise ValueError("FROZEN_PACKAGE_CANNOT_REWRITE")
    BASE.mkdir(parents=True, exist_ok=True)
    index = []
    labs = labels()
    for case in materials():
        path = BASE / f"materials/{case['id']}.json"
        path.parent.mkdir(exist_ok=True)
        write_once(path, case)
        probe = asyncio.run(capture(case))
        p = BASE / f"captures/{case['id']}.json"
        p.parent.mkdir(exist_ok=True)
        write_once(p, probe)
        index.append(
            dict(
                id=case["id"],
                material=str(path.relative_to(ROOT)),
                sha256=sha(path.read_bytes()),
                prelabel=labs[case["id"]],
                independent_signoff="pending_Lee_for_this_batch",
                use="development_only_not_H_or_formal_denominator",
            )
        )
    write_once(
        BASE / "index.json",
        dict(order=ORDER, candidate_count=1, items=index, real_requests_authorized=0),
    )
    write_once(
        BASE / "budget.json",
        dict(
            requests_max=8,
            per_case=1,
            output_per_request=8192,
            output_cap_sum=65536,
            input_tokens_max=None,
            fees="unlimited user policy; accurate new request count not yet approved",
            per_request_seconds=60,
            case_seconds=180,
            wall_seconds=3600,
            automatic_retries=0,
            fallbacks=0,
            semantic_failure="retain failure; collect remaining fixed controls once to observe both false blocks and misses; no adaptation",
            technical_failure="immediate stop, no automatic retry",
            real_requests_authorized=0,
        ),
    )
    print(json.dumps(dict(materials=8, provider_calls=0, requests_proposed=8)))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare"])
    p.parse_args()
    prepare()
