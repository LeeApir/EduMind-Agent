"""Program-owned fixed-capacity FIFO example, trace and transfer practice."""

from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.services import stack_course_materials as fixed
from app.services.free_course_snapshots import SnapshotError, digest

GOAL = (
    "理解队头、队尾与先进先出。初始空队列，依次执行 enqueue(3) → enqueue(8) → "
    "dequeue() → enqueue(5)，追踪队头、队尾、有效元素和出队值。"
)
VERSION = "queue-fifo-course-v1"
BATCH = "queue-fifo-deepseek-r01"
ORIGIN = "queue_fifo_model_generation"
CAPACITY = 3
MAIN = (3, 8, None, 5)
TRANSFER = (-4, 6, 2, None, 9, None, None)
TITLE = "队列的入队、出队与先进先出"
CODE = """#include <stdbool.h>
#include <stddef.h>

enum { CAP = 3 };
typedef struct { int data[CAP]; size_t count; } Queue;

static bool enqueue(Queue *q, int value) {
    if (q->count == CAP) return false;
    q->data[q->count] = value;
    ++q->count;
    return true;
}

static bool dequeue(Queue *q, int *out) {
    if (q->count == 0) return false;
    *out = q->data[0];
    for (size_t i = 1; i < q->count; ++i)
        q->data[i - 1] = q->data[i];
    --q->count;
    return true;
}

int main(void) {
    Queue q = {{0}, 0};
    int value;
"""
INSTRUCTION = """[ROLE] Write one complete beginner lesson in Simplified Chinese.
[GOAL] Explain FIFO, the front and rear, enqueue, dequeue and the exact five supplied frames.
[PROGRAM MATERIAL] Code, trace, facts, scenario and private answers are fixed by the program.
Order every queue array from front to rear. When empty there is no front or rear. A sole
element is both. Explain count and why only data[0..count) is active. Enqueue adds at the
rear; dequeue delivers the old front via *out, shifts survivors, then reduces count.
Distinguish the removed value from the new front. Explain capacity 3, no resizing or
wraparound, O(1) enqueue and linear successful dequeue in this shifting implementation.
Full enqueue and empty dequeue return false without changing the queue; empty dequeue
does not write *out. The demonstration covers initialization and four successful caller
statements, not failure branches or each loop iteration. Never claim the app executes C.
[TEXT] Write 4–7 useful paragraphs, each citing exact supporting fact IDs. Write one note per
frame in exact order; each explains the code and resulting state. Include a summary.
Do not use HTML, links, tools, code fences, invented facts or extra examples.
[PRACTICE] Write one single-line Chinese stem and a precise explanation per key. Each stem
will be followed by the same complete scenario, so refer to “下方代码” or “这段代码”.
Specify the exact checkpoint and integer or JSON integer array input format. State
front-to-rear order for active elements and chronological order for removed values.
Do not reveal transfer answers in the stems, notes or lesson; explain them only in explanations.
Return exactly the supplied Schema with no extra fields or duplicate keys."""
QUESTIONS = {
    "first_dequeue": ("第一次 dequeue 写入 value 的值", "integer"),
    "after_enqueue": ("enqueue(9) 后有效元素（从队头到队尾）", "json_integer_array"),
    "dequeue_order": ("三次 dequeue 写入 value 的值（按发生顺序）", "json_integer_array"),
    "final_rear": ("最后一次 dequeue 后的队尾值", "integer"),
}
SCHEMA = {
    **fixed.SCHEMA,
    "properties": {
        **fixed.SCHEMA["properties"],
        "questions": fixed.closed(
            {key: fixed.closed(dict(stem=fixed.TEXT, explanation=fixed.TEXT)) for key in QUESTIONS}
        ),
    },
}
VALIDATOR = Draft202012Validator(SCHEMA)


def example(operations: tuple[int | None, ...]) -> dict[str, Any]:
    lines = CODE.splitlines()
    values: list[int] = []
    frames = [
        dict(
            frame_id="f0",
            operation="初始化空队列",
            line=lines.index("    Queue q = {{0}, 0};") + 1,
            values=[],
            front=None,
            rear=None,
            dequeued=None,
        )
    ]
    for i, op in enumerate(operations, 1):
        if op is None:
            if not values:
                raise SnapshotError("QUEUE_UNSUPPORTED_UNDERFLOW")
            action, call = "dequeue()", "dequeue(&q, &value)"
            dequeued = values.pop(0)
        else:
            if len(values) >= CAPACITY:
                raise SnapshotError("QUEUE_UNSUPPORTED_OVERFLOW")
            action, call = f"enqueue({op})", f"enqueue(&q, {op})"
            values.append(op)
            dequeued = None
        lines.append(f"    if (!{call}) return 1;")
        frames.append(
            dict(
                frame_id=f"f{i}",
                operation=action,
                line=len(lines),
                values=values.copy(),
                front=values[0] if values else None,
                rear=values[-1] if values else None,
                dequeued=dequeued,
            )
        )
    return dict(source="\n".join([*lines, "    return 0;", "}", ""]), frames=frames)


