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


def test_fixed_outline_covers_exact_goals_and_reviewed_materials():
    inputs = dict(PLANNING_INPUT, stack_boundaries=basis.FIXED_BATCH)
    plan = course.fixed_outline(inputs)
    objective_map = {o["id"]: o for o in plan["objectives"]}
    assert [
        (s["scene_key"], [objective_map[k]["source_excerpt"] for k in s["objective_ids"]],
         s["depends_on"])
        for s in plan["scenes"]
    ] == [
        ("normal", ["追踪正常入栈和出栈，解释栈顶与后进先出"], []),
        (
            "rejections",
            ["解释满栈为什么拒绝入栈", "解释空栈为什么拒绝出栈，以及拒绝后哪些状态保持不变"],
            ["normal"],
        ),
    ]
    assert plan["shared_example"] == basis.VERSION
    assert {o["source_key"] for o in plan["objectives"]} == {"request_1"}
    data = basis.materials()
    normal, rejections = [data["scenes"][s["scene_key"]] for s in plan["scenes"]]
    assert (data["capacity"], len(normal["frames"]), len(rejections["frames"])) == (3, 5, 9)
    assert [f["popped"] for f in normal["frames"]] == [None, None, None, 8, None]
    assert "int data[CAP]; size_t count;" in rejections["source"]
    for index, condition in ((4, "s->count == CAP"), (8, "s->count == 0")):
        prev, refused = rejections["frames"][index - 1:index + 1]
        assert f"if ({condition}) return false;" in rejections["source"]
        assert refused["success"] is False and refused["popped"] is None
        assert all(refused[key] == prev[key] for key in ("values", "count", "storage", "output"))
    fake = scene_input(example_plan(), "s1", [])
    fake["request"] = inputs
    with pytest.raises(SnapshotError, match="STACK_FIXED_OUTLINE_BINDING"):
        course.bound_scene_request(fake)


def test_practice_checkpoints_from_independent_expectations():
    from hashlib import sha256

    data = basis.materials()
    evidence = basis.practice_evidence(data)["scenes"]
    reference = json.loads((Path(__file__).resolve().parents[2] /
        "docs/acceptance/phase-1.5-stack-lifo-t119/independent-reference.json").read_bytes()
    )["transfer"]
    for scene in evidence.values():
        assert scene["code_sha256"] == sha256(scene["code"].encode()).hexdigest()
        for q in scene["questions"].values():
            assert q["practice_code_sha256"] == scene["code_sha256"]
            for checkpoint in q["checkpoints"]:
                assert checkpoint["observation"] == "after_call"
                line = checkpoint["after"]["call_line"]
                assert checkpoint["after"]["operation"].split("(")[0] in (
                    scene["code"].splitlines()[line - 1]
                )

    normal = evidence["normal"]["questions"]
    for key, index in (("first_pop", 4), ("final_top", 7)):
        q = normal[key]
        assert q["reference_answer"] == str(reference["answers"][key])
        check, = q["checkpoints"]
        for state, frame in ((check["before"], index - 1), (check["after"], index)):
            assert state["frame_id"] == f"f{frame}"
            for field in ("values", "top", "popped"):
                assert state[field] == reference[field][frame]
    first = normal["first_pop"]["checkpoints"][0]
    assert first["before"]["value_status"] == "uninitialized"
    assert first["after"]["value"] == 2

    boundary = evidence["rejections"]["questions"]
    assert {k: q["reference_answer"] for k, q in boundary.items()} == {
        "full_count": "3", "empty_return": "0", "empty_output": "1", "guard_pair": "A",
    }
    for key, indices in (
        ("full_count", (4,)), ("empty_return", (8,)), ("empty_output", (8,)),
        ("guard_pair", (4, 8)),
    ):
        for check, index in zip(boundary[key]["checkpoints"], indices, strict=True):
            before, after = check["before"], check["after"]
            assert (before["frame_id"], after["frame_id"]) == (f"f{index-1}", f"f{index}")
            assert after["success"] is False and after["popped"] is None
            assert (after["values"], after["count"], after["storage"], after["value"]) == (
                ([1, 2, 4], 3, [1, 2, 4], -99) if index == 4 else ([], 0, [1, 2, 4], 1)
            )
            assert all(before[k] == after[k] for k in ("values", "count", "storage", "value"))
            assert after["guard_line"] == (9 if index == 4 else 16)
    wrong = deepcopy(data)
    wrong["scenes"]["normal"]["exercise_source"] = data["scenes"]["normal"]["source"]
    with pytest.raises(SnapshotError, match="STACK_PRACTICE_CODE_MISMATCH"):
        basis.practice_evidence(wrong)


def practice_fixture(payload):
    fact_id = next(iter(payload["demonstration"]["facts"]))
    return dict(
        paragraphs=[
            dict(text="仅检查装配。", fact_ids=[fact_id]),
            dict(text="仅检查引用。", fact_ids=[fact_id]),
        ],
        explanations={
            key: dict(
                text="离线解析夹具。", evidence_id=q["evidence_id"],
                checkpoint_ids=[c["id"] for c in q["checkpoints"]],
            )
            for key, q in payload["practice"]["questions"].items()
        },
    )


