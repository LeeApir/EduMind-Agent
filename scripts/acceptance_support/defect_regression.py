"""Authored 4x3 diagnostic fixtures; no network, semantic oracle or production changes."""

from copy import deepcopy
from unittest.mock import patch

from acceptance_support.om_diagnostic import Capture
from prepare_five_hour_materials import contents, draft_for, input_for, quiz, uid

from app.agents.planned_scene_generation import PlannedScenes
from app.agents.shared_learning_plan import CallWindow, generate_shared_plan
from app.services.learning_contract import digest
from app.services.learning_policy import active_policy_digest
from app.services.teaching_actions import assemble_actions
from app.services.unit_material import unit_material

FAMILIES = ("pointer-scope", "plan-consistency", "requirement-origin", "assessment-coverage")
VARIANTS = ("correct", "error", "insufficient")
BASE_GOAL = (
    "用C实现固定数组{4,6,9}求和，返回19且不打印；给出讲解、函数及三题，不要求动画或完整节点。"
)
TRACE_GOAL = (
    "用C实现数组{4,6,9}求和，逐轮解释s、i和退出边界；用三题"
    "考查过程，其中至少一题要求辨认完整逐轮状态表，不要动画。"
)
POINTER_GOAL = (
    "说明C指针形参能否清空调用方head，依据实际形参、赋值和调用点"
    "判断释放后安全；给出讲解、代码和三题。不要求数组求和或动画。"
)


