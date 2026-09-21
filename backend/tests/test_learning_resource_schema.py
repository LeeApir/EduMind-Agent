"""P0 learning-resource output contracts remain strict and traceable."""

import pytest

from app.agents.learning_resource_prompt import learning_resource_prompt
from app.agents.learning_resource_schema import (
    RESOURCE_PROMPT_VERSION,
    LearningResourceType,
    ResourceSchemaError,
    resource_output_schema,
    validate_learning_resource,
)


def envelope(resource_type: str, content: dict[str, object]) -> dict[str, object]:
    return {
        "resource_type": resource_type,
        "prompt_version": RESOURCE_PROMPT_VERSION,
        "content": content,
    }


@pytest.mark.parametrize(
    ("resource_type", "value"),
    [
        (
            LearningResourceType.EXPLANATION,
            envelope("explanation", {"markdown": "链表通过 next 指针连接节点。"}),
        ),
        (
            LearningResourceType.CODE,
            envelope(
                "code",
                {
                    "language": "C",
                    "source": "printf(\"ok\\n\");",
                    "expected_output": "ok",
                    "key_steps": ["打印字符串"],
                    "display_only": True,
                },
            ),
        ),
        (
            LearningResourceType.EXERCISE,
            envelope(
                "exercise",
                {
                    "items": [
                        {
                            "id": "q1",
                            "question": "头插法的时间复杂度？",
                            "answer": "O(1)",
                            "explanation": "只修改常数个指针。",
                        },
                        {
                            "id": "q2",
                            "question": "尾插法需要什么？",
                            "answer": "尾指针",
                            "explanation": "可避免遍历。",
                        },
                        {
                            "id": "q3",
                            "question": "删除前要保存什么？",
                            "answer": "前驱节点",
                            "explanation": "需要重连 next。",
                        },
                    ]
                },
            ),
        ),
    ],
)
def test_three_resource_types_validate_with_traceable_prompt_version(
    resource_type: LearningResourceType, value: dict[str, object]
) -> None:
    validated = validate_learning_resource(value, expected_type=resource_type)
    assert validated == value
    assert validated is not value
    schema = resource_output_schema(resource_type)
    assert schema["properties"]["resource_type"] == {"const": resource_type.value}
    assert schema["properties"]["prompt_version"] == {"const": RESOURCE_PROMPT_VERSION}
    assert RESOURCE_PROMPT_VERSION in learning_resource_prompt(resource_type)


@pytest.mark.parametrize(
    ("resource_type", "value"),
    [
        (
            "explanation",
            envelope("explanation", {"markdown": "", "unsafe_extra": "ignored"}),
        ),
        (
            "code",
            envelope(
                "code",
                {
                    "language": "C",
                    "source": "main(){}",
                    "expected_output": "",
                    "key_steps": [],
                    "display_only": False,
                },
            ),
        ),
        (
            "exercise",
            envelope(
                "exercise",
                {
                    "items": [
                        {
                            "id": "repeat",
                            "question": "Q1",
                            "answer": "A1",
                            "explanation": "E1",
                        },
                        {
                            "id": "repeat",
                            "question": "Q2",
                            "answer": "A2",
                            "explanation": "E2",
                        },
                    ]
                },
            ),
        ),
        (
            "explanation",
            {
                "resource_type": "code",
                "prompt_version": "old-version",
                "content": {"markdown": "错类型"},
            },
        ),
    ],
)
def test_invalid_resource_shapes_or_versions_are_rejected(
    resource_type: str, value: dict[str, object]
) -> None:
    with pytest.raises(ResourceSchemaError):
        validate_learning_resource(value, expected_type=resource_type)


def test_code_schema_marks_source_as_display_only_and_exercises_are_about_three() -> None:
    code_schema = resource_output_schema("code")
    assert code_schema["properties"]["content"]["properties"]["display_only"] == {"const": True}
    exercise_schema = resource_output_schema("exercise")
    items = exercise_schema["properties"]["content"]["properties"]["items"]
    assert items["minItems"] == 2
    assert items["maxItems"] == 4
    assert "display-only" in learning_resource_prompt("code").lower()
