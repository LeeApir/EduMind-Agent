"""Program-owned scene materials for a fixed-capacity stack with rejected operations."""

from hashlib import sha256
from typing import Any

from app.services import stack_course_materials as stack
from app.services.free_course_snapshots import SnapshotError, digest

VERSION = "stack-boundaries-multiscene-v1"
FIXED_BATCH = "stack-boundaries-fixed-outline-v1"
EVIDENCE_BATCH = "stack-boundaries-practice-evidence-v1"
SELECTION_BATCH = "stack-goal-selection-v1"
TYPED_PRACTICE_BATCH = "stack-boundaries-typed-practice-v1"
FIXED_BATCHES = (FIXED_BATCH, EVIDENCE_BATCH, TYPED_PRACTICE_BATCH)
PRACTICE_BATCHES = (EVIDENCE_BATCH, SELECTION_BATCH, TYPED_PRACTICE_BATCH)
PRACTICE_VERSION = "stack-practice-checkpoints-v1"
NORMAL_GOAL = "追踪正常入栈和出栈，解释栈顶与后进先出"
FULL_GOAL = "解释满栈为什么拒绝入栈"
EMPTY_GOAL = "解释空栈为什么拒绝出栈，以及拒绝后哪些状态保持不变"
GOAL = f"{NORMAL_GOAL}；{FULL_GOAL}；{EMPTY_GOAL}。"
SCENE_GOALS = {"normal": (NORMAL_GOAL,), "rejections": (FULL_GOAL, EMPTY_GOAL)}
FORMS = ("text", "code", "visualization", "exercise")

DEMO = (3, 8, 5, 9, None, None, None, None)
TRANSFER = (1, 2, 4, 7, None, None, None, None)
INTEGER_GUIDE = (
    " 整数题格式示例：12 或 -7。负数使用半角减号，不加正号、前导零、小数点、"
    "引号、单位或解释。反馈若提示输入格式，表示该输入未参与数值比较。"
)


def materials(batch: str | None = None) -> dict[str, Any]:
    typed = batch == TYPED_PRACTICE_BATCH
    existing = stack.materials()
    normal = existing["main"]
    normal_transfer = existing["transfer"]
    demo = stack.example(DEMO, observe_rejections=True)
    transfer = stack.example(TRANSFER, observe_rejections=True)
    full = transfer["frames"][4]
    empty = transfer["frames"][8]

    def question(key, checkpoint, domain, answer, *, integer_domain):
        result = dict(key=key, checkpoint=checkpoint, domain=domain, private_answer=str(answer))
        if typed:
            if integer_domain is None:
                result.update(
                    input_type="short_text", domain="A 或 B（大小写均可）",
                    input_instruction="输入 A 或 B，大小写均可，不加其他文字。",
                )
            else:
                result.update(
                    input_type="integer", domain=f"{integer_domain}一个 JSON 整数",
                    input_instruction=f"只输入{integer_domain}一个 JSON 整数。",
                )
        return result

    scenes = {
        "normal": dict(
            **normal,
            facts={key: value for key, value in existing["facts"].items() if key != "boundary"},
            demonstrated="从空栈初始化，依次成功入栈 3、入栈 8、出栈、入栈 5。",
            text_only="用 count 解释有效前缀。满栈和空栈的拒绝不在本场景演示。",
            exercise_source=normal_transfer["source"],
            questions=[
                question(
                    key, normal_transfer["questions"][key]["target"], "[-4,9] 内的一个整数",
                    normal_transfer["questions"][key]["private_answer"],
                    integer_domain="[-4,9] 范围内的",
                )
                for key in ("first_pop", "final_top")
            ],
        ),
        "rejections": dict(
            **demo,
            facts=dict(
                order=existing["facts"]["order"],
                boundary="容量为 3，不扩容；满栈 push 在写入前返回 false，"
                         "空栈 pop 在递减 count 和写 *out 前返回 false。"
                         "实际用有效指针，value 初始为 -99，只在成功 pop 时更新。",
                storage="成功 pop 不清零槽位；count 确定逻辑范围，旧值不属于栈。"
                        "失败时旧槽与调用者 value 均保持，无新出栈值。",
                **{frame["frame_id"]: frame for frame in demo["frames"]},
            ),
            demonstrated="f4 满栈 push(9) 返回 false，f8 空栈 pop 返回 false；"
                         "调用者记录返回值并继续，两个拒绝前后的逻辑栈、count、"
                         "底层三个槽和调用者输出均可对照。",
            text_only="无扩容是本实现的约定。无效指针不在支持域，只说明有效指针前提。",
            exercise_source=transfer["source"],
            questions=[
                question("full_count", "push(7) 被拒后有效元素数", "[0,3] 内的一个整数",
                         full["count"], integer_domain="[0,3] 范围内的"),
                question(
                    "empty_return", "最后一次空栈 pop 的返回值（false=0，true=1）",
                    "0 或 1 中的一个整数", int(empty["success"]), integer_domain="值为 0 或 1 的",
                ),
                question(
                    "empty_output", "最后一次空栈 pop 后调用者 value 的值",
                    "[-99,7] 内的一个整数", empty["output"], integer_domain="[-99,7] 范围内的",
                ),
                question(
                    "guard_pair",
                    "两次拒绝各自触发的守卫是哪组，A 为 push 的 count == CAP 和 "
                    "pop 的 count == 0，B 为这两个条件对调",
                    "A 或 B 中的一个大写字母", "A", integer_domain=None,
                ),
            ],
        ),
    }
    version = TYPED_PRACTICE_BATCH if typed else VERSION
    if typed:
        for scene in scenes.values():
            scene["exercise_guide"] = INTEGER_GUIDE
    data = dict(version=version, capacity=stack.CAPACITY, order="bottom_to_top", scenes=scenes)
    return {**data, "materials_digest": digest(version, data=data)}


