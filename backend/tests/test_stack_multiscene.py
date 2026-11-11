"""Independent C execution and grounded planning/scene request checks."""

import json
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from app.services import stack_course_materials as stack
from app.services import stack_multiscene as course
from app.services import stack_multiscene_materials as basis
from app.services.free_course_snapshots import SnapshotError

PLANNING_INPUT = dict(
    course_id="00000000-0000-0000-0000-000000000001",
    operation_id="00000000-0000-0000-0000-000000000002",
    request_id="00000000-0000-0000-0000-000000000003",
    original_goal=basis.GOAL, teaching_language="zh-CN", code_language="C",
    learner_evidence={}, profile_id=None, profile_version=None,
)
PLANNING_INPUT["request_sources"] = dict(request_1=dict(
    request_id=PLANNING_INPUT["request_id"], version=1, text=basis.GOAL,
))


def example_plan():
    # A local protocol fixture, not a generated or approved plan.
    def objective(key, quote):
        return dict(id=key, description=quote, source="user_requirement", source_key="request_1",
                    source_excerpt=quote)

    return dict(
        title="数组栈的正常操作与拒绝",
        shared_example=basis.VERSION,
        terminology=[dict(term="count", meaning="有效元素个数")],
        conventions=["固定容量 3，按栈底到栈顶排列有效元素"],
        objectives=[
            objective("trace", basis.NORMAL_GOAL),
            objective("full", basis.FULL_GOAL),
            objective("empty", basis.EMPTY_GOAL),
        ],
        scenes=[
            dict(scene_key="normal", title="正常操作", purpose="追踪成功操作和栈顶变化",
                 forms=list(basis.FORMS), objective_ids=["trace"], depends_on=[]),
            dict(scene_key="rejections", title="两种拒绝", purpose="比较满栈和空栈的守卫及原状态",
                 forms=list(basis.FORMS), objective_ids=["full", "empty"], depends_on=["normal"]),
        ],
    )


def response(plan):
    return dict(needs_clarification=False, plan=plan, questions=[], reason=None, source_keys=[])


def scene_input(plan, scene_id, upstream):
    return dict(
        request=PLANNING_INPUT, scene_id=scene_id,
        plan=dict(candidate=plan, scenes=[
            dict(plan["scenes"][0], scene_id="s1"),
            dict(plan["scenes"][1], scene_id="s2", depends_on=["s1"]),
        ]),
        expected_head=1 if scene_id == "s1" else 2, upstream=upstream, lease_epoch=1,
    )


