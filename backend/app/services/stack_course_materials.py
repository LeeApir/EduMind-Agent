"""Program-owned materials for one fixed-capacity stack lesson."""

from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.services.course_question_stem import is_single_line_stem, with_stem_format
from app.services.free_course_snapshots import SnapshotError, canonical, digest

GOAL = (
    "理解栈顶、入栈、出栈和后进先出。使用初始空栈，依次执行 "
    "push(3) → push(8) → pop() → push(5)，追踪每步栈内容、栈顶及出栈结果。"
)
VERSION = "stack-lifo-course-v1"
BATCH = "stack-lifo-deepseek-r01"
ORIGIN = "stack_lifo_model_generation"
TITLE = "栈顶、入栈与出栈"
CAPACITY = 3
MAIN = (3, 8, None, 5)
TRANSFER = (-4, 6, 2, None, 9, None, None)
CODE = """#include <stdbool.h>
#include <stddef.h>

enum { CAP = 3 };
typedef struct { int data[CAP]; size_t count; } Stack;

static bool push(Stack *s, int value) {
    if (s->count == CAP) return false;
    s->data[s->count] = value;
    ++s->count;
    return true;
}

static bool pop(Stack *s, int *out) {
    if (s->count == 0) return false;
    --s->count;
    *out = s->data[s->count];
    return true;
}

int main(void) {
    Stack s = {{0}, 0};
    int value;
"""
INSTRUCTION = """[ROLE] Write one complete beginner lesson in Simplified Chinese.
[GOAL] Teach the exact supplied goal. Assume no learner evidence beyond the request.
Explain the stack top, push, pop and why this sequence demonstrates last in, first out.
[PROGRAM MATERIAL] Code, logical stack, trace, facts, exercise scenario and private answers
are fixed by the program. Use bottom-to-top order when writing stack arrays. Explain count,
why data[count-1] is the top only when nonempty, the two guards, bool versus *out,
and why bytes outside data[0..count) are not stack elements. Distinguish the value removed
on this frame from the current top. This is a fixed-capacity array of 3, without resizing.
The five frames show completed caller statements, including initialization, all successful.
Full/empty rejection is explained using the code, not demonstrated in those frames.
Never say the app executes C.
[TEXT] Write 4–7 useful paragraphs, each citing exact supporting fact IDs. Write one note per
frame in exact order. Each note explains that frame's code and resulting state. Include a
summary. Do not use HTML, links, tools, code fences, or invent facts or extra examples.
[PRACTICE] Write one single-line Chinese stem and a precise explanation per key. The program
appends the same full transfer scenario to each stem. Mention the exact checkpoint or set
of operations asked for by the key. Integer questions request one integer; array questions
request a JSON integer array. State the array order per question. Do not reveal transfer
answers in the stems, notes or lesson; explain the results only in exercise explanations.
Return exactly the supplied Schema with no extra fields or duplicate keys."""


def closed(properties: dict[str, Any]) -> dict[str, Any]:
    return dict(
        type="object", properties=properties, required=list(properties), additionalProperties=False
    )


TEXT = dict(type="string", minLength=1, maxLength=1200)
QUESTIONS = {
    "first_pop": ("第一次 pop 写入 value 的值", "integer"),
    "after_push": ("push(9) 后栈内容（从栈底到栈顶）", "json_integer_array"),
    "pop_order": ("三次 pop 各自写入 value 的值（按发生顺序）", "json_integer_array"),
    "final_top": ("最后一次 pop 后当前栈顶的值", "integer"),
}
SCHEMA = closed(
    dict(
        paragraphs=dict(
            type="array",
            minItems=4,
            maxItems=7,
            items=closed(
                dict(
                    text=TEXT,
                    fact_ids=dict(
                        type="array",
                        minItems=1,
                        maxItems=8,
                        uniqueItems=True,
                        items=dict(type="string"),
                    ),
                )
            ),
        ),
        step_notes=dict(
            type="array",
            minItems=5,
            maxItems=5,
            items=closed(dict(frame_id=dict(type="string"), note=TEXT)),
        ),
        questions=closed({key: closed(dict(stem=TEXT, explanation=TEXT)) for key in QUESTIONS}),
        summary=TEXT,
    )
)
VALIDATOR = Draft202012Validator(SCHEMA)


