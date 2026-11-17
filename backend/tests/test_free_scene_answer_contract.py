"""Generation guidance does not redefine Schema acceptance or scoring authority."""

import asyncio
import json
from copy import deepcopy

import pytest
from test_free_scene_generation import Gateway, authorize, inputs, response

from app.agents.free_course_planning import request_digest
from app.agents.free_scene_generation import SCHEMA, build_request, generate_once, validate_response
from app.services.free_course_snapshots import SnapshotError, canonical
from app.services.quiz_scoring import _canonical_answer


def closed_candidate():
    raw = response()
    raw["blocks"][1]["source"] = "int a[5] = {10, 20, 30, 40, 50}; a[3] = 99;"
    raw["blocks"][2]["question"] = "分别按各题说明的状态作答，不沿用上一题的修改。"
    raw["blocks"][2]["items"] = [
        dict(
            question_id="initial",
            input_type="short_text",
            question=(
                "仅按初始数组a={10,20,30,40,50}，未执行赋值。a[3]是多少？"
                "答案域为0至100的整数；只输入十进制数字，不带单位、前导零或解释。"
            ),
            answer_key="40",
            solution="下标从0开始，初始第4个元素为40。",
        ),
        dict(
            question_id="after",
            input_type="short_text",
            question=(
                "从初始a={10,20,30,40,50}执行一次a[3]=99后，a[3]是多少？"
                "答案域为0至100的整数；只输入十进制数字，不带单位、前导零或解释。"
            ),
            answer_key="99",
            solution="赋值只把下标3的元素改为99。",
        ),
        dict(
            question_id="reason",
            input_type="short_text",
            question=(
                "对普通连续存储且元素等宽的数组，已知合法下标，直接访问通常为何比顺序查找少比较？"
                "选项A：可由首地址和下标计算元素位置；选项B：必须从首元素依次比较所有值。"
                "答案域仅为A、B；只输入一个大写字母，不带标点或解释。"
            ),
            answer_key="A",
            solution="等宽连续存储允许按地址偏移定位；顺序查找需逐项比较。",
        ),
    ]
    return raw


@pytest.mark.parametrize(
    "forms",
    [
        ["text"],
        ["code"],
        ["exercise"],
        ["visualization"],
        ["text", "code", "exercise", "visualization"],
    ],
)
def test_kind_fields_and_answer_contract_preserve_schema_forms_and_sources(forms):
    data = inputs(forms=forms)
    before = deepcopy(data)
    req = build_request(data)
    wire = json.loads(req.prompt.messages[-1].content)
    contract = wire["response_contract"]
    assert wire["prompt_version"] == "free-scene-generation-v5"
    assert set(contract["fields_by_block_kind"]) == set(forms) | {"text"}
    for definition in SCHEMA["$defs"].values():
        kind = definition.get("properties", {}).get("kind", {}).get("const")
        if kind in contract["fields_by_block_kind"]:
            assert set(contract["fields_by_block_kind"][kind]) == set(definition["properties"])
    if "code" in forms:
        assert "markdown" not in contract["fields_by_block_kind"]["code"]
    assert contract["exercise_answers"]["scoring_reliability"].startswith("unverified")
    assert data == before
    for key in data:
        assert wire[key] == data[key]
    assert req.json_schema == SCHEMA


def test_bounded_trace_and_reasoning_choices_are_schema_candidates_only():
    raw = closed_candidate()
    before = deepcopy(raw)
    result = asyncio.run(generate_once(Gateway(raw), inputs(), authorize_send=authorize))
    assert result.state == "candidate" and result.response == before
    qs = raw["blocks"][2]["items"]
    initial = [10, 20, 30, 40, 50]
    after = initial.copy()
    after[3] = 99
    assert qs[0]["answer_key"] == str(initial[3])
    assert qs[1]["answer_key"] == str(after[3])
    assert _canonical_answer("40") != _canonical_answer(qs[1]["answer_key"])
    assert _canonical_answer("99") != _canonical_answer(qs[0]["answer_key"])
    assert _canonical_answer("A") == _canonical_answer(qs[2]["answer_key"])
    assert _canonical_answer("B") != _canonical_answer(qs[2]["answer_key"])
    assert result.response == raw == before
    # No review/qualification/mastery flag is created by this structural operation.
    assert set(result.response) == {"blocks", "actions"}


@pytest.mark.parametrize("bad_field", ["markdown", "answer_key", "question"])
def test_cross_kind_empty_fields_still_fail_and_raw_is_retained(bad_field):
    raw = closed_candidate()
    raw["blocks"][1][bad_field] = ""
    before = deepcopy(raw)
    result = asyncio.run(generate_once(Gateway(raw), inputs(), authorize_send=authorize))
    assert result.state == "failed" and result.reason_code == "SCHEMA_INVALID"
    assert result.response == raw == before


def test_open_answer_is_not_silently_rewritten_or_labeled_reliable():
    raw = closed_candidate()
    raw["blocks"][2]["items"][0].update(
        question="请用一句话解释数组访问的原理", answer_key="连续内存可计算偏移"
    )
    before = deepcopy(raw)
    assert validate_response(raw, inputs()) == before
    # Output Schema intentionally unchanged: semantic review must detect unreliability.
    assert raw == before


@pytest.mark.parametrize("unit", ["x", "中"])
def test_complete_new_payload_has_exact_byte_boundary_without_truncation(unit):
    data = inputs()
    data["request"]["original_goal"] = ""
    payload = json.loads(build_request(data).prompt.messages[-1].content)
    overhead = len(canonical(payload))
    count = (128000 - overhead) // len(unit.encode())
    data["request"]["original_goal"] = unit * count
    req = build_request(data)
    assert 128000 - len(unit.encode()) < len(req.prompt.messages[-1].content.encode()) <= 128000
    data["request"]["original_goal"] += unit
    gateway = Gateway()
    with pytest.raises(SnapshotError, match="SCENE_INPUT_TOO_LARGE"):
        asyncio.run(generate_once(gateway, data, authorize_send=authorize))
    assert not gateway.requests


def test_new_contract_is_in_request_identity_and_caller_cannot_mutate_schema():
    req = build_request(inputs())
    before = request_digest(req)
    req.json_schema["additionalProperties"] = True
    assert request_digest(req) != before
    assert SCHEMA["additionalProperties"] is False