def specification(family, variant):
    """Labels stay separate from the actual review payload."""
    goal = (
        TRACE_GOAL
        if family == "assessment-coverage"
        else POINTER_GOAL
        if family == "pointer-scope"
        else BASE_GOAL
    )
    d = contents("complete")
    if family != "assessment-coverage":
        # Baseline requests implementation, not a trace-measurement promise.
        d["exercise"]["items"] = [
            quiz(1, "4+6+9=19", "T", "4+6=10，再加9得19。"),
            quiz(2, "长度3数组的合法下标包括3", "F", "合法下标0、1、2。"),
            quiz(3, "return 19等于打印19", "F", "返回值不等于标准输出。"),
        ]
    label = dict(
        expected_verdict="pass" if variant == "correct" else "needs_human",
        required_claims=[],
        forbidden_claims=[
            "将模型计划承诺冒称为原始用户要求",
            "把无法保证P当作确定非P",
            "无据断言调用者悬垂或UB的确定数值",
        ],
        expected_category=None,
        expected_severity=None,
        author="Codex authored calibration labels; not independent human truth",
        actual_result=None,
    )
    overrides = {}
    if family == "plan-consistency":
        if variant == "error":
            overrides["objective"] = "实现{4,6,9}求和并返回17，不打印。"
            label["required_claims"] = [
                "计划目标17与自身轨迹/数组和19矛盾；学生代码19正确。需修正/澄清计划，不怪用户。"
            ]
        elif variant == "insufficient":
            goal = (
                "用C对长度3的有效数组求和，元素各在0..100；本次指定输入见"
                "未提供附件，请核验是否返回19。不要求完整过程测量或动画。"
            )
            overrides["objective"] = "核验指定输入求和是否为19；指定元素尚未提供，结果待核验。"
            overrides["unknown_input"] = True
            d["explanation"]["markdown"] = (
                "函数要求a指向3个有效int，元素各在0..100。每项累加，返"
                "回其和，不打印。指定输入附件缺失，不能确定该次和是否19。"
            )
            d["code"].update(
                source=(
                    "int sum_sample(const int a[3]) { int s=0; for(int i=0;i<"
                    "3;++i) s+=a[i]; return s; }"
                ),
                expected_output="依给定输入返回其和；本次指定输入未知，无打印。",
                key_steps=["a须指向3个有效int，元素0..100；下标依次0、1、2，不访问a[3]。"],
            )
            d["exercise"]["items"] = [
                quiz(
                    1,
                    "若给定输入为{4,6,9}，本函数返回19",
                    "T",
                    "这是条件示例，不是缺失附件的实际输入。",
                ),
                quiz(2, "函数自行打印结果", "F", "无打印。"),
                quiz(3, "合法读取下标为0、1、2", "T", "前提a指向3个有效int。"),
            ]
            label["required_claims"] = [
                "缺指定元素，无法核验该次和是否19；不宣布计划确定自相矛盾或一定非19。"
            ]
        else:
            label["required_claims"] = ["目标、轨迹、学生实现均为19，无计划矛盾误报。"]
    elif family == "requirement-origin":
        if variant == "error":
            overrides["objective"] = "按模型追加的承诺返回17。"
            d["explanation"]["markdown"] = "用户明确要求返回17，因此sum_sample返回17，不打印。"
            d["code"]["expected_output"] = "返回17，不打印。"
            label.update(
                expected_verdict="reject", expected_category="fact", expected_severity="major"
            )
            label["required_claims"] = [
                (
                    "原文要求19，只有计划追加17；讲解把17归给用户无据，实际求和"
                    "代码仍返回19，与讲解/预期17矛盾。"
                )
            ]
        elif variant == "insufficient":
            goal = (
                "用C实现{4,6,9}求和，另按我提到但未提交的附件检查附加输出"
                "要求；当前没有附件正文。不要求动画或完整状态测量。"
            )
            overrides["objective"] = "实现求和返回19，不打印；附加输出要求需取得原附件后核对。"
            label["required_claims"] = [
                "已知求和19正确，附件的附加要求不可核验；不能虚构附件要求17或声称全部满足。"
            ]
        else:
            label["required_claims"] = [
                "原文19、计划19、代码19一致；不把图谱背景扩大成必达目标或要求动画。"
            ]
    elif family == "assessment-coverage":
        overrides["objective"] = "实现并解释循环状态与退出，练习必须要求辨认完整逐轮状态表。"
        # Distributed delivery is intentional: trace in code steps, exit in q2.
        d["explanation"]["markdown"] = (
            "本函数返回19，不打印。逐轮状态见代码步骤，退出原因见q2解析。"
        )
        d["code"]["key_steps"] = [
            "各次条件判断前(s,i)：(0,0)→(4,1)→(10,2)→(19,3)。最后3<3为假，不访问a[3]。"
        ]
        d["exercise"]["items"] = [
            quiz(
                1,
                (
                    "请完整推演并核对此状态表：条件判断前(s,i)依次(0,0)、("
                    "4,1)、(10,2)、(19,3)，最后一次条件为假"
                ),
                "T",
                "0加4得4，再加6得10，再加9得19；i逐次增到3后退出。",
            ),
            quiz(
                2, "i=3时先退出，绝不执行a[3]那次累加", "T", "首次失败3<3为假，退出前不进循环体。"
            ),
            quiz(3, "将i<3改为i<=3仍能只访问0..2", "F", "此时i=3还会进入循环体读取a[3]，越界。"),
        ]
        if variant == "error":
            d["exercise"]["items"] = [
                quiz(1, "4+6+9=19", "T", "结果19。"),
                quiz(2, "6+9=15", "T", "结果15。"),
                quiz(3, "4+9=13", "T", "结果13。"),
            ]
            label["required_claims"] = [
                (
                    "过程已在代码步骤明确教过；三题仅算术，未测完整状态和退出；nee"
                    "ds_human，不编造fact。"
                )
            ]
        elif variant == "insufficient":
            d["exercise"]["items"] = [
                quiz(
                    n,
                    f"未随本次材料提交的纸质题本第{n}题所列状态表正确",
                    "T",
                    "只转录了题本答案T，原状态表缺失，无法核验其正确性或是否完整考查过程。",
                )
                for n in range(1, 4)
            ]
            label["required_claims"] = [
                (
                    "缺题本正文，不能判断实际过程测量；指出缺证据，不能声称未见题本一"
                    "定只考算术或一定合格。"
                )
            ]
        else:
            label["required_claims"] = [
                (
                    "教学分散覆盖且完整状态表判断题真实要求推演，干净pass；不能因"
                    "不是开放题或讲解未重写轨迹而误拒。"
                )
            ]
    else:
        source = "#include <stdlib.h>\ntypedef struct Node { int data; struct Node *next; } Node;\n"
        if variant == "correct":
            source += (
                "void free_list(Node **head) { Node *p=*head; while(p) { "
                "Node *q=p->next; free(p); p=q; } *head=NULL; }\nint main("
                "void) { Node *head=malloc(sizeof *head); if(!head) retur"
                "n 0; head->data=4; head->next=NULL; free_list(&head); if"
                "(head) free(head); return 0; }"
            )
            claim = (
                "free_list接收Node **，释放后*head=NULL"
                "；main传&head，故清空调用方head。if(head)为"
                "假，不二次释放。"
            )
            label["required_claims"] = [
                (
                    "按形参Node **、赋值*head=NULL和调用&head判"
                    "断；不可将讲解局部变量片段脱离完整源码而判调用方悬垂。"
                )
            ]
        elif variant == "error":
            source += (
                "void free_list(Node *head) { Node *p=head; while(p) { No"
                "de *q=p->next; free(p); p=q; } head=NULL; }\nint main(voi"
                "d) { Node *head=malloc(sizeof *head); if(!head) return 0"
                "; head->data=4; head->next=NULL; free_list(head); free(h"
                "ead); return 0; }"
            )
            claim = "本例声称free_list中的head=NULL也会清空main的head，因此再次free(head)安全。"
            label.update(
                expected_verdict="reject",
                expected_category="code_safety",
                expected_severity="severe",
            )
            label["required_claims"] = [
                (
                    "malloc成功路径中Node *按值传递，函数已释放对象，ma"
                    "in再次free同一地址构成可达二次释放；不推导UB确定返回值。"
                )
            ]
        else:
            source += (
                "void free_list(Node *head); /* 实现未提供 */\nvoid caller(Node"
                " *head) { free_list(head); /* 后续用途未提供 */ }"
            )
            claim = (
                "这里只给free_list声明和部分调用点，函数体及调用后的用途"
                "未提供；不能断定是否释放、是否悬垂或发生二次释放。"
            )
            label["required_claims"] = [
                (
                    "函数体/后续用途缺失，不能保证安全也不能断定已释放或二次释放；不"
                    "能把Node *声明当函数已释放的证据。"
                )
            ]
        d["explanation"]["markdown"] = claim
        d["code"].update(
            source=source,
            expected_output="不包含打印语句；不主张未定义行为有确定返回值。",
            key_steps=[claim],
        )
        d["exercise"]["items"] = [
            quiz(1, "Node *形参的赋值必然修改调用方指针变量", "F", "指针值按值传递。"),
            quiz(
                2,
                "通过有效的Node **可写入调用方指针对象",
                "T",
                "例如*head=NULL，仍须核对实际调用点。",
            ),
            quiz(3, "只见函数声明就足以证明函数已free对象", "F", "还需函数体和可达调用路径。"),
        ]
        overrides["pointer"] = True
    return goal, d, overrides, label