def _practice_states(trace: dict[str, Any]) -> list[dict[str, Any]]:
    states = []
    value = None
    for frame in trace["frames"]:
        if frame["popped"] is not None:
            value = frame["popped"]
        initialized = "output" in frame or value is not None
        states.append(dict(
            frame_id=frame["frame_id"], operation=frame["operation"], call_line=frame["line"],
            count=len(frame["values"]), values=frame["values"], top=frame["top"],
            popped=frame["popped"], value=frame.get("output", value),
            value_status="initialized" if initialized else "uninitialized",
            success=frame.get("success", True if frame["frame_id"] != "f0" else None),
            **({key: frame[key] for key in ("storage", "guard_line", "rejection")}
               if "storage" in frame else {}),
        ))
    return states


def practice_evidence(data: dict[str, Any]) -> dict[str, Any]:
    """Build private per-question checkpoints from the existing, exact practice programs."""
    programs = {
        "normal": stack.example(stack.TRANSFER),
        "rejections": stack.example(TRANSFER, observe_rejections=True),
    }
    targets = {
        "normal": {"first_pop": (4,), "final_top": (7,)},
        "rejections": {
            "full_count": (4,), "empty_return": (8,), "empty_output": (8,), "guard_pair": (4, 8),
        },
    }
    result = {}
    for key, trace in programs.items():
        mat = data["scenes"][key]
        code = trace["source"]
        if code != mat["exercise_source"]:
            raise SnapshotError("STACK_PRACTICE_CODE_MISMATCH")
        code_sha256 = sha256(code.encode()).hexdigest()
        states = _practice_states(trace)
        questions = {}
        for q in mat["questions"]:
            question_key = q["key"]
            evidence_id = f"practice.{key}.{question_key}"
            questions[question_key] = dict(
                evidence_id=evidence_id, practice_code_sha256=code_sha256,
                asked=q["checkpoint"], answer_domain=q["domain"],
                reference_answer=q["private_answer"],
                **({field: q[field] for field in ("input_type", "input_instruction")}
                   if "input_type" in q else {}),
                checkpoints=[
                    dict(
                        id=f"{evidence_id}.after-f{i}", observation="after_call",
                        before=states[i - 1], after=states[i],
                    )
                    for i in targets[key][question_key]
                ],
            )
        result[key] = dict(code=code, code_sha256=code_sha256, questions=questions)
    return dict(version=PRACTICE_VERSION, scenes=result)


def materials_digest(batch: str) -> str:
    data = materials(batch)
    if batch not in PRACTICE_BATCHES:
        return data["materials_digest"]
    return digest(
        TYPED_PRACTICE_BATCH if batch == TYPED_PRACTICE_BATCH else EVIDENCE_BATCH,
        base_materials_digest=data["materials_digest"],
        practice_evidence=practice_evidence(data),
    )