def test_rejections_against_independent_c(tmp_path):
    mats = basis.materials()["scenes"]
    cases = (
        ("source", [
            (1, 1, 3, 0, 0, -99), (1, 2, 3, 8, 0, -99),
            (1, 3, 3, 8, 5, -99), (0, 3, 3, 8, 5, -99),
            (1, 2, 3, 8, 5, 5), (1, 1, 3, 8, 5, 8),
            (1, 0, 3, 8, 5, 3), (0, 0, 3, 8, 5, 3),
        ]),
        ("exercise_source", [
            (1, 1, 1, 0, 0, -99), (1, 2, 1, 2, 0, -99),
            (1, 3, 1, 2, 4, -99), (0, 3, 1, 2, 4, -99),
            (1, 2, 1, 2, 4, 4), (1, 1, 1, 2, 4, 2),
            (1, 0, 1, 2, 4, 1), (0, 0, 1, 2, 4, 1),
        ]),
    )
    data = mats["rejections"]
    for kind, expected in cases:
        src = tmp_path / f"{kind}.c"
        binary = tmp_path / kind
        src.write_text(data[kind])
        subprocess.run(
            ["clang", "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(binary)],
            check=True,
        )
        output = subprocess.check_output([str(binary)], text=True)
        assert [tuple(map(int, line.split())) for line in output.splitlines()] == expected
    frames = data["frames"]
    assert [
        (f["success"], f["count"], *f["storage"], f["output"]) for f in frames[1:]
    ] == cases[0][1]
    assert [(f["values"], f["top"], f["popped"]) for f in frames] == [
        ([], None, None), ([3], 3, None), ([3, 8], 8, None), ([3, 8, 5], 5, None),
        ([3, 8, 5], 5, None), ([3, 8], 8, 5), ([3], 3, 8), ([], None, 3), ([], None, None),
    ]
    assert [(f["frame_id"], f["guard_line"], f["line"]) for f in frames if f["rejection"]] == [
        ("f4", 9, 31), ("f8", 16, 39),
    ]
    assert [q["private_answer"] for q in data["questions"]] == ["3", "0", "1", "A"]
    assert [q["private_answer"] for q in mats["normal"]["questions"]] == ["2", "-4"]
    root = Path(__file__).resolve().parents[2]
    ref = root / "docs/acceptance/phase-1.5-stack-lifo-t119/independent-reference.json"
    assert mats["normal"]["frames"] == json.loads(ref.read_bytes())["main"]
    assert mats["normal"]["source"] == stack.materials()["main"]["source"]


def test_exact_plan_request_and_scene_bindings():
    plan = example_plan()
    req = course.planning_request(PLANNING_INPUT)
    data = json.loads(req.prompt.messages[1].content)
    assert data["supported_material"]["id"] == basis.VERSION
    assert data["supported_material"]["scene_goal_excerpts"] == {
        key: list(excerpts) for key, excerpts in basis.SCENE_GOALS.items()
    }
    assert course.validate_plan(response(plan), PLANNING_INPUT)["plan"] == plan
    wrong = deepcopy(plan)
    wrong["scenes"][1]["depends_on"] = []
    with pytest.raises(SnapshotError, match="STACK_PLAN_SCOPE"):
        course.validate_plan(response(wrong), PLANNING_INPUT)
    wrong = deepcopy(plan)
    wrong["scenes"][0]["objective_ids"] = ["full", "trace"]
    wrong["scenes"][1]["objective_ids"] = ["empty"]
    with pytest.raises(SnapshotError, match="STACK_PLAN_SCOPE"):
        course.validate_plan(response(wrong), PLANNING_INPUT)
    first = scene_input(plan, "s1", [])
    with pytest.raises(SnapshotError, match="STACK_SCENE_DEPENDENCY"):
        course.scene_request(scene_input(plan, "s2", []))
    normal = dict(
        paragraphs=[dict(text="离线夹具一。", fact_ids=["order"]),
                    dict(text="离线夹具二。", fact_ids=["f3"])],
        explanations=dict(first_pop="夹具解析。", final_top="夹具解析。"),
    )
    assembled = course.assemble(normal, first)
    second = scene_input(plan, "s2", [
        dict(scene_id="s1", scene_version_id="v-normal", digest="fixture",
             content={"blocks": assembled["blocks"]}, actions=assembled["actions"],
             dependencies=[]),
    ])
    n_req = course.scene_request(first)
    b_req = course.scene_request(second)
    assert n_req.json_schema != b_req.json_schema
    n_mat = json.loads(n_req.prompt.messages[1].content)["scene_material"]
    b_payload = json.loads(b_req.prompt.messages[1].content)
    assert len(n_mat["frames"]) == 5 and len(b_payload["scene_material"]["frames"]) == 9
    assert b_payload["upstream"][0]["scene_version_id"] == "v-normal"
    with pytest.raises(SnapshotError, match="STACK_SCENE_CONTENT"):
        course.assemble(normal, second)
    boundary = dict(normal, explanations={key: "夹具解析。" for key in
                   b_req.json_schema["properties"]["explanations"]["required"]})
    blocks = course.assemble(boundary, second)["blocks"]
    assert [q["answer_key"] for q in blocks[-1]["items"]] == ["3", "0", "1", "A"]
    visual = next(block for block in blocks if block["kind"] == "visualization")
    assert "满栈拒绝 · 返回 false · count=3，value=-99" in visual["steps"][4]["caption"]
    assert "空栈拒绝 · 返回 false · count=0，value=3" in visual["steps"][8]["caption"]
