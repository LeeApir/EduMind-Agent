"""Versioned, type-specific instructions for P0 learning resource generation."""

import json

from app.agents.learning_resource_schema import (
    RESOURCE_PROMPT_VERSION,
    LearningResourceType,
    resource_output_schema,
)

RESOURCE_INSTRUCTION_VERSION = "learning-resources-instructions-v8"
OBJECTIVE_INSTRUCTION_VERSIONS = frozenset(
    {
        "learning-resources-instructions-v4",
        "learning-resources-instructions-v5",
        "learning-resources-instructions-v6",
        "learning-resources-instructions-v7",
        "learning-resources-instructions-v8",
    }
)

_COMMON_INSTRUCTIONS = """Create exactly one requested learning resource in Chinese.
Return only JSON matching the supplied schema. Use the requested prompt_version unchanged.
Do not claim to execute, compile, or run code; code is display-only. Do not add facts that
are unsupported by the learning context."""

_JSON_SERIALIZATION_INSTRUCTIONS = r"""Serialization contract: emit one complete JSON object,
not Markdown around JSON. All Markdown and source code belong INSIDE JSON string values.
Escape every newline as \n, double quote as \", and backslash as \\ inside strings.
Never put literal line breaks inside a quoted JSON string. For math, prefer plain text;
if using LaTeX, escape its backslashes for JSON (for example \\frac, not \frac).
Do not wrap the response in a ```json fence or add comments/trailing commas. Check that
the whole response parses as JSON before returning; do not claim to have run a parser."""


def explanation_serialization_example() -> str:
    """Use real serialization so the instruction example cannot teach invalid JSON."""
    return json.dumps(
        {
            "resource_type": "explanation",
            "prompt_version": RESOURCE_PROMPT_VERSION,
            "content": {"markdown": '# 示例\n数组下标访问通常为 O(1)。示例字符串："x"。'},
        },
        ensure_ascii=False,
    )


def objective_serialization_example() -> str:
    return json.dumps(
        {
            "resource_type": "exercise",
            "prompt_version": RESOURCE_PROMPT_VERSION,
            "content": {
                "items": [
                    {
                        "id": "q1",
                    "question": ("[单选题] 已初始化指针保存什么？\nA. 地址\nB. 对象的值\n"
                                 "C. 类型名\nD. 对象大小\n仅填 A、B、C 或 D"),
                        "answer": "A",
                        "explanation": "指针保存地址。",
                    },
                    {
                        "id": "q2",
                        "question": "[判断题] 空指针可以安全解引用。仅填 T 或 F（T=正确，F=错误）",
                        "answer": "F",
                        "explanation": "不能解引用空指针。",
                    },
                    {
                        "id": "q3",
                        "question": (
                            "[单选题] int x=1; int *p=&x; *p=20; 此时x的值为？\n"
                            "A. 1\nB. 20\nC. 0\nD. 无法确定\n仅填 A、B、C 或 D"
                        ),
                        "answer": "B",
                        "explanation": "通过已初始化指针赋值修改x为20。",
                    },
                ]
            },
        },
        ensure_ascii=False,
    )


def code_serialization_example() -> str:
    return json.dumps(
        {
            "resource_type": "code",
            "prompt_version": RESOURCE_PROMPT_VERSION,
            "content": {
                "language": "C",
                "source": "int main(void) { return 0; }",
                "expected_output": "无标准输出",
                "key_steps": ["返回成功状态"],
                "display_only": True,
            },
        },
        ensure_ascii=False,
    )


_TYPE_INSTRUCTIONS: dict[LearningResourceType, str] = {
    LearningResourceType.EXPLANATION: (
        "Write a short Markdown explanation with a concrete example and only necessary formulas."
        " The envelope has exactly three root fields resource_type, prompt_version, content. "
        "content is an object with exactly one field markdown, whose value is a JSON string. "
        "After ending that string, close the content object and the root object exactly once "
        "each, then STOP. Do not emit a third closing brace or any suffix after the root. "
        "Match structural opening and closing braces; braces inside escaped strings are text."
    ),
    LearningResourceType.CODE: (
        "Use exactly the requested programming language. Include one source listing, expected "
        "output, and concise key steps; set display_only to true."
    ),
    LearningResourceType.EXERCISE: (
        "Create about three independent OBJECTIVE exercises (two to four). The server scores "
        "normalized exact text, never semantic equivalence. Each question must have exactly "
        "one unambiguous answer and explicitly tell the learner the accepted response format. "
        "Use only these formats: (1) question starts [单选题], has four separate option lines "
        "A. text through D. text, ends 仅填 A、B、C 或 D; answer is one uppercase A-D letter. "
        "(2) question starts [判断题], ends 仅填 T 或 F（T=正确，F=错误）; answer is T or F. "
        "(3) question starts [填空题], has exactly one ____ blank, ends 仅填一个整数; "
        "answer is one canonical decimal integer, no units/leading zeros/plus sign. "
        "An integer fill must ask for a concrete computable numeric result with all values "
        "given. Never ask for a memory address, pointer identity, concept, or explanation "
        "as an integer; use single-choice or true/false for those concepts. Never invent "
        "an arbitrary numeric key just to fit the format. Avoid undefined C behavior. "
        "Type variety is NOT required: do not force one exercise of every format. "
        "Prefer single-choice or true/false for conceptual facts and pointer rewiring. "
        "Use integer fill only when a concrete numeric calculation is naturally meaningful. "
        "A pointer expression or code statement is NOT an integer answer; ask learners to "
        "choose the correct operation instead. "
        "No open-ended questions, multiple blanks, multiple correct options, requests to "
        "explain/prove/justify, or prose answer keys. Put teaching reasoning ONLY in "
        "explanation. Review option uniqueness and the answer key against the facts. "
        "Keep existing JSON fields id/question/answer/explanation, no extra kind/options keys."
        " IMPORTANT: a [填空题] MUST contain the literal four-underscore string ____ "
        "exactly once inside the question; a question asking '多少/是多少' without ____ "
        "does NOT meet this contract. Rewrite it as a blank, not an open numeric question."
    ),
}


def learning_resource_prompt(resource_type: LearningResourceType | str) -> str:
    """Build the versioned system instruction for a single resource type."""
    try:
        normalized_type = LearningResourceType(resource_type)
    except ValueError:
        raise ValueError("Unsupported learning resource type.") from None
    return (
        f"{_COMMON_INSTRUCTIONS}\nPrompt version: {RESOURCE_PROMPT_VERSION}.\n"
        f"Instruction version: {RESOURCE_INSTRUCTION_VERSION}.\n"
        f"Requested resource type: {normalized_type.value}.\n"
        f"{_TYPE_INSTRUCTIONS[normalized_type]}\n{_JSON_SERIALIZATION_INSTRUCTIONS}"
        + "\nRequired output contract (all nested required keys must be present; "
        "use exactly these names and types, including expected_output, key_steps and "
        "display_only for code and answer/explanation for every exercise):\n"
        + json.dumps(resource_output_schema(normalized_type), ensure_ascii=False)
        + (
            "\nSerialization example only; replace its facts with the requested node:\n"
            + {
                LearningResourceType.EXPLANATION: explanation_serialization_example,
                LearningResourceType.CODE: code_serialization_example,
                LearningResourceType.EXERCISE: objective_serialization_example,
            }[normalized_type]()
        )
    )
