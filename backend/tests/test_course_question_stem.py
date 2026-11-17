"""Verify the actual request and local stem checks for the four fixed topics."""

import json
from copy import deepcopy
from functools import partial
from pathlib import Path

import pytest
from app.services import binary_search_course_materials as binary
from app.services import head_course_materials as head
from app.services import queue_course_materials as queue
from app.services import stack_course_materials as stack
from app.services.course_question_stem import PROMPT_VERSION
from app.services.free_course_snapshots import SnapshotError, canonical
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from test_binary_search_course_trial import teaching as binary_text
from test_head_course_empty import empty_payload, empty_text
from test_queue_course_trial import teaching as queue_text
from test_stack_course_trial import teaching_fixture as stack_text

from scripts import prepare_head_course_empty as head_package

ACCEPTANCE = Path(__file__).resolve().parents[2] / "docs" / "acceptance"


@pytest.fixture(params=["head", "stack", "queue", "binary-search"])
def topic(request):
    if request.param == "head":
        payload = empty_payload()
        return (
            partial(head.body, payload),
            partial(head.validate_content, payload),
            empty_text(payload),
        )
    module, text = {
        "stack": (stack, stack_text),
        "queue": (queue, queue_text),
        "binary-search": (binary, binary_text),
    }[request.param]
    return module.request, partial(module.validate_content, mat=module.materials()), text()


def test_versioned_request_contains_exact_stem_rules(topic):
    build, _, _ = topic
    old = build()
    request = json.loads(canonical(build(stem_prompt_version=PROMPT_VERSION)))
    system = request["input"][0]
    assert system["role"] == "system"
    old_system = old["input"][0]["content"]
    prefix = f"{old_system}\n[QUESTION STEM FORMAT course-question-stem-v2]\n"
    assert system["content"].startswith(prefix)
    rules = system["content"][len(prefix):]
    for clause in (
        "one nonblank line",
        "Do not include line breaks",
        "program appends the exact C scenario after the stem",
        "Do not copy scenario code",
        "No code fences, ASCII braces or ASCII semicolons",
        "'#include', '```', '~~~', '{', '}', ';'",
        "square brackets for JSON integer array notation",
        "required explanation separately for every question",
    ):
        assert clause in rules
    system["content"] = old_system
    assert request == old  # Includes the full strict Schema and the original material payload.
    with pytest.raises(ValueError, match="Unknown question stem prompt version"):
        build(stem_prompt_version="unknown")


def test_required_explanation_and_local_format_boundaries(topic):
    build, validate, raw = topic
    schema = build(stem_prompt_version=PROMPT_VERSION)["text"]["format"]["schema"]
    validator = Draft202012Validator(schema)
    question = next(iter(raw["questions"].values()))
    question["stem"] = "根据下方代码，填写有效元素。请用 JSON 整数数组作答，使用方括号 []。"
    before = deepcopy(raw)
    validate(raw)
    assert raw == before

    for stem in (
        "  ",
        "读题\n",
        "读题\u2028继续",
        "#include <stdio.h>",
        "```C",
        "~~~C",
        "{",
        "}",
        "x = 0;",
    ):
        question["stem"] = stem
        assert validator.is_valid(raw), repr(stem)
        with pytest.raises(SnapshotError, match="QUESTION_PROSE_REQUIRED"):
            validate(raw)

    question["stem"] = next(iter(before["questions"].values()))["stem"]
    question.pop("explanation")
    assert not validator.is_valid(raw)
    with pytest.raises((SnapshotError, ValidationError), match="TEACHING_SCHEMA|explanation"):
        validate(raw)
    assert "explanation" not in question


def test_legacy_request_bytes_match_frozen_packages():
    for directory, build in (
        ("phase-1.5-stack-lifo-t119", stack.request),
        ("phase-1.5-queue-fifo-t121", queue.request),
        ("phase-1.5-binary-search-t122", binary.request),
    ):
        assert canonical(build()) == (ACCEPTANCE / directory / "request.json").read_bytes()

    template = "teaching-request.template.json"
    raw = head_package.outputs()[template]
    for directory in ("phase-1.5-head-empty-t118", "phase-1.5-head-empty-t118-r02"):
        assert raw == (ACCEPTANCE / directory / template).read_bytes()


def test_head_version_rejects_the_legacy_code_in_stem_contract():
    with pytest.raises(SnapshotError, match="HEAD_STEM_PROMPT_REQUIRES_EMPTY_EXAMPLE"):
        head.body({"original_goal": head.GOAL}, stem_prompt_version=PROMPT_VERSION)