def example(
    operations: tuple[int | None, ...], *, observe_rejections: bool = False
) -> dict[str, Any]:
    lines = CODE.splitlines()
    stack: list[int] = []
    storage = [0] * CAPACITY
    output = -99
    if observe_rejections:
        lines.insert(2, "#include <stdio.h>")
        lines[-1] = f"    int value = {output};"
    frames: list[dict[str, Any]] = [
        dict(
            frame_id="f0",
            operation="初始化空栈",
            line=lines.index("    Stack s = {{0}, 0};") + 1,
            values=[],
            top=None,
            popped=None,
        )
    ]
    if observe_rejections:
        frames[0].update(
            success=None, rejection=None, guard_line=None, count=0,
            storage=storage.copy(), output=output,
        )
    for i, op in enumerate(operations, 1):
        rejection = None
        popped = None
        if op is None:
            action, call = "pop()", "pop(&s, &value)"
            if not stack:
                rejection = "empty"
                if not observe_rejections:
                    raise SnapshotError("STACK_UNSUPPORTED_UNDERFLOW")
            else:
                popped = stack.pop()
                output = popped
        else:
            action, call = f"push({op})", f"push(&s, {op})"
            if len(stack) >= CAPACITY:
                rejection = "full"
                if not observe_rejections:
                    raise SnapshotError("STACK_UNSUPPORTED_OVERFLOW")
            else:
                storage[len(stack)] = op
                stack.append(op)
        if observe_rejections:
            lines.append(f"    const bool ok_{i} = {call};")
        else:
            lines.append(f"    if (!{call}) return 1;")
        frames.append(
            dict(
                frame_id=f"f{i}",
                operation=action,
                line=len(lines),
                values=stack.copy(),
                top=stack[-1] if stack else None,
                popped=popped,
            )
        )
        if observe_rejections:
            guard = "s->count == 0" if op is None else "s->count == CAP"
            frames[-1].update(
                success=rejection is None, rejection=rejection, count=len(stack),
                storage=storage.copy(), output=output,
                guard_line=next(
                    n for n, line in enumerate(lines, 1) if f"if ({guard})" in line
                ),
            )
            lines.append(
                f'    printf("%d %zu %d %d %d %d\\n", ok_{i}, s.count, '
                "s.data[0], s.data[1], s.data[2], value);"
            )
    return dict(source="\n".join([*lines, "    return 0;", "}", ""]), frames=frames)


def materials() -> dict[str, Any]:
    main = example(MAIN)
    transfer = example(TRANSFER)
    facts = {
        "order": "程序以 data[0..count) 保存有效元素。数组按栈底到栈顶，"
        "非空时栈顶为 data[count-1]。",
        "push": "push 先查满栈，再把新值写到 data[count]、增加 count，返回 true。",
        "pop": "pop 先查空栈，再减小 count，将原栈顶通过 *out 写入调用者变量，返回 true。",
        "lifo": "最近仍在栈中的入栈元素先出栈；本例先入 3 后入 8，第一次出栈取 8，3 留在栈中。",
        "boundary": "容量为 3，无扩容。满栈 push 或空栈 pop 返回 false，"
        "状态不变，失败的 pop 不写 *out。"
        "要求有效 s/out 指针。出栈不会清零底层存储，count 之外的旧值无效。主例未进入失败分支。",
        **{frame["frame_id"]: frame for frame in main["frames"]},
    }
    frames = transfer["frames"]
    answers = dict(
        first_pop=frames[4]["popped"],
        after_push=frames[5]["values"],
        pop_order=[f["popped"] for f in frames if f["popped"] is not None],
        final_top=frames[-1]["top"],
    )
    data = dict(
        version=VERSION,
        capacity=CAPACITY,
        order="bottom_to_top",
        main=main,
        facts=facts,
        transfer=dict(
            source=transfer["source"],
            questions={
                key: dict(target=target, input_type=kind, private_answer=answers[key])
                for key, (target, kind) in QUESTIONS.items()
            },
        ),
    )
    return {**data, "materials_digest": digest("stack-course-materials", data=data)}


def outline() -> dict[str, Any]:
    return dict(
        title=TITLE,
        objectives=[
            dict(
                id="lifo",
                description="解释栈顶、入栈、出栈和后进先出",
                source="user_requirement",
                source_key="request_1",
                source_excerpt="理解栈顶、入栈、出栈和后进先出",
            ),
            dict(
                id="trace",
                description="逐步追踪栈内容、栈顶和出栈结果",
                source="user_requirement",
                source_key="request_1",
                source_excerpt="追踪每步栈内容、栈顶及出栈结果",
            ),
        ],
        shared_example="stack-lifo-fixed-v1",
        terminology=[
            dict(term="LIFO", meaning="后进先出"),
            dict(term="count", meaning="有效元素个数"),
        ],
        conventions=["按栈底到栈顶列出有效元素", "固定容量 3，仅展示初始化及四个成功操作"],
        scenes=[
            dict(
                scene_key="stack",
                title=TITLE,
                purpose="理解并追踪固定容量栈，再在新数据上练习",
                forms=["text", "code", "visualization", "exercise"],
                objective_ids=["lifo", "trace"],
                depends_on=[],
            )
        ],
    )