def materials() -> dict[str, Any]:
    main, transfer = example(MAIN), example(TRANSFER)
    frames = transfer["frames"]
    answers = dict(
        first_dequeue=frames[4]["dequeued"],
        after_enqueue=frames[5]["values"],
        dequeue_order=[frame["dequeued"] for frame in frames if frame["dequeued"] is not None],
        final_rear=frames[-1]["rear"],
    )
    data = dict(
        version=VERSION,
        capacity=CAPACITY,
        order="front_to_rear",
        main=main,
        facts={
            "order": "有效元素位于 data[0..count)，从队头到队尾排列。空队列没有队头、队尾，"
            "非空时分别为 data[0] 和 data[count-1]，单元素同时是队头和队尾。",
            "enqueue": "入队先判满，再向 data[count] 写入新值，增加 count，返回 true。",
            "dequeue": "出队先判空，经 *out 写回原队头，将剩余元素向前移动一格，减少 count，"
            "返回 true。布尔返回值表示成功与否，旧存储槽是否清零不影响有效元素。",
            "fifo": "先进先出。主例先入 3 后入 8，出队取出 3，8 成为新队头，最后 5 成为队尾。",
            "boundary": "固定容量 3，无扩容或环绕。满队列入队或空队列出队返回 false，"
            "队列不变，失败的出队不写 *out。传入指针须有效。演示只展示成功操作完成后的状态。",
            "complexity": "入队 O(1)，成功出队前移 count-1 个元素，时间随原有效元素个数线性增长。",
            **{frame["frame_id"]: frame for frame in main["frames"]},
        },
        transfer=dict(
            source=transfer["source"],
            questions={
                key: dict(target=target, input_type=kind, private_answer=answers[key])
                for key, (target, kind) in QUESTIONS.items()
            },
        ),
    )
    return {**data, "materials_digest": digest("queue-course-materials", data=data)}


def outline() -> dict[str, Any]:
    return dict(
        title=TITLE,
        objectives=[
            dict(
                id="fifo",
                description="解释队头、队尾与先进先出",
                source="user_requirement",
                source_key="request_1",
                source_excerpt="理解队头、队尾与先进先出",
            ),
            dict(
                id="trace",
                description="逐步追踪入队、出队和有效元素",
                source="user_requirement",
                source_key="request_1",
                source_excerpt="追踪队头、队尾、有效元素和出队值",
            ),
        ],
        shared_example="queue-fifo-fixed-v1",
        terminology=[
            dict(term="FIFO", meaning="先进先出"),
            dict(term="count", meaning="有效元素个数"),
        ],
        conventions=["按队头到队尾列出有效元素", "固定容量 3，出队前移，仅展示成功主例"],
        scenes=[
            dict(
                scene_key="queue",
                title=TITLE,
                purpose="理解并追踪固定容量队列，再在新数据上练习",
                forms=["text", "code", "visualization", "exercise"],
                objective_ids=["fifo", "trace"],
                depends_on=[],
            )
        ],
    )


def request(*, stem_prompt_version: str | None = None) -> dict[str, Any]:
    return fixed.fixed_request(
        INSTRUCTION,
        GOAL,
        outline(),
        materials(),
        "edumind_queue_fifo_v1",
        SCHEMA,
        stem_prompt_version=stem_prompt_version,
    )


def validate_content(raw: Any, mat: dict[str, Any]) -> None:
    fixed.validate_fixed_content(raw, mat, VALIDATOR, "QUEUE")


def assemble(raw: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    mat = materials()
    validate_content(raw, mat)
    steps = []
    for frame, note in zip(mat["main"]["frames"], raw["step_notes"], strict=True):
        elements = [
            dict(id=f"slot-{i}", label=str(value), next_id=None)
            for i, value in enumerate(frame["values"])
        ]
        ends = list(dict.fromkeys([elements[0]["id"], elements[-1]["id"]])) if elements else []
        steps.append(
            dict(
                caption=frame["operation"],
                elements=elements,
                highlight_ids=ends,
                queue_frame=dict(
                    frame_id=frame["frame_id"],
                    code_anchor="queue-code",
                    line=frame["line"],
                    dequeued=frame["dequeued"],
                    note=note["note"],
                ),
            )
        )
    return fixed.assemble_fixed_lesson(
        "queue",
        raw,
        source,
        mat,
        steps,
        "有效元素按队头到队尾从左向右列出。每帧对应完成的一条调用者语句。",
        "队列的迁移练习",
    )
