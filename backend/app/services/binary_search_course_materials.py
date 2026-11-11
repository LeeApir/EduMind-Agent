"""Fixed closed-interval binary search example and transfer exercises."""

from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from app.services import stack_course_materials as fixed
from app.services.free_course_snapshots import digest

VERSION = "binary-search-course-v1"
BATCH = "binary-search-deepseek-r01"
ORIGIN = "binary_search_model_generation"
TITLE = "二分查找"
GOAL = (
    "在升序数组 [2,5,8,12,16] 中查找 5，使用从 0 开始的下标与闭区间，"
    "理解中点计算、比较、区间更新及查找终止。"
)
MAIN = (2, 5, 8, 12, 16)
TARGET = 5
TRANSFER = (1, 4, 7, 10, 13, 16, 19, 22)
HIT, MISS = 19, 9
CODE = """#include <stdio.h>

static int binary_search(const int values[], int length, int target) {
    int left = 0, right = length - 1;
    while (left <= right) {
        int mid = left + (right - left) / 2;
        if (values[mid] == target) {
            return mid;
        }
        if (values[mid] < target) {
            left = mid + 1;
        } else {
            right = mid - 1;
        }
    }
    return -1;
}
"""
QUESTIONS = {
    "increase_left": ("查找 19 时第一次更新后的闭区间端点 [left,right]", "json_integer_array"),
    "decrease_right": ("查找 9 时第一次更新后的闭区间端点 [left,right]", "json_integer_array"),
    "found_index": ("查找 19 的函数返回值（零基下标）", "integer"),
    "missing_result": ("查找 9 的函数返回值", "integer"),
}
SCHEMA = {
    **fixed.SCHEMA,
    "properties": {
        **fixed.SCHEMA["properties"],
        "step_notes": {**fixed.SCHEMA["properties"]["step_notes"], "minItems": 6, "maxItems": 6},
        "questions": fixed.closed(
            {key: fixed.closed(dict(stem=fixed.TEXT, explanation=fixed.TEXT)) for key in QUESTIONS}
        ),
    },
}
VALIDATOR = Draft202012Validator(SCHEMA)
INSTRUCTION = """[ROLE] Write a beginner lesson in Simplified Chinese for the fixed C example.
[PROGRAM MATERIAL] Use only the supplied code, facts and frames. The array is ascending
(nondecreasing; duplicates may exist). Indices start at zero, and both endpoints of
[left,right] are included. Each loop requires left <= right, and mid is computed by
left + (right - left) / 2 with integer division rounding down on this nonnegative span.
[COMPARE] Always describe values[mid] compared with target. A smaller value updates
left = mid + 1; a larger value updates right = mid - 1. Explain why sorted order allows
the discarded half and mid to be excluded. Equality returns that mid immediately. If
left > right, the interval is empty and the function returns -1. -1 is a return signal,
not an array index. With duplicates the code returns a matching index, not necessarily
the first or last. Keep the fixed example and exercises separate.
[FRAMES] Write one note per supplied frame in order, tied to its code line. An update frame
shows the new bounds and the just-used mid from the same iteration. Do not call that
value a newly computed mid. The initialization frame has not computed a mid. The demo
shows only the main example's successful search. Explain unsuccessful termination from
the code and the separate exercise, not as another main-example frame.
[TEXT] Write 4–7 useful paragraphs with exact supporting fact IDs, and one short summary.
No HTML, links, tools, code fences, invented facts or unrelated examples.
[PRACTICE] Write one single-line Chinese stem and a precise explanation for each key.
Refer to the program-appended code below. Specify the target and exact checkpoint, and
request a two-element JSON integer array [left,right] for interval questions or an
integer for return-value questions. Do not reveal answers in the stems, notes, or
lesson. Keep the answers and reasoning in the explanations.
Return exactly the supplied Schema without extra fields or duplicate keys."""


def search(values: tuple[int, ...], target: int) -> tuple[list[dict[str, Any]], int]:
    lines = CODE.splitlines()
    left, right = 0, len(values) - 1

    def frame(phase: str, statement: str, mid: int | None = None, comparison: str | None = None):
        return dict(
            frame_id=f"f{len(frames)}",
            phase=phase,
            line=lines.index(statement) + 1,
            left=left,
            right=right,
            mid=mid,
            target=target,
            comparison=comparison,
        )

    frames: list[dict[str, Any]] = []
    frames.append(frame("initial", "    int left = 0, right = length - 1;"))
    while left <= right:
        mid = left + (right - left) // 2
        if values[mid] == target:
            frames.append(frame("found", "            return mid;", mid, "equal"))
            return frames, mid
        comparison = "less" if values[mid] < target else "greater"
        frames.append(frame("compare", "        if (values[mid] < target) {", mid, comparison))
        if comparison == "less":
            left = mid + 1
            frames.append(frame("narrowed", "            left = mid + 1;", mid, comparison))
        else:
            right = mid - 1
            frames.append(frame("narrowed", "            right = mid - 1;", mid, comparison))
    return frames, -1


