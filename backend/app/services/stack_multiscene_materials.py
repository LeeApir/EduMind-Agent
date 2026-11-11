"""Program-owned scene materials for a fixed-capacity stack with rejected operations."""

from typing import Any

from app.services import stack_course_materials as stack
from app.services.free_course_snapshots import digest

VERSION = "stack-boundaries-multiscene-v1"
NORMAL_GOAL = "追踪正常入栈和出栈，解释栈顶与后进先出"
FULL_GOAL = "解释满栈为什么拒绝入栈"
EMPTY_GOAL = "解释空栈为什么拒绝出栈，以及拒绝后哪些状态保持不变"
GOAL = f"{NORMAL_GOAL}；{FULL_GOAL}；{EMPTY_GOAL}。"
SCENE_GOALS = {"normal": (NORMAL_GOAL,), "rejections": (FULL_GOAL, EMPTY_GOAL)}
FORMS = ("text", "code", "visualization", "exercise")

DEMO = (3, 8, 5, 9, None, None, None, None)
TRANSFER = (1, 2, 4, 7, None, None, None, None)


def materials() -> dict[str, Any]:
    existing = stack.materials()
    normal = existing["main"]
    normal_transfer = existing["transfer"]
    demo = stack.example(DEMO, observe_rejections=True)
    transfer = stack.example(TRANSFER, observe_rejections=True)
    full = transfer["frames"][4]
    empty = transfer["frames"][8]

    def question(key, checkpoint, domain, answer):
        return dict(key=key, checkpoint=checkpoint, domain=domain, private_answer=str(answer))

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
                         full["count"]),
                question("empty_return", "最后一次空栈 pop 的返回值（false=0，true=1）",
                         "0 或 1 中的一个整数", int(empty["success"])),
                question("empty_output", "最后一次空栈 pop 后调用者 value 的值",
                         "[-99,7] 内的一个整数", empty["output"]),
                question(
                    "guard_pair",
                    "两次拒绝各自触发的守卫是哪组，A 为 push 的 count == CAP 和 "
                    "pop 的 count == 0，B 为这两个条件对调",
                    "A 或 B 中的一个大写字母", "A",
                ),
            ],
        ),
    }
    data = dict(version=VERSION, capacity=stack.CAPACITY, order="bottom_to_top", scenes=scenes)
    return {**data, "materials_digest": digest(VERSION, data=data)}