def test_practice_assembly_rejects_mixed_evidence():
    request = dict(PLANNING_INPUT, stack_boundaries=basis.EVIDENCE_BATCH)
    plan = course.fixed_outline(request)
    inputs = scene_input(plan, "s1", [])
    inputs["request"] = request
    payload = json.loads(course.bound_scene_request(inputs).prompt.messages[1].content)
    assert "scene_material" not in payload and "upstream" not in payload
    assert set(payload["demonstration"]) == {
        "source", "frames", "demonstrated", "text_only", "facts",
    }
    assert payload["practice"]["code"] != payload["demonstration"]["source"]
    raw = practice_fixture(payload)
    blocks = course.assemble(raw, inputs)["blocks"]
    assert next(b["source"] for b in blocks if b["anchor_id"] == "practice-code") == (
        payload["practice"]["code"]
    )
    items = next(b["items"] for b in blocks if b["kind"] == "exercise")
    assert [(q["answer_key"], q["solution"]) for q in items] == [
        ("2", "离线解析夹具。"), ("-4", "离线解析夹具。"),
    ]

    for field, value in (
        ("evidence_id", "demo.normal.f3"),
        ("evidence_id", "practice.rejections.full_count"),
        ("checkpoint_ids", ["practice.normal.first_pop.after-f7"]),
    ):
        bad = deepcopy(raw)
        bad["explanations"]["first_pop"][field] = value
        with pytest.raises(SnapshotError, match="STACK_EXERCISE_EVIDENCE_BINDING"):
            course.assemble(bad, inputs)

    bad = deepcopy(raw)
    bad["explanations"]["first_pop"] = deepcopy(raw["explanations"]["final_top"])
    with pytest.raises(SnapshotError, match="STACK_EXERCISE_EVIDENCE_BINDING"):
        course.assemble(bad, inputs)

    bad = deepcopy(raw)
    bad["paragraphs"][0]["fact_ids"] = ["practice.normal.first_pop"]
    with pytest.raises(SnapshotError, match="STACK_SCENE_CONTENT"):
        course.assemble(bad, inputs)


def test_typed_practice_assembly_uses_t155_input_rules():
    from app.services.free_course_answers import compare_answer, comparison_rule
    from app.services.free_scene_generation import generation_contract

    expected = {
        "first_pop": ("integer", "[-4,9]", "2"),
        "final_top": ("integer", "[-4,9]", "-4"),
        "full_count": ("integer", "[0,3]", "3"),
        "empty_return": ("integer", "0 或 1", "0"),
        "empty_output": ("integer", "[-99,7]", "1"),
        "guard_pair": ("short_text", "输入 A 或 B，大小写均可", "A"),
    }

    def assemble_both(batch):
        planning_input = dict(PLANNING_INPUT, stack_boundaries=batch)
        plan = course.fixed_outline(planning_input)
        upstream = []
        questions = {}
        for scene_id, scene_key in (("s1", "normal"), ("s2", "rejections")):
            inputs = scene_input(plan, scene_id, upstream)
            inputs["request"] = planning_input
            inputs["plan"]["digest"] = "0" * 64
            request, check, prompt_version, wire_version = generation_contract(inputs)
            payload = json.loads(request.prompt.messages[1].content)
            assert payload["materials_digest"] == basis.materials_digest(batch)
            assert payload["prompt_version"] == prompt_version
            assert wire_version == course.EVIDENCE_WIRE
            assert payload["plan_source"] == "fixed_outline"
            raw = practice_fixture(payload)
            source = dict(
                origin="stack_boundaries_model_generation", batch=batch, model="deepseek-flash",
                prompt_version=prompt_version, plan_source="fixed_outline",
                plan_digest=inputs["plan"]["digest"], materials_digest=payload["materials_digest"],
                candidate_digest="a" * 64, review_sha256="b" * 64, evidence_kind="offline_fixture",
                scene_key=scene_key, parent_digest=None, source_request_sha256="c" * 64,
                source_response_sha256="d" * 64,
            )
            checked = check(dict(raw_output=raw, generation_source=source), inputs)["cleaned"]
            group = next(b for b in checked["content"]["blocks"] if b["kind"] == "exercise")
            shown = next(b for b in course.assemble(raw, inputs)["blocks"]
                         if b["kind"] == "exercise")
            assert shown == group
            if batch == basis.TYPED_PRACTICE_BATCH:
                assert prompt_version == course.TYPED_PRACTICE_PROMPT
                assert "整数题格式示例：12 或 -7" in group["question"]
                assert "未参与数值比较" in group["question"]
                assert comparison_rule(group) == "free-course-typed-json-v1"
                for q in group["items"]:
                    evidence = payload["practice"]["questions"][q["question_id"]]
                    assert evidence["input_type"] == q["input_type"]
                    assert q["question"].endswith(evidence["input_instruction"])
            else:
                assert "格式示例" not in group["question"]
                assert comparison_rule(group) == "quiz-exact-text-v1"
            questions.update((q["question_id"], q) for q in group["items"])
            upstream = [dict(scene_id=scene_id, scene_version_id="v-normal",
                             digest="fixture", **checked)]
        return questions

    typed = assemble_both(basis.TYPED_PRACTICE_BATCH)
    old = assemble_both(basis.EVIDENCE_BATCH)
    assert typed.keys() == old.keys() == expected.keys()
    assert "一个大写字母" in old["guard_pair"]["question"]
    for key, (kind, hint, answer) in expected.items():
        q = typed[key]
        assert q["input_type"] == kind and hint in q["question"]
        assert ("JSON 整数" in q["question"]) == (kind == "integer")
        assert old[key]["input_type"] == "short_text" and "JSON 整数" not in old[key]["question"]
        assert q["answer_key"] == old[key]["answer_key"] == answer
        assert compare_answer(q, answer) == (True, q["solution"])

    for key, value in (
        ("first_pop", "+2"), ("final_top", "-04"), ("final_top", "−4"),
        ("full_count", "+3"), ("empty_output", "+1"),
    ):
        matched, feedback = compare_answer(typed[key], value)
        assert not matched and feedback.startswith("请输入一个 JSON 整数，不附加文字。")
    for key, value in (("empty_return", "-0"), ("guard_pair", "a")):
        assert compare_answer(typed[key], value) == (True, typed[key]["solution"])