def materials() -> dict[str, Any]:
    frames, result = search(MAIN, TARGET)
    hit_frames, hit = search(TRANSFER, HIT)
    miss_frames, miss = search(TRANSFER, MISS)
    answers = {
        "increase_left": [hit_frames[2]["left"], hit_frames[2]["right"]],
        "decrease_right": [miss_frames[2]["left"], miss_frames[2]["right"]],
        "found_index": hit,
        "missing_result": miss,
    }
    source = (
        CODE
        + f"""
int main(void) {{
    const int values[] = {{{", ".join(map(str, MAIN))}}};
    printf("%d\\n", binary_search(values, {len(MAIN)}, {TARGET}));
    return 0;
}}
"""
    )
    transfer = (
        CODE
        + f"""
int main(void) {{
    const int values[] = {{{", ".join(map(str, TRANSFER))}}};
    const int hit = binary_search(values, {len(TRANSFER)}, {HIT});
    const int miss = binary_search(values, {len(TRANSFER)}, {MISS});
    printf("%d %d\\n", hit, miss);
    return 0;
}}
"""
    )
    data = dict(
        version=VERSION,
        main=dict(source=source, values=list(MAIN), target=TARGET, frames=frames, result=result),
        facts={
            "order": "数组升序排列，允许相等值。下标从 0 开始，[left,right] 包含两端。",
            "bounds": "初始 left=0、right=length-1。仅 left<=right 时计算和访问中点。",
            "mid": "mid = left + (right - left) / 2。区间跨度非负，整数除法向下取整。",
            "smaller": "values[mid] 小于目标时，mid 及其左边的值都太小，left=mid+1。",
            "larger": "values[mid] 大于目标时，mid 及其右边的值都太大，right=mid-1。",
            "termination": "相等立刻返回 mid。left>right 时区间为空，退出循环并返回 -1。",
            "duplicates": "遇到相等值即返回本轮 mid。重复值场景不保证返回首个或末个匹配下标。",
            "display": "演示为主例的六个状态快照。更新帧保留刚使用的 mid，区间已更新。",
            **{item["frame_id"]: item for item in frames},
        },
        transfer=dict(
            source=transfer,
            questions={
                key: dict(target=goal, input_type=kind, private_answer=answers[key])
                for key, (goal, kind) in QUESTIONS.items()
            },
        ),
    )
    return {**data, "materials_digest": digest("binary-search-course-materials", data=data)}


def outline() -> dict[str, Any]:
    return dict(
        title=TITLE,
        objectives=[
            dict(
                id="interval",
                description="理解中点、比较与闭区间收缩",
                source="user_requirement",
                source_key="request_1",
                source_excerpt="理解中点计算、比较、区间更新及查找终止",
            ),
            dict(
                id="termination",
                description="区别命中与区间为空的结束条件",
                source="user_requirement",
                source_key="request_1",
                source_excerpt="查找终止",
            ),
        ],
        shared_example="binary-search-fixed-v1",
        terminology=[
            dict(term="闭区间", meaning="包含 left 和 right 两个端点"),
            dict(term="mid", meaning="当前轮次的中点下标"),
        ],
        conventions=["升序数组，零基下标", "比较方向为 values[mid] 相对于 target"],
        scenes=[
            dict(
                scene_key="binary_search",
                title=TITLE,
                purpose="跟踪主例的区间和中点，再用新数据判断更新与返回值",
                forms=["text", "code", "visualization", "exercise"],
                objective_ids=["interval", "termination"],
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
        "edumind_binary_search_v1",
        SCHEMA,
        stem_prompt_version=stem_prompt_version,
    )


def validate_content(raw: Any, mat: dict[str, Any]) -> None:
    fixed.validate_fixed_content(raw, mat, VALIDATOR, "BINARY_SEARCH")


def assemble(raw: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    mat = materials()
    validate_content(raw, mat)
    captions = dict(
        initial="初始化闭区间",
        compare="计算中点并比较",
        narrowed="排除中点并更新区间",
        found="相等，返回下标",
    )
    elements = [
        dict(id=f"index-{index}", label=str(value), next_id=None)
        for index, value in enumerate(mat["main"]["values"])
    ]
    steps = [
        dict(
            caption=captions[frame["phase"]],
            elements=elements,
            highlight_ids=[] if frame["mid"] is None else [f"index-{frame['mid']}"],
            binary_search_frame=dict(**frame, code_anchor="binary-search-code", note=note["note"]),
        )
        for frame, note in zip(mat["main"]["frames"], raw["step_notes"], strict=True)
    ]
    return fixed.assemble_fixed_lesson(
        "binary-search",
        raw,
        source,
        mat,
        steps,
        "下标从 0 开始。每帧标出当前闭区间和本轮中点。更新帧中的中点来自刚完成的比较。",
        "二分查找的迁移练习",
    )