def request(*, stem_prompt_version: str | None = None) -> dict[str, Any]:
    return fixed_request(
        INSTRUCTION,
        GOAL,
        outline(),
        materials(),
        "edumind_stack_lifo_v1",
        SCHEMA,
        stem_prompt_version=stem_prompt_version,
    )


def fixed_request(
    instruction,
    goal,
    plan,
    material,
    schema_name,
    schema,
    *,
    stem_prompt_version: str | None = None,
):
    return dict(
        model="deepseek-flash",
        stream=False,
        store=False,
        reasoning=dict(effort="none"),
        max_output_tokens=4000,
        temperature=0.2,
        input=[
            dict(role="system", content=with_stem_format(instruction, stem_prompt_version)),
            dict(
                role="user",
                content=canonical(dict(goal=goal, plan=plan, materials=material)).decode(),
            ),
        ],
        text=dict(format=dict(type="json_schema", name=schema_name, strict=True, schema=schema)),
    )


def validate_content(raw: Any, mat: dict[str, Any]) -> None:
    validate_fixed_content(raw, mat, VALIDATOR, "STACK")


def validate_fixed_content(raw, mat, validator, prefix):
    if not validator.is_valid(raw):
        raise SnapshotError(f"{prefix}_TEACHING_SCHEMA")
    if any(
        not p["text"].strip() or not set(p["fact_ids"]) <= set(mat["facts"])
        for p in raw["paragraphs"]
    ):
        raise SnapshotError(f"{prefix}_FACT_REFERENCE")
    if (
        [n["frame_id"] for n in raw["step_notes"]] != [f["frame_id"] for f in mat["main"]["frames"]]
        or any(not n["note"].strip() for n in raw["step_notes"])
        or not raw["summary"].strip()
    ):
        raise SnapshotError(f"{prefix}_FRAME_BINDING")
    for q in raw["questions"].values():
        if not is_single_line_stem(q["stem"]) or not q["explanation"].strip():
            raise SnapshotError(f"{prefix}_QUESTION_PROSE_REQUIRED")


def assemble(raw: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    mat = materials()
    validate_content(raw, mat)
    steps = []
    for f, n in zip(mat["main"]["frames"], raw["step_notes"], strict=True):
        elements = [
            dict(id=f"slot-{i}", label=str(v), next_id=None) for i, v in enumerate(f["values"])
        ]
        steps.append(
            dict(
                caption=f["operation"],
                elements=elements,
                highlight_ids=[elements[-1]["id"]] if elements else [],
                stack_frame=dict(
                    frame_id=f["frame_id"],
                    code_anchor="stack-code",
                    line=f["line"],
                    popped=f["popped"],
                    note=n["note"],
                ),
            )
        )
    return assemble_fixed_lesson(
        "stack",
        raw,
        source,
        mat,
        steps,
        "状态按栈底到栈顶列出；竖向图的栈顶在上方。",
        "栈的迁移练习",
    )


def assemble_fixed_lesson(topic, raw, source, mat, steps, text_alternative, exercise_title):
    blocks = [
        dict(kind="text", anchor_id=f"{topic}-text-{i}", markdown=p["text"])
        for i, p in enumerate(raw["paragraphs"])
    ]
    blocks.append(
        dict(kind="code", anchor_id=f"{topic}-code", language="c", source=mat["main"]["source"])
    )
    blocks.extend(
        [
            dict(
                kind="visualization",
                anchor_id=f"{topic}-state",
                visualization_type=topic,
                text_alternative=text_alternative,
                steps=steps,
            ),
            dict(kind="text", anchor_id=f"{topic}-summary", markdown=raw["summary"]),
            dict(
                kind="exercise",
                anchor_id=f"{topic}-questions",
                exercise_key=f"{topic}-questions",
                question=exercise_title,
                items=[
                    dict(
                        question_id=key,
                        question=raw["questions"][key]["stem"] + "\n\n" + mat["transfer"]["source"],
                        input_type=q["input_type"],
                        answer_key=canonical(q["private_answer"]).decode(),
                        solution=raw["questions"][key]["explanation"],
                    )
                    for key, q in mat["transfer"]["questions"].items()
                ],
            ),
        ]
    )
    return dict(
        blocks=blocks,
        generation_source=source,
        actions=[
            dict(type="show_step", anchor_id=f"{topic}-state", step_index=i)
            for i in range(len(steps))
        ],
    )
