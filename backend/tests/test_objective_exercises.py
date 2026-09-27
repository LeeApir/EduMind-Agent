"""Regress correct independently worded answers being mis-scored as free explanations."""

import asyncio
import json
from dataclasses import replace
from uuid import uuid4

import pytest

from app.agents.learning_resource_prompt import (
    RESOURCE_INSTRUCTION_VERSION,
    code_serialization_example,
    learning_resource_prompt,
    objective_serialization_example,
)
from app.agents.learning_resource_schema import LearningResourceType, validate_learning_resource
from app.agents.learning_unit_generator import PendingLearningResource
from app.agents.objective_exercises import objective_exercise_issues
from app.agents.review_agent import ReviewAgent
from app.services.provider_gateway import StructuredResult
from app.services.quiz_scoring import score_exercise_content
from tests.test_review_agent import QueueGateway, review


def test_format_diagnostic_retains_only_fixed_metrics_not_generated_text():
    from app.agents.objective_exercises import objective_format_diagnostics

    diagnostic = objective_format_diagnostics({"items": [{
        "question": "[填空题] secret-topic 结果是多少？仅填一个整数",
        "answer": "987654321", "explanation": "secret-explanation",
    }]})
    assert diagnostic[0]["blank_count"] == 0
    assert diagnostic[0]["answer_is_canonical_integer"] is True
    serialized = json.dumps(diagnostic)
    assert "secret" not in serialized and "987654321" not in serialized


CHOICE = "[单选题] 指针p=&x，p保存什么？\nA. x的地址\nB. x的值\nC. 类型\nD. 长度\n仅填 A、B、C 或 D"
BOOLEAN = "[判断题] 空指针可以安全解引用。仅填 T 或 F（T=正确，F=错误）"
FILL = "[填空题] int x=1; int *p=&x; *p=20; 此时x=____。仅填一个整数"
WHY_CHOICE = (
    "[单选题] 为什么数组下标访问通常为 O(1)？\n"
    "A. 可以根据下标计算地址\nB. 必须逐个遍历节点\nC. 需要移动全部元素\nD. 需要排序\n"
    "仅填 A、B、C 或 D"
)


def content(question=CHOICE, answer="A"):
    return {
        "items": [
            {"id": "q1", "question": question, "answer": answer, "explanation": "依据C规则。"},
            {"id": "q2", "question": BOOLEAN, "answer": "F", "explanation": "不能解引用。"},
        ]
    }


@pytest.mark.parametrize(
    "question,answer", [(CHOICE, "A"), (WHY_CHOICE, "A"), (BOOLEAN, "F"), (FILL, "20")]
)
def test_supported_formats_are_scoreable_without_prose_matching(question, answer):
    candidate = content(question, answer)
    assert objective_exercise_issues(candidate) == []
    scored = score_exercise_content(
        resource_id=uuid4(),
        resource_version=1,
        content=candidate,
        answers=[
            {"question_id": "q1", "answer": f" {answer.lower()} "},
            {"question_id": "q2", "answer": "f"},
        ],
    )
    assert scored.score == 1


@pytest.mark.parametrize(
    "question,answer",
    [
        ("请解释指针与地址的区别", "指针保存地址"),
        (CHOICE, "A和B"),
        (CHOICE, "A. x的地址"),
        (CHOICE.replace("B. x的值", "B. x的地址"), "A"),
        (CHOICE.replace("D. 长度\n", ""), "A"),
        (CHOICE + " 请说明理由", "A"),
        (WHY_CHOICE + " 请解释为什么", "A"),
        (WHY_CHOICE, "因为可以计算地址"),
        ("为什么数组访问是常数时间？请解释原因。", "计算地址"),
        (BOOLEAN, "正确"),
        (BOOLEAN.replace("仅填 T 或 F（T=正确，F=错误）", ""), "F"),
        (FILL, "20，因为修改了x"),
        (FILL, "020"),
        (FILL, "+20"),
        (FILL.replace("x=____", "x=____，p=____"), "20"),
    ],
)
def test_open_ambiguous_or_wrong_format_candidates_require_correction(question, answer):
    issues = objective_exercise_issues(content(question, answer))
    assert issues and issues[0]["severity"] == "major"
    assert question not in issues[0]["message"]


def candidate(value):
    return PendingLearningResource(
        LearningResourceType.EXERCISE,
        value,
        "learning-resources-v1",
        "generation",
        None,
        instruction_version=RESOURCE_INSTRUCTION_VERSION,
    )


def test_local_gate_revises_before_model_pass_and_corrected_candidate_gets_independent_review():
    corrected = {
        "resource_type": "exercise",
        "prompt_version": "learning-resources-v1",
        "content": content(),
    }

    async def scenario():
        gateway = QueueGateway([StructuredResult(corrected, "correction"), review("pass", [])])
        outcome = await ReviewAgent(gateway).review(candidate(content("为什么需要指针？", "解释")))
        assert outcome.approved and outcome.correction_attempts == 1
        assert len(gateway.requests) == 2
        assert "objective exercise" in gateway.requests[-1].prompt.messages[0].content

    asyncio.run(scenario())


def test_two_invalid_corrections_cannot_publish_and_legacy_version_is_not_rewritten():
    value = content("请解释指针", "指针保存地址")
    envelope = {
        "resource_type": "exercise",
        "prompt_version": "learning-resources-v1",
        "content": value,
    }

    async def scenario():
        gateway = QueueGateway([StructuredResult(envelope, "correction") for _ in range(2)])
        outcome = await ReviewAgent(gateway).review(candidate(value))
        assert not outcome.approved and outcome.correction_attempts == 2
        assert len(gateway.requests) == 2
        legacy = replace(candidate(value), instruction_version="learning-resources-instructions-v3")
        old = await ReviewAgent(QueueGateway([review("pass", [])])).review(legacy)
        assert old.approved and old.resource.instruction_version == legacy.instruction_version

    asyncio.run(scenario())


def test_generation_instruction_states_exact_scoring_and_keeps_schema_fields():
    prompt = learning_resource_prompt(LearningResourceType.EXERCISE)
    assert "normalized exact text" in prompt and "No open-ended" in prompt
    assert "[单选题]" in prompt and "[判断题]" in prompt and "[填空题]" in prompt
    assert "no extra kind/options keys" in prompt
    assert "Never ask for a memory address" in prompt
    assert "Type variety is NOT required" in prompt
    assert "pointer expression or code statement is NOT an integer" in prompt


def test_all_new_examples_serialize_and_obey_same_production_contract():
    exercise = validate_learning_resource(
        json.loads(objective_serialization_example()), expected_type="exercise"
    )
    assert objective_exercise_issues(exercise["content"]) == []
    code = validate_learning_resource(
        json.loads(code_serialization_example()), expected_type="code"
    )
    assert code["content"]["display_only"] is True
    assert "without ____" in learning_resource_prompt("exercise")