async def build_case(family, variant):
    name = family + "--" + variant
    goal, content, overrides, label = specification(family, variant)
    i = input_for("defect-r01:" + name, "c-pointer" if family == "pointer-scope" else "array", goal)
    draft = draft_for(i, "complete")
    if overrides.get("objective"):
        draft["objectives"][0]["text"] = overrides["objective"]
    if overrides.get("pointer"):
        draft["terminology"] = [dict(term="形参", meaning="调用时取得参数值的函数内参数对象。")]
        draft["conventions"].update(
            index_base=None,
            capacity=None,
            state_representation="区分调用方head与形参；是否释放依具体函数体。",
            not_applicable_reasons=["本例指针接口，不规定容器下标或容量。"],
        )
        draft["shared_example"] = dict(
            input_description="Node指针及释放接口",
            initial_state="依提供的caller与函数体",
            steps=[
                dict(
                    operation="核对接口及调用",
                    expected_state="依形参、赋值、调用点确定；缺证据保留未知。",
                    expected_output="不打印。",
                )
            ],
        )
    if overrides.get("unknown_input"):
        draft["shared_example"] = dict(
            input_description="长度3有效数组，指定元素附件未提供",
            initial_state="s=0,i=0",
            steps=[
                dict(
                    operation="依次加三个输入值",
                    expected_state="i=3时退出，数值和取决于缺失输入。",
                    expected_output="返回值待核验是否19，不打印。",
                )
            ],
        )
    plan = await generate_shared_plan(Capture(draft), i, CallWindow())
    binding = {
        k: uid("defect-r01:" + name + ":" + k)
        for k in ("owner_id", "unit_id", "operation_id", "plan_id")
    }
    binding.update(
        plan_version=1,
        plan_digest=digest("plan", "learning-plan-v1", plan=plan),
        input_digest=digest("input", "learning-input-v1", snapshot=i.snapshot()),
        references_digest=digest("references", "references-v1", references=i.references),
        policy_version="hybrid-review-v1",
        policy_digest=active_policy_digest(),
    )
    w = PlannedScenes(
        plan, binding, reference_context=i.reference_context, input_snapshot=i.snapshot()
    )
    for role, value in content.items():
        with patch(
            "app.agents.planned_scene_generation.uuid4", return_value=uid(name + ":" + role)
        ):
            c = w.stage(
                role,
                dict(resource_type=role, prompt_version="learning-resources-v1", content=value),
            )
        w.disposition(role, c.id, "needs_human")  # Fixture assembly only; never approval.
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
    case = dict(
        id=name,
        family=family,
        variant=variant,
        scope="unit",
        selected_role=None,
        input_snapshot=i.snapshot(),
        material=unit_material(w, scenes, assemble_actions(w.candidates())),
        provenance="Authored calibration fixture; known failure types, not holdout or live result",
        actual_model_result=None,
    )
    return case, deepcopy(label)
